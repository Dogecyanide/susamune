#include "susamune/menu_theme_assets.hxx"
#include "susamune/menu_native_icon.hxx"
#include "susamune/ghost_storage.h"
#include "susamune/mem2_map.h"
#include "susamune/retail_input.hxx"
#include "susamune/susamune_cfg.h"
#include <Dolphin/OS.h>
#include <Dolphin/mem.h>
#include <Dolphin/printf.h>
#include <Dolphin/string.h>
#include <JSystem/JKernel/JKRArchivePri.hxx>
#include <JSystem/JKernel/JKRHeap.hxx>
#include <JSystem/JUtility/JUTTexture.hxx>
#include <SMS/System/Application.hxx>
#include <SMS/System/MarDirector.hxx>

extern void *menuGuideVtable[] asm("__vt__6TGuide");
extern void retailMenuGuideLoad(void *, JSUMemoryInputStream &)
    asm("load__6TGuideFR20JSUMemoryInputStream");
extern u8 menuShineStage(u8) asm("SMS_getShineStage__FUc");

namespace {
const u32 kBufferSize = 0x64000;
const u32 kGuideOffset = 0x5b000;
const u32 kOptionOffset = 0x48000;
const u32 kGuideMagic = 0x4d544731;
const u32 kOptionMagic = 0x4d544f32;
const unsigned kGuideCount = 11;

struct Cache {
    u32 magic, bytes;
    u16 offset[kGuideCount], size[kGuideCount];
    u32 reserved[11];
};
static_assert(sizeof(Cache) == 96, "native texture headers must stay aligned");
static_assert(36128 + sizeof(Cache) <= kBufferSize - kGuideOffset,
              "native guide assets exceed the retail archive suffix");
static_assert(MenuNativeIcon::ControllerBytes + 3776 + MenuNativeIcon::BooBytes +
              sizeof(Cache) <= SUSAMUNE_MENU_ASSET_BACKUP_SIZE,
              "native option backup exceeds presentation scratch");
static_assert(MenuNativeIcon::WorkspaceBytes <= kGuideOffset - kOptionOffset,
              "native icon extraction exceeds the existing upload gap");
static_assert(kOptionOffset + SUSAMUNE_MENU_ASSET_BACKUP_SIZE <= kGuideOffset,
              "option GPU upload overlaps the persistent guide cache");

bool sOptionReady;
bool sBooAttempted;

bool range(u32 offset, u32 size, u32 limit) {
    return offset <= limit && size <= limit - offset;
}

bool inStage(const void *pointer, u32 bytes) {
    JKRHeap *heap = gpApplication.mCurrentHeap;
    const u32 p = reinterpret_cast<u32>(pointer);
    return heap && !(p & 31) && p >= 0x80000000u && p <= 0x81800000u &&
        range(p, bytes, 0x81800000u) &&
        p >= reinterpret_cast<u32>(heap->mStart) &&
        range(p, bytes, reinterpret_cast<u32>(heap->mEnd));
}

u8 *gameBuffer(TMarDirector *director) {
    return director && inStage(director->mGame6Data, kBufferSize)
        ? reinterpret_cast<u8 *>(director->mGame6Data) : nullptr;
}

struct Archive {
    const u8 *base;
    u32 size, data, entries, count, strings, stringBytes;
};

// Include every file extent, not just RARC's claimed total, before borrowing slack.
bool openArchive(const u8 *base, u32 capacity, Archive &out) {
    if (!base || capacity < 0x40) return false;
    const u32 *h = reinterpret_cast<const u32 *>(base);
    if (h[0] != 0x52415243 || h[2] != 0x20 ||
        h[1] < 0x40 || h[1] > capacity || !range(0x20, h[3], h[1]))
        return false;
    const u32 data = 0x20 + h[3];
    if (!range(data, h[4], h[1]) || data < 0x40 ||
        !h[8] || h[8] > 1024 || h[10] > 4096 ||
        !range(0x20, h[9], data) || !range(0x20 + h[9], h[8] * 16, data) ||
        !range(0x20, h[11], data) || !range(0x20 + h[11], h[10] * 20, data) ||
        !range(0x20, h[13], data) || !range(0x20 + h[13], h[12], data) ||
        ((h[9] | h[11] | data) & 3)) return false;
    out = {base, h[1], data, 0x20 + h[11], h[10], 0x20 + h[13], h[12]};
    for (u32 i = 0; i < out.count; ++i) {
        const u32 *f = reinterpret_cast<const u32 *>(base + out.entries + i * 20);
        if ((f[1] & 0xffffff) >= out.stringBytes) return false;
        if (!(f[1] & 0x02000000) && !range(f[2], f[3], h[4])) return false;
    }
    return true;
}

const u8 *find(const Archive &archive, const char *name, u32 &bytes) {
    const u32 length = strlen(name) + 1;
    for (u32 i = 0; i < archive.count; ++i) {
        const u32 *f = reinterpret_cast<const u32 *>(
            archive.base + archive.entries + i * 20);
        const u32 offset = f[1] & 0xffffff;
        // These native BTIs are uncompressed members; never decompress on the draw path.
        if ((f[1] & 0x06000000) || !range(offset, length, archive.stringBytes) ||
            memcmp(archive.base + archive.strings + offset, name, length)) continue;
        bytes = f[3];
        return archive.base + archive.data + f[2];
    }
    return nullptr;
}

const ResTIMG *texture(const void *data, u32 bytes) {
    if (!data || bytes < sizeof(ResTIMG) || (reinterpret_cast<u32>(data) & 31))
        return nullptr;
    const ResTIMG *t = static_cast<const ResTIMG *>(data);
    if (!t->mWidth || !t->mHeight || t->mWidth > 1024 || t->mHeight > 1024)
        return nullptr;
    u32 bw = 4, bh = 4, blockBytes = 32;
    switch (t->mFormat) {
    case ResTIMG::I4: case ResTIMG::C4: case ResTIMG::CMPR: bw = bh = 8; break;
    case ResTIMG::I8: case ResTIMG::IA4: case ResTIMG::C8: bw = 8; break;
    case ResTIMG::RGBA32: blockBytes = 64; break;
    case ResTIMG::IA8: case ResTIMG::RGB565: case ResTIMG::RGB5A3:
    case ResTIMG::C14X2: break;
    default: return nullptr;
    }
    const u32 pixels = ((t->mWidth + bw - 1) / bw) *
        ((t->mHeight + bh - 1) / bh) * blockBytes;
    if (t->mTextureOffset < 32 || (t->mTextureOffset & 31) ||
        !range(t->mTextureOffset, pixels, bytes)) return nullptr;
    const bool indexed = t->mFormat == ResTIMG::C4 || t->mFormat == ResTIMG::C8 ||
        t->mFormat == ResTIMG::C14X2;
    if (indexed && !t->mHasPalette) return nullptr;
    if ((t->mFormat == ResTIMG::C4 && t->mPaletteColors > 16) ||
        (t->mFormat == ResTIMG::C8 && t->mPaletteColors > 256)) return nullptr;
    if (t->mHasPalette && (t->mPaletteOffset < 32 || (t->mPaletteOffset & 31) ||
        !t->mPaletteColors || t->mPaletteColors > 16384 || t->mPaletteFormat > 2 ||
        !range(t->mPaletteOffset, t->mPaletteColors * 2u, bytes))) return nullptr;
    return t;
}

const ResTIMG *cached(const Cache *cache, u32 capacity, u32 magic, unsigned index) {
    if (index >= kGuideCount || cache->magic != magic ||
        cache->bytes < sizeof(Cache) || cache->bytes > capacity ||
        cache->offset[index] < sizeof(Cache) ||
        !range(cache->offset[index], cache->size[index], cache->bytes)) return nullptr;
    return texture(reinterpret_cast<const u8 *>(cache) + cache->offset[index],
                   cache->size[index]);
}

bool append(Cache *cache, u32 capacity, unsigned index,
            const Archive &archive, const char *name) {
    u32 bytes = 0;
    const u8 *source = find(archive, name, bytes);
    if (!texture(source, bytes) || bytes > 65535 ||
        !range(cache->bytes, (bytes + 31) & ~31u, capacity)) return false;
    cache->offset[index] = cache->bytes;
    cache->size[index] = bytes;
    memcpy(reinterpret_cast<u8 *>(cache) + cache->bytes, source, bytes);
    cache->bytes += (bytes + 31) & ~31u;
    return true;
}

bool backupAvailable() {
#if IS_EMULATOR
    return true;
#else
    const volatile SusamuneCfg *cfg = SUSAMUNE_CFG_PPC_PTR;
    DCInvalidateRange((void *)cfg, 32);
    const u32 flags = SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION |
                      SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED;
    if (cfg->magic != SUSAMUNE_CFG_MAGIC || cfg->version != SUSAMUNE_CFG_VERSION ||
        (cfg->flags & flags) != flags) return false;
    volatile SusamuneGhostStorageMailbox *mailbox = SUSAMUNE_GHOST_STORAGE_PPC_PTR;
    DCInvalidateRange((void *)&mailbox->response, 32);
    return mailbox->response.responseMagic == SUSAMUNE_GHOST_STORAGE_MAGIC &&
        mailbox->response.protocolVersion == SUSAMUNE_GHOST_STORAGE_VERSION;
#endif
}

void captureOption() {
    if (sOptionReady || !backupAvailable()) return;
    JKRArchive *volume = JKRFileLoader::getVolume("option");
    if (!volume || volume->_3C != 1) return;
    // Archive's info block is the native header +0x20 in every retail region.
    if (volume->_44 < 0x80000020u) return;
    const u8 *base = reinterpret_cast<const u8 *>(volume->_44 - 0x20);
    if (!inStage(base, 64)) return;
    Archive archive;
    if (!openArchive(base, reinterpret_cast<u32>(gpApplication.mCurrentHeap->mEnd) -
                     reinterpret_cast<u32>(base), archive)) return;
    Cache *cache = reinterpret_cast<Cache *>(SUSAMUNE_MENU_ASSET_BACKUP_PPC_BASE);
    memset(cache, 0, sizeof(Cache));
    cache->bytes = sizeof(Cache);
    u32 controllerBytes = 0;
    const u8 *controller = find(archive, "option_control.bti", controllerBytes);
    if (!texture(controller, controllerBytes) ||
        !MenuNativeIcon::scaleController(controller, controllerBytes,
            reinterpret_cast<u8 *>(cache) + cache->bytes, MenuNativeIcon::ControllerBytes)) return;
    cache->offset[0] = cache->bytes;
    cache->size[0] = MenuNativeIcon::ControllerBytes;
    cache->bytes += MenuNativeIcon::ControllerBytes;
    if (!append(cache, SUSAMUNE_MENU_ASSET_BACKUP_SIZE, 1, archive, "option_sunglass.bti"))
        return;
    cache->magic = kOptionMagic;
    sOptionReady = true;
}

void loadGuide(void *guide, JSUMemoryInputStream &stream) {
    retailMenuGuideLoad(guide, stream);
    captureOption();
    u8 *buffer = gameBuffer(gpMarDirector);
    Archive archive;
    if (!buffer || !openArchive(buffer, kGuideOffset, archive)) return;
    Cache *cache = reinterpret_cast<Cache *>(buffer + kGuideOffset);
    memset(cache, 0, sizeof(Cache));
    cache->bytes = sizeof(Cache);
    static const char *const names[] = {
        "guide_back.bti", "guide_draw_shine.bti",
        "guide_draw_palmtree_1.bti", "guide_draw_palmtree_2.bti",
        "guide_draw_fish_1.bti", "guide_draw_fish_2.bti",
        "guide_cursor_1.bti", "guide_cursor_2.bti",
        "guide_draw_ship_1.bti", "guide_draw_ship_2.bti"
    };
    for (unsigned i = 0; i < 10; ++i)
        if (!append(cache, kBufferSize - kGuideOffset, i, archive, names[i])) return;
    char name[32];
    const unsigned stage = gpMarDirector->mAreaID <= 60
        ? menuShineStage(gpMarDirector->mAreaID) : 1;
    snprintf(name, sizeof(name), "guide_picture_%02u.bti", stage <= 12 ? stage : 1);
    if (!append(cache, kBufferSize - kGuideOffset, 10, archive, name)) return;
    cache->magic = kGuideMagic;
    DCFlushRange(cache, cache->bytes);
}
}

