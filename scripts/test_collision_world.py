"""Exercise production collision traversal, rejection and GX setup without a game."""
import ctypes as C
import _ctypes
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
class CollisionWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-collision-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT/"src/collision_viewer.cpp").read_text()
        source = re.sub(r"^#include.*\n", "", source, flags=re.M)
        source = re.sub(r"static_assert\([\s\S]*?;\n", "", source)
        # Only host pointer width differs; the fixture arena stays in MEM1's range.
        source = source.replace("reinterpret_cast<u32>", "reinterpret_cast<unsigned long long>")
        source = source.replace("*reinterpret_cast<volatile u32 *>(0xCC008000)=color;", "recordColor(color);")
        constants = sorted(set(re.findall(r"\bGX_[A-Z0-9_]+\b", source)))
        calls = sorted(set(re.findall(r"\b(GX\w+)\(", source)))
        prelude = r'''
using u8=unsigned char;using u16=unsigned short;using s16=short;
using u32=unsigned int;using f32=float;using Mtx=float[3][4];using Mtx44=float[4][4];
struct GXColor {u8 r,g,b,a;};
extern "C" { int _fltused=0;
void *memset(void *p,int v,unsigned long long n){u8 *b=(u8*)p;while(n--)*b++=v;return p;}
void *memcpy(void *p,const void *q,unsigned long long n){u8 *b=(u8*)p;const u8 *a=(const u8*)q;while(n--)*b++=*a++;return p;}
int snprintf(char *p,unsigned long long,const char*,...){p[0]=0;return 0;}}
struct TVec3f{float x,y,z;};
struct TBGCheckData {u16 mType; s16 mValue;u16 mFlags;u8 mSoundID;
float mMinHeight,mMaxHeight;TVec3f mVertices[3],mNormal;float mProjectionFactor;void *mOwner;};
struct TBGCheckList {void *vptr;TBGCheckList *mNextTriangle;TBGCheckData *mColTriangle;};
struct TBGCheckListWarp:TBGCheckList{TBGCheckList *mPreNode;s16 mCellX,mCellZ;};
struct TBGCheckListRoot{TBGCheckList mCheckList[3];};
struct TMapCollisionData{
float mAreaSizeX,mAreaSizeZ;u32 mBlockXCount,mBlockZCount,mBlockTotalCount;
TBGCheckListRoot *mStaticCollisionRoot,*mMoveCollisionRoot;
u32 mCheckDataMax,mCheckListMax,mCheckListWarpMax;
TBGCheckData *mCollisionTris;TBGCheckList *mCollisionLists;TBGCheckListWarp *mCollisionListWarps;
u32 mCheckDataCount,mCheckListStaticCount,mCheckListMoveRemaining;u16 mCheckListWarpCount;
};
struct JKRHeap{void *mEnd;};
struct Mario {TBGCheckData *mFloorTriangle;};
struct App {JKRHeap *mCurrentHeap;}gpApplication;
TMapCollisionData *gpMapCollisionData;Mario *gpMarioOriginal;
struct TMarDirector{enum{STATE_GAME_STARTING=2};int _260,mCurState;}director;
namespace RetailInput {const TMarDirector *stageDirector(){return &director;}}
enum{SETTING_COLLISION_VIEWER,SETTING_COLLISION_LEGEND};
struct Settings {u8 mode,legend;u8 get(int id){return id?legend:mode;}bool getBool(int id){return get(id)!=0;}}gSettings;
namespace JUtility{struct TColor{TColor(u8,u8,u8,u8){}};}
int textCount,boxCount;
struct Menu {void drawText(const char*,int,int,int,int,JUtility::TColor){++textCount;}
 void fillBox(int,int,int,int,JUtility::TColor){++boxCount;}};
namespace GhostCamera {bool matricesReady=true;Mtx view;Mtx44 projection;
bool renderMatrices(Mtx v,Mtx44 p){memcpy(v,view,sizeof(view));memcpy(p,projection,sizeof(projection));return matricesReady;}}
namespace GameWireframe {void beginFrame(){}}
namespace TransferLease {bool ready=true;bool sharedMap(){return ready;}}
int SMSGetGameRenderWidth(){return 640;}int SMSGetGameRenderHeight(){return 448;}
int submissions,viewportHeight,viewportWrites,scissorWrites,zEnabled,zCompare,zWrite,lastCount,batchCount,vertexCount;u32 colors[10000];
#include "susamune/collision_geometry.h"
#include "susamune/mem2_map.h"
'''
        prelude += "\nenum {"+",".join(constants)+"};\n"
        prelude += r'''
void GXBegin(int,int,int count){
 if(count<=0 || count%3 || count>12288)__builtin_trap();lastCount=count;++batchCount;}
void recordColor(u32 color){if(++vertexCount%3==0)colors[submissions++]=color;}
void GXSetViewport(float,float,float,float h,float,float){viewportHeight=(int)h;++viewportWrites;}
void GXSetScissor(...){++scissorWrites;}
void GXSetZMode(int e,int c,int w){zEnabled=e;zCompare=c;zWrite=w;}
'''
        for name in calls:
            if name not in ("GXBegin","GXSetViewport","GXSetScissor","GXSetZMode"):
                prelude += "void "+name+"(...){}\n"
        exports = r'''
#define API extern "C" __declspec(dllexport)
API void reset(unsigned n){
 memset((void*)0x81000000,0,0x700000);memset(colors,0,sizeof(colors));
 gpApplication.mCurrentHeap=(JKRHeap*)0x81000000;
 gpApplication.mCurrentHeap->mEnd=(void*)0x81700000;
 gpMapCollisionData=(TMapCollisionData*)0x81000100;gpMarioOriginal=(Mario*)0x81000500;
 TMapCollisionData &m=*gpMapCollisionData;
 m.mBlockXCount=32;m.mBlockZCount=8;m.mBlockTotalCount=256;
 m.mStaticCollisionRoot=(TBGCheckListRoot*)0x81010000;
 m.mMoveCollisionRoot=(TBGCheckListRoot*)0x81018000;
 m.mCollisionTris=(TBGCheckData*)0x81100000;m.mCheckDataMax=10000;m.mCheckDataCount=n;
 m.mCollisionLists=(TBGCheckList*)0x81300000;m.mCheckListMax=10001;
 m.mCheckListStaticCount=n;m.mCheckListMoveRemaining=10000;
 m.mCollisionListWarps=(TBGCheckListWarp*)0x81400000;m.mCheckListWarpMax=256;
 m.mStaticCollisionRoot[255].mCheckList[0].mNextTriangle=n?m.mCollisionLists:nullptr;
 for(unsigned i=0;i<n;++i){
  TBGCheckData &t=m.mCollisionTris[i];t.mVertices[0]={-1,-1,-100};
  t.mVertices[1]={1,-1,-100};t.mVertices[2]={0,1,-100};t.mNormal={0,1,0};
  m.mCollisionLists[i].mColTriangle=&t;
  m.mCollisionLists[i].mNextTriangle=i+1<n?&m.mCollisionLists[i+1]:nullptr;
 }
 director={1,4};gSettings={2,1};submissions=viewportWrites=scissorWrites=zEnabled=zCompare=zWrite=textCount=boxCount=lastCount=batchCount=vertexCount=0;viewportHeight=448;
 TransferLease::ready=true;
 CollisionViewer::beginFrame();
 memset(GhostCamera::view,0,sizeof(Mtx));memset(GhostCamera::projection,0,sizeof(Mtx44));
 for(int i=0;i<3;++i)GhostCamera::view[i][i]=1;
 GhostCamera::projection[0][0]=GhostCamera::projection[1][1]=1;
 GhostCamera::projection[2][2]=-1.0f/9999;GhostCamera::projection[2][3]=-10000.0f/9999;
 GhostCamera::projection[3][2]=-1;GhostCamera::matricesReady=true;
}
API void change(unsigned kind){
 TMapCollisionData &m=*gpMapCollisionData;TBGCheckData &t=m.mCollisionTris[0];
 if(kind==0){gSettings.mode=0;}
 if(kind==1){m.mStaticCollisionRoot[255].mCheckList[0].mNextTriangle=(TBGCheckList*)((u8*)m.mCollisionLists+4);}
 if(kind==2){m.mCollisionLists[0].mColTriangle=(TBGCheckData*)((u8*)m.mCollisionTris+4);}
 if(kind==3){m.mCheckDataCount=10001;}
 if(kind==4){m.mCollisionLists[0].mNextTriangle=m.mCollisionLists;}
 if(kind==5){m.mCollisionLists[0].mColTriangle=nullptr;}
 if(kind==6){t.mFlags=0x10;}
 if(kind==7){m.mCheckListStaticCount=0;m.mStaticCollisionRoot[255].mCheckList[0].mNextTriangle=nullptr;
  TBGCheckList *node=&m.mCollisionLists[10000];node->mColTriangle=&t;
  m.mMoveCollisionRoot[255].mCheckList[0].mNextTriangle=node;m.mCheckListMoveRemaining=9999;
  gpMarioOriginal->mFloorTriangle=&t;t.mOwner=(void*)0xdeadbeef;}
 if(kind==8){m.mCheckListStaticCount=0;m.mCheckListWarpCount=1;
  m.mCollisionListWarps[0].mColTriangle=&t;
  m.mStaticCollisionRoot[255].mCheckList[0].mNextTriangle=&m.mCollisionListWarps[0];}
 if(kind==9){m.mCheckListStaticCount=0;}
 if(kind==10){for(auto &v:t.mVertices)v.z=100;}
 if(kind==11){t.mVertices[0].z=0;t.mVertices[1].z=-2;t.mVertices[2].z=-2;}
 if(kind==12){GhostCamera::matricesReady=false;}
 if(kind==13){gSettings.legend=0;}
 if(kind==14){gpMarioOriginal->mFloorTriangle=&t;gSettings.mode=1;}
 if(kind==15){director._260=0;}
 if(kind==16){for(auto &v:t.mVertices)v.x+=10000;}
 if(kind==17){m.mCollisionTris=(TBGCheckData*)0x816ffffc;}
 if(kind==18){t.mType=0x8002;}
 if(kind==19){m.mStaticCollisionRoot[255].mCheckList[2].mNextTriangle=m.mStaticCollisionRoot[255].mCheckList[0].mNextTriangle;
  m.mStaticCollisionRoot[255].mCheckList[0].mNextTriangle=nullptr;t.mNormal.y=0;}
 if(kind==20){*(u32*)&t.mVertices[0].x=0x7fc00000;}
 if(kind==21){*(u32*)&t.mVertices[0].x=0x7f800000;}
 if(kind==22){m.mBlockTotalCount=257;}
 if(kind==23){gSettings.mode=3;}
 if(kind==24){for(unsigned i=0;i<m.mCheckListStaticCount;++i)m.mCollisionLists[i].mColTriangle=&m.mCollisionTris[(i&1)?256:0];}
 if(kind==25){m.mCheckListStaticCount=0;m.mCheckListWarpCount=0;m.mCheckListMoveRemaining=m.mCheckListMax-1;}
 if(kind==26){m.mCheckListStaticCount=m.mCheckListMoveRemaining+2;}
 if(kind==27){m.mCheckListWarpCount=m.mCheckListWarpMax+1;}
 if(kind==28){m.mCheckListMoveRemaining=m.mCheckListMax;}
 if(kind==29){m.mCheckListStaticCount=0;m.mCheckListWarpCount=0;
  m.mCollisionListWarps[0].mColTriangle=&t;m.mCollisionLists[10000].mColTriangle=&t;
  gpMarioOriginal->mFloorTriangle=&t;}
 if(kind==30){m.mCheckListWarpCount=1;m.mCollisionListWarps[0].mColTriangle=&t;
  m.mCollisionLists[10000].mColTriangle=&t;m.mCheckListMoveRemaining=9999;}
}
API unsigned run(){
 CollisionViewer::drawWorld();
 Menu menu;CollisionViewer::draw(&menu);
 return submissions | (CollisionViewer::sLimit?0x10000:0) |
 (CollisionViewer::sFloorValid?0x20000:0);
}
API void highPool(unsigned flags){
 reset(1);
 gpApplication.mCurrentHeap=(JKRHeap*)0x80000000;
 gpApplication.mCurrentHeap->mEnd=(void*)0x81700000;
 TMapCollisionData &m=*gpMapCollisionData;
 m.mCollisionTris=(TBGCheckData*)0x80100000;
 m.mCheckDataCount=m.mCheckDataMax=CollisionViewer::kTriangleCapacity;
 m.mCheckListStaticCount=(flags&2)?0:4;
 const unsigned indices[]={CollisionViewer::kRetainedWords*32-1,
  CollisionViewer::kRetainedWords*32,CollisionViewer::kTriangleCapacity-1,
  CollisionViewer::kTriangleCapacity-1};
 for(unsigned i=0;i<4;++i){
  TBGCheckData &t=m.mCollisionTris[indices[i]];t={};
  t.mVertices[0]={-1,-1,-100};t.mVertices[1]={1,-1,-100};
  t.mVertices[2]={0,1,-100};t.mNormal={0,1,0};
  m.mCollisionLists[i].mColTriangle=&t;
 }
 if(flags&1)gpMarioOriginal->mFloorTriangle=&m.mCollisionTris[CollisionViewer::kTriangleCapacity-1];
 TransferLease::ready=!(flags&4);
}
API void admission(int ready){TransferLease::ready=ready;}
API unsigned retainedBytes(){return sizeof(CollisionViewer::sActiveTriangles);}
API unsigned spillBase(){return SUSAMUNE_COLLISION_BITS_PPC_BASE;}
API unsigned spillBytes(){return SUSAMUNE_COLLISION_BITS_SIZE;}
API unsigned color(unsigned i){return colors[i];}
API unsigned rgb(unsigned type,unsigned plane){return CollisionViewer::kCollisionColors[SusamuneCollisionColorFor(type,plane)];}
API unsigned plane(unsigned type,float normalY){return SusamuneCollisionPlane(type,normalY);}
API int hud(int boxes){return boxes?boxCount:textCount;}
API int depth(){return zEnabled==GX_TRUE && zCompare==GX_LEQUAL && zWrite==GX_TRUE;}
API int batches(){return batchCount;}
API int height(){return viewportHeight;}
API int viewportChanges(){return viewportWrites+scissorWrites;}
API unsigned outcode(float x,float y,float z,float w){return SusamuneCollisionOutcode(x,y,z,w);}
'''
        folder = Path(cls.temp.name)
        (folder/"fixture.cpp").write_text(prelude+source+exports)
        result = subprocess.run([str(ROOT/"toolchain/clang++.exe"),
            "--target=x86_64-pc-windows-msvc","-shared","-O1","-fno-builtin","-ffast-math",
            "-nostdlib","-fuse-ld=lld","-Xlinker","/noentry","-I",str(ROOT/"include"),
            str(folder/"fixture.cpp"),"-o",str(folder/"fixture.dll")],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        cls.dll=C.CDLL(str(folder/"fixture.dll"))
        cls.addClassCleanup(lambda:_ctypes.FreeLibrary(cls.dll._handle))
        cls.dll.run.restype=cls.dll.color.restype=cls.dll.rgb.restype=C.c_uint
        cls.dll.outcode.argtypes=[C.c_float]*4
        cls.dll.plane.argtypes=[C.c_uint,C.c_float]
        kernel=C.WinDLL("kernel32",use_last_error=True)
        kernel.VirtualAlloc.argtypes=[C.c_void_p,C.c_size_t,C.c_ulong,C.c_ulong]
        kernel.VirtualAlloc.restype=C.c_void_p
        kernel.VirtualFree.argtypes=[C.c_void_p,C.c_size_t,C.c_ulong]
        for address,size in ((0x80000000,0x1700000),(0x91cf0000,0x20000),(0xcc000000,0x10000)):
            p=kernel.VirtualAlloc(address,size,0x3000,4)
            if p != address: raise RuntimeError("fixture memory unavailable")
            cls.addClassCleanup(lambda a=p:kernel.VirtualFree(a,0,0x8000))

    def setUp(self): self.dll.reset(1)
    def test_visible_world_exceeds_old_radius_and_96_limit(self):
        self.dll.reset(300)
        before=C.string_at(0x81000000,0x700000)
        self.assertEqual(self.dll.run(),300)
        self.assertEqual(C.string_at(0x81000000,0x700000),before)
        self.assertTrue(self.dll.depth())
        self.assertEqual(self.dll.height(),448)
        self.assertEqual(self.dll.viewportChanges(),0)
        self.assertEqual(self.dll.batches(),1)

    def test_moving_and_warp_activity_without_owner_dereference(self):
        self.dll.change(7)
        self.assertEqual(self.dll.run(),0x20001)
        self.assertEqual(self.dll.color(0),0xffe63cff)
        self.dll.reset(1);self.dll.change(8)
        self.assertEqual(self.dll.run(),1)
        self.dll.reset(1);self.dll.change(9)
        self.assertEqual(self.dll.run(),0)

    def test_invalid_spans_and_non_active_triangles_are_rejected(self):
        for change,expected in ((1,1),(2,0x10000),(3,0),(5,0x10000),(6,0),(12,0),(15,0),(17,0),(20,0),(21,0),(22,1),(26,0),(27,0),(28,0)):
            self.dll.reset(1);self.dll.change(change)
            self.assertEqual(self.dll.run(),expected,change)

    def test_exact_deduplication_and_batches_cover_large_active_pools(self):
        self.dll.change(4)
        self.assertEqual(self.dll.run(),1)  # List links are not followed.
        self.dll.reset(9000)
        self.assertEqual(self.dll.run(),9000)
        self.assertEqual(self.dll.batches(),3)
        self.dll.reset(9000);self.dll.change(24)
        self.assertEqual(self.dll.run(),2)
        self.assertEqual(self.dll.batches(),1)
        self.dll.reset(9000);self.dll.change(25)
        self.assertEqual(self.dll.run(),0)

    def test_retired_pool_tails_and_cross_pool_duplicates(self):
        self.dll.change(29)
        self.assertEqual(self.dll.run(),0)
        self.dll.reset(1);self.dll.change(30)
        self.assertEqual(self.dll.run(),1)
        self.assertEqual(self.dll.batches(),1)

    def test_camera_clipping_and_no_projection_division(self):
        for change,expected in ((10,0),(11,1),(16,0)):
            self.dll.reset(1);self.dll.change(change)
            self.assertEqual(self.dll.run(),expected)
        self.assertEqual(self.dll.outcode(0,0,-1,1),0)
        self.assertEqual(self.dll.outcode(0,0,-2,1),16)
        self.assertEqual(self.dll.outcode(0,0,1,1),32)

    def test_retail_collision_classes_and_plane_priority(self):
        for type_ in (1,0x4001,0x8001,0xc001):
            self.assertEqual(self.dll.rgb(type_,0),0x3030bfff)
        for type_ in (2,0x8002):
            self.assertEqual(self.dll.rgb(type_,0),0x60c8ffff)
        self.assertEqual(self.dll.rgb(0x4002,0),0x3078ffff)
        for type_ in (3,0x8003):self.assertEqual(self.dll.rgb(type_,0),0x4848ffff)
        for type_ in (0xc,0x800c,0xa00c):self.assertEqual(self.dll.rgb(type_,0),0x9870ffff)
        for type_ in (4,0x4004,0x8004,0xc004,0x500):self.assertEqual(self.dll.rgb(type_,0),0x20a8bfff)
        for type_ in (0x100,0x101,0x102,0x103,0x104,0x105,0x4104):self.assertEqual(self.dll.rgb(type_,0),0x40e8ffff)
        for type_ in (0x701,0x4701,0x8701,0xc701):self.assertEqual(self.dll.rgb(type_,0),0xe8b048ff)
        for type_ in (0x200,0x201,0x202,0x203):self.assertEqual(self.dll.rgb(type_,0),0xc868e8ff)
        self.assertEqual(self.dll.rgb(0x4006,0),0x3078ffff)
        self.assertEqual(self.dll.rgb(0x600,2),0x888888ff)
        self.assertEqual(self.dll.rgb(0x800,0),0x888888ff)
        self.assertEqual(self.dll.rgb(0,2),0x30d050ff)
        self.assertEqual(self.dll.rgb(0,1),0xf04040ff)
        self.dll.change(18);self.assertEqual(self.dll.run(),1)
        self.assertEqual(self.dll.color(0),0x60c8ffff)

    def test_plane_thresholds_and_forced_floor_match_retail(self):
        for normal,expected in ((0.20001,0),(0.2,2),(0,2),(-0.2,2),(-0.20001,1)):
            self.assertEqual(self.dll.plane(0,normal),expected)
        self.assertEqual(self.dll.plane(0x801,-1),0)
        self.assertEqual(self.dll.plane(0x4801,-1),1)

    def test_off_floor_and_legend_toggle(self):
        self.dll.change(0);self.assertEqual(self.dll.run(),0)
        self.assertEqual(self.dll.hud(0),0)
        self.dll.reset(1);self.dll.change(14)
        self.assertEqual(self.dll.run(),0x20001)
        self.assertEqual(self.dll.hud(1),13)
        self.dll.reset(1);self.dll.change(13)
        self.dll.run();self.assertEqual(self.dll.hud(1),0)
        self.assertEqual(self.dll.hud(0),1)

    def test_render_wireframe_mode_keeps_coloured_collision_fill(self):
        self.dll.reset(300);self.dll.change(23)
        self.assertEqual(self.dll.run(),300)
        self.assertTrue(self.dll.depth())
        self.assertEqual(self.dll.batches(),1)

    def test_split_boundary_full_capacity_and_adjacent_owners(self):
        base=self.dll.spillBase() & 0xffffffff
        size=self.dll.spillBytes()
        self.assertEqual((base,size,self.dll.retainedBytes()),(0x91cfd100,7936,8448))
        C.memset(base-32,0xa7,size+64)
        self.dll.highPool(1)
        self.assertEqual(self.dll.run(),0x20003)
        self.assertEqual(self.dll.color(2),0xffe63cff)
        self.assertEqual(C.string_at(base-32,32),bytes([0xa7])*32)
        self.assertEqual(C.string_at(base+size,32),bytes([0xa7])*32)
        self.dll.highPool(2)
        self.assertEqual(self.dll.run(),0)
        self.assertEqual(C.string_at(base,size),bytes(size))

    def test_large_pool_requires_admission_and_small_pool_still_works(self):
        base=self.dll.spillBase() & 0xffffffff
        size=self.dll.spillBytes()
        C.memset(base,0xa7,size)
        self.dll.highPool(4)
        self.assertEqual(self.dll.run(),0)
        self.assertEqual(C.string_at(base,size),bytes([0xa7])*size)
        self.dll.admission(True)
        self.assertEqual(self.dll.run(),3)
        self.dll.reset(1);self.dll.admission(False)
        self.assertEqual(self.dll.run(),1)

if __name__=="__main__": unittest.main()
