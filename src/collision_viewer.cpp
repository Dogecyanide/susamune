#include "susamune/collision_viewer.hxx"
#include "susamune/collision_geometry.h"
#include "susamune/ghost_camera.hxx"
#include "susamune/game_wireframe.hxx"
#include "susamune/mem2_map.h"
#include "susamune/menu.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/settings.hxx"
#include "susamune/transfer_lease.hxx"
#include "Dolphin/GX.h"
#include "Dolphin/MTX.h"
#include "Dolphin/mem.h"
#include "Dolphin/printf.h"
#include "JSystem/JKernel/JKRHeap.hxx"
#include "SMS/Map/MapCollisionData.hxx"
#include "SMS/Player/Mario.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "SMS/System/Resolution.hxx"

namespace CollisionViewer {
namespace {
const char kCollisionFloorFormat[] = "Floor %04X value %d flags %04X";
const char kCollisionNoFloor[] = "Floor: no active triangle";
const char kCollisionLimit[] = "Collision view: invalid pool data";
const char *const kCollisionLabels[] = {"Floor", "Slippery (2)",
    "Very slippery (1)", "Slide (C)", "No-slip (3)", "Wet / water-slip",
    "Water", "Sand", "Warp / exit", "Wall", "Ceiling", "OOB / death", "Current floor"};
const u32 kCollisionColors[] = {0x3078ffff, 0x60c8ffff, 0x3030bfff,
    0x9870ffff, 0x4848ffff, 0x20a8bfff, 0x40e8ffff, 0xe8b048ff,
    0xc868e8ff, 0x30d050ff, 0xf04040ff, 0x888888ff, 0xffe63cff};
constexpr u32 kTriangleCapacity = 131072;
constexpr u32 kRetainedWords = kTriangleCapacity / 32 -
    SUSAMUNE_COLLISION_BITS_SIZE / sizeof(u32);
u32 sActiveTriangles[kRetainedWords];
u16 sFloorType, sFloorFlags;
s16 sFloorValue;
bool sFloorValid, sLimit, sDrawn;
static_assert(sizeof(TBGCheckData) == 0x48 && sizeof(TBGCheckList) == 0xc &&
              sizeof(TBGCheckListWarp) == 0x14 && sizeof(TBGCheckListRoot) == 0x24, "collision layout changed");
static_assert(__builtin_offsetof(TMapCollisionData, mCollisionTris) == 0x28 &&
              __builtin_offsetof(TMapCollisionData, mCheckDataCount) == 0x34, "collision pool offsets changed");
static_assert(sizeof(sActiveTriangles) + SUSAMUNE_COLLISION_BITS_SIZE ==
              kTriangleCapacity / 8, "collision capacity changed");

u32 *spillTriangles() {
    return reinterpret_cast<u32 *>(SUSAMUNE_COLLISION_BITS_PPC_BASE);
}
u32 &activeWord(u32 index) {
    return index < kRetainedWords ? sActiveTriangles[index] :
        spillTriangles()[index - kRetainedWords];
}
bool finite(f32 f) {
    // Float comparisons may assume away NaNs under the production fast-math flags.
    union { f32 value; u32 bits; } v = {f};
    return (v.bits & 0x7fffffffu) < 0x49742400u; // abs(f) < 1,000,000
}
bool span(const void *p, u32 bytes, u32 lo, u32 hi) {
    const u32 a = reinterpret_cast<u32>(p);
    return !(a & 3) && a >= lo && a < hi && bytes <= hi - a;
}
template <class T> bool member(const T *p, const T *base, u32 count) {
    return SusamuneCollisionArrayMember(reinterpret_cast<u32>(p),
        reinterpret_cast<u32>(base), count, sizeof(T));
}
struct Pool {
    const TMapCollisionData &map;
    bool valid(u32 lo, u32 hi) const {
        return map.mCheckDataCount <= map.mCheckDataMax &&
            map.mCheckDataMax <= kTriangleCapacity &&
            map.mCheckListMax && map.mCheckListMax <= 1048576 &&
            map.mCheckListMoveRemaining < map.mCheckListMax &&
            map.mCheckListStaticCount <= map.mCheckListMoveRemaining + 1 &&
            map.mCheckListWarpCount <= map.mCheckListWarpMax && map.mCheckListWarpMax <= 65535 &&
            span(map.mCollisionTris,map.mCheckDataMax*sizeof(TBGCheckData),lo,hi) &&
            span(map.mCollisionLists,map.mCheckListMax*sizeof(TBGCheckList),lo,hi) &&
            (!map.mCheckListWarpMax || span(map.mCollisionListWarps,
                map.mCheckListWarpMax*sizeof(TBGCheckListWarp),lo,hi));
    }
    bool triangle(const TBGCheckData *p) const {
        return member(p,map.mCollisionTris,map.mCheckDataCount) && !(p->mFlags & 0x10);
    }
};
struct Projection {
    Mtx44 projection;
    Mtx view;
    bool init() {
        if (!GhostCamera::renderMatrices(view,projection)) return false;
        for (u32 r=0;r<4;++r) for (u32 c=0;c<4;++c) {
            if (!finite(projection[r][c]) || (r<3 && !finite(view[r][c]))) return false;
        }
        if (!(projection[0][0]>0 && projection[1][1]>0 &&
              projection[2][2]<0 && projection[2][3]<0 && projection[3][2]==-1)) return false;
        // A small depth bias keeps coplanar collision above the retail surface.
        projection[2][2] += 0.00001f;
        return true;
    }
    bool visible(const TBGCheckData &tri) const {
        unsigned reject=63;
        for (u32 i=0;i<3;++i) {
            const TVec3f &p=tri.mVertices[i];
            if (!finite(p.x) || !finite(p.y) || !finite(p.z)) return false;
            f32 v[3];
            for (u32 r=0;r<3;++r) v[r]=view[r][0]*p.x+view[r][1]*p.y+view[r][2]*p.z+view[r][3];
            reject &= SusamuneCollisionOutcode(projection[0][0]*v[0]+projection[0][2]*v[2],
                projection[1][1]*v[1]+projection[1][2]*v[2],
                projection[2][2]*v[2]+projection[2][3],-v[2]);
        }
        return !reject;
    }
};
struct Batch {
    u32 remaining, triangles;
    void triangle(const TBGCheckData &tri, u32 color) {
        if (!triangles) {
            const u32 count = remaining > 4096 ? 4096 : remaining;
            GXBegin(GX_TRIANGLES,GX_VTXFMT0,count*3);
            remaining -= count;
            triangles = count;
        }
        --triangles;
        volatile f32 *fifo=reinterpret_cast<volatile f32 *>(0xCC008000);
        for (u32 i=0;i<3;++i) {
            const TVec3f &vertex=tri.mVertices[i];
            *fifo=vertex.x; *fifo=vertex.y; *fifo=vertex.z;
            *reinterpret_cast<volatile u32 *>(0xCC008000)=color;
        }
    }
};
unsigned plane(const TBGCheckData &tri) {
    return SusamuneCollisionPlane(tri.mType,tri.mNormal.y);
}
void collect(const Pool &pool, const TBGCheckData *tri) {
    if (!member(tri,pool.map.mCollisionTris,pool.map.mCheckDataCount)) {
        sLimit=true;
        return;
    }
    if (tri->mFlags & 0x10) return;
    const u32 index=tri-pool.map.mCollisionTris;
    activeWord(index>>5) |= 1u<<(index&31);
}
}
void beginFrame() {
    sDrawn=sFloorValid=sLimit=false;
    GameWireframe::beginFrame();
}
bool drawWorld() {
    sDrawn=sFloorValid=sLimit=false;
    const u8 mode=gSettings.get(SETTING_COLLISION_VIEWER);
    const TMarDirector *director=RetailInput::stageDirector();
    if (!mode || mode>3 || !director || !director->_260 || director->mCurState<TMarDirector::STATE_GAME_STARTING) return false;
    const JKRHeap *heap=gpApplication.mCurrentHeap;
    if (!span(heap,sizeof(*heap),0x80000000u,0x81800000u)) return false;
    const u32 lo=reinterpret_cast<u32>(heap), hi=reinterpret_cast<u32>(heap->mEnd);
    if (hi<=lo || hi>0x81800000u || !span(gpMarioOriginal,sizeof(*gpMarioOriginal),lo,hi) ||
        !span(gpMapCollisionData,sizeof(*gpMapCollisionData),lo,hi)) return false;
    const Pool pool={*gpMapCollisionData};
    Projection projection;
    if (!pool.valid(lo,hi) || !projection.init()) return false;
    const TMapCollisionData &map=pool.map;
    const TBGCheckData *floor=gpMarioOriginal->mFloorTriangle;
    const u32 words=(map.mCheckDataCount+31)/32;
#if !IS_EMULATOR
    if (words > kRetainedWords && !TransferLease::sharedMap()) return false;
#endif
    // CPU-only deduplication is rebuilt every draw; physical bank swaps never move it.
    memset(sActiveTriangles,0,(words < kRetainedWords ? words : kRetainedWords)*sizeof(u32));
    if (words > kRetainedWords)
        memset(spillTriangles(),0,(words-kRetainedWords)*sizeof(u32));
    // Retail keeps static nodes, rebuilds the moving tail, and compacts warps.
    // Their active allocation ranges avoid grid duplicates and stale owners.
    for (u32 i=0;i<map.mCheckListStaticCount;++i)
        collect(pool,map.mCollisionLists[i].mColTriangle);
    for (u32 i=map.mCheckListMoveRemaining+1;i<map.mCheckListMax;++i)
        collect(pool,map.mCollisionLists[i].mColTriangle);
    for (u32 i=0;i<map.mCheckListWarpCount;++i)
        collect(pool,map.mCollisionListWarps[i].mColTriangle);
    if (pool.triangle(floor)) {
        const u32 index=floor-map.mCollisionTris, mask=1u<<(index&31);
        sFloorValid=(activeWord(index>>5)&mask)!=0;
        activeWord(index>>5) &= ~mask;
    }
    u32 visible=0;
    for (u32 word=0;word<words;++word) {
        u32 bits=activeWord(word);
        while (bits) {
            const u32 bit=31-__builtin_clz(bits), mask=1u<<bit;
            bits &= ~mask;
            const TBGCheckData &tri=map.mCollisionTris[word*32+bit];
            if (mode==1 || !finite(tri.mNormal.y) || !projection.visible(tri))
                activeWord(word) &= ~mask;
            else ++visible;
        }
    }
    const bool floorVisible=sFloorValid && projection.visible(*floor);
    if (sFloorValid) {
        sFloorType=floor->mType; sFloorValue=floor->mValue; sFloorFlags=floor->mFlags;
    }
    sDrawn=true;
    if (!visible && !floorVisible) return false;
    // Keep the world viewport's field jitter and clipping rectangle.
    GXSetClipMode(GX_CLIP_ENABLE);
    GXSetProjection(projection.projection,GX_PERSPECTIVE);
    GXLoadPosMtxImm(projection.view,GX_PNMTX0);
    GXSetCurrentMtx(GX_PNMTX0);
    GXClearVtxDesc();
    GXSetVtxDesc(GX_VA_POS,GX_DIRECT); GXSetVtxDesc(GX_VA_CLR0,GX_DIRECT);
    GXSetVtxAttrFmt(GX_VTXFMT0,GX_VA_POS,GX_POS_XYZ,GX_F32,0);
    GXSetVtxAttrFmt(GX_VTXFMT0,GX_VA_CLR0,GX_CLR_RGBA,GX_RGBA8,0);
    GXSetNumChans(1); GXSetNumTexGens(0); GXSetNumIndStages(0); GXSetNumTevStages(1);
    GXSetTevDirect(GX_TEVSTAGE0); GXSetTevOp(GX_TEVSTAGE0,GX_PASSCLR);
    GXSetTevOrder(GX_TEVSTAGE0,0xff,GX_TEXMAP_NULL,GX_COLOR0A0);
    GXSetChanCtrl(GX_COLOR0A0,GX_FALSE,GX_SRC_REG,GX_SRC_VTX,0,GX_DF_NONE,GX_AF_NONE);
    GXSetBlendMode(GX_BM_NONE,GX_BL_ONE,GX_BL_ZERO,GX_LO_COPY);
    GXSetAlphaCompare(GX_ALWAYS,0,GX_AOP_AND,GX_ALWAYS,0);
    GXSetColorUpdate(GX_TRUE);
    GXSetAlphaUpdate(GX_FALSE);
    GXSetZCompLoc(GX_TRUE);
    GXSetZMode(GX_TRUE,GX_LEQUAL,GX_TRUE);
    GXSetCullMode(GX_CULL_NONE);
    GXSetFog(GX_FOG_NONE,0,1,0,1,GXColor{0,0,0,0});
    Batch batch={visible+static_cast<u32>(floorVisible),0};
    for (u32 word=0;word<words;++word) {
        u32 bits=activeWord(word);
        while (bits) {
            const u32 bit=31-__builtin_clz(bits);
            bits &= ~(1u<<bit);
            const TBGCheckData &tri=map.mCollisionTris[word*32+bit];
            batch.triangle(tri,kCollisionColors[SusamuneCollisionColorFor(tri.mType,plane(tri))]);
        }
    }
    if (floorVisible) batch.triangle(*floor,kCollisionColors[SUSAMUNE_COLLISION_CURRENT]);
    return true;
}
void draw(Menu *menu) {
    if (!menu || !sDrawn || !gSettings.get(SETTING_COLLISION_VIEWER)) return;
    char text[64];
    if (sFloorValid) snprintf(text,sizeof(text),kCollisionFloorFormat,sFloorType,sFloorValue,sFloorFlags);
    menu->drawText(sFloorValid ? text : kCollisionNoFloor,18,276,14,14,JUtility::TColor(255,230,60,255));
    if (sLimit) menu->drawText(kCollisionLimit,18,294,12,12,JUtility::TColor(255,230,60,255));
    if (!gSettings.getBool(SETTING_COLLISION_LEGEND)) return;
    for (unsigned i=0;i<sizeof(kCollisionColors)/sizeof(kCollisionColors[0]);++i) {
        const int x=18+(i/5)*205, y=170+(i%5)*18;
        const u32 color=kCollisionColors[i];
        menu->fillBox(x,y,10,10,JUtility::TColor(color>>24,color>>16,color>>8,255));
        menu->drawText(kCollisionLabels[i],x+15,y,12,12,JUtility::TColor(255,255,255,255));
    }
}
}