namespace MenuThemeAssets {
void service() {
    if (menuGuideVtable[4] == reinterpret_cast<void *>(&retailMenuGuideLoad)) {
        menuGuideVtable[4] = reinterpret_cast<void *>(&loadGuide);
        DCStoreRange(menuGuideVtable + 4, sizeof(void *));
    }
}

void prepare() {
    if (sBooAttempted || !sOptionReady) return;
    TMarDirector *director = RetailInput::stageDirector();
    if (!director || !director->_260 || !OSIsThreadTerminated(&gSetupThread) ||
        director->mCurState != TMarDirector::STATE_NORMAL || !backupAvailable()) return;
    u8 *buffer = gameBuffer(director);
    Archive archive;
    if (!buffer || !openArchive(buffer, kOptionOffset, archive)) return;
    Cache *backup = reinterpret_cast<Cache *>(SUSAMUNE_MENU_ASSET_BACKUP_PPC_BASE);
    if (!cached(backup, SUSAMUNE_MENU_ASSET_BACKUP_SIZE, kOptionMagic, 0) ||
        !cached(backup, SUSAMUNE_MENU_ASSET_BACKUP_SIZE, kOptionMagic, 1) ||
        !range(backup->bytes, MenuNativeIcon::BooBytes, SUSAMUNE_MENU_ASSET_BACKUP_SIZE)) return;
    sBooAttempted = true;
    // DVD DMA and decoding borrow only the checked gap, never the live archive.
    GXDrawDone();
    if (MenuNativeIcon::loadBoo(buffer + kOptionOffset, kGuideOffset - kOptionOffset,
            reinterpret_cast<u8 *>(backup) + backup->bytes, MenuNativeIcon::BooBytes)) {
        backup->offset[2] = backup->bytes;
        backup->size[2] = MenuNativeIcon::BooBytes;
        backup->bytes += MenuNativeIcon::BooBytes;
    }
    memcpy(buffer + kOptionOffset, backup, backup->bytes);
    DCFlushRange(buffer + kOptionOffset, backup->bytes);
    GXInvalidateTexAll();
}

const ResTIMG *get(Asset asset, unsigned pose) {
    if (static_cast<unsigned>(asset) >= Count) return nullptr;
    TMarDirector *director = RetailInput::stageDirector();
    if (!director || (!director->_260 && !OSIsThreadTerminated(&gSetupThread)))
        return nullptr;
    u8 *buffer = gameBuffer(director);
    Archive archive;
    if (!buffer || !openArchive(buffer, kGuideOffset, archive)) return nullptr;
    if (asset <= Postcard) {
        static const u8 indices[] = {0, 1, 2, 4, 6, 8, 10};
        const unsigned index = indices[asset] +
            ((asset >= Palm && asset <= Boat) ? (pose & 1) : 0);
        return cached(reinterpret_cast<const Cache *>(buffer + kGuideOffset),
                      kBufferSize - kGuideOffset, kGuideMagic, index);
    }
    if (asset == TabPad || asset == TabGlasses || asset == TabGhost) {
        if (!sOptionReady || archive.size > kOptionOffset) return nullptr;
        const Cache *backup = reinterpret_cast<const Cache *>(SUSAMUNE_MENU_ASSET_BACKUP_PPC_BASE);
        const unsigned index = asset == TabGhost ? 2 : asset == TabGlasses;
        if (!cached(backup, SUSAMUNE_MENU_ASSET_BACKUP_SIZE, kOptionMagic, index)) return nullptr;
        Cache *gpu = reinterpret_cast<Cache *>(buffer + kOptionOffset);
        if (!cached(gpu, SUSAMUNE_MENU_ASSET_BACKUP_SIZE, kOptionMagic, index)) {
            // Guide swaps overwrite this middle gap; only immutable backup bytes live in MEM2.
            GXDrawDone();
            memcpy(gpu, backup, backup->bytes);
            DCFlushRange(gpu, backup->bytes);
            GXInvalidateTexAll();
        }
        return cached(gpu, SUSAMUNE_MENU_ASSET_BACKUP_SIZE, kOptionMagic, index);
    }
    const char *name = nullptr;
    switch (asset) {
    case TabShine: name = "shine_icon.bti"; break;
    case TabMario: name = "mario_icon.bti"; break;
    case TabCoin: name = "bluecoin_icon.bti"; break;
    case TabPianta: name = "monte_icon.bti"; break;
    default: return nullptr;
    }
    u32 bytes = 0;
    const u8 *source = find(archive, name, bytes);
    return texture(source, bytes);
}
}
