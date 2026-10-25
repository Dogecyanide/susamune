#include "susamune/menu_native_icon.h"
#include "susamune/menu_native_icon.hxx"
#include <Dolphin/DVD.h>
#include <Dolphin/OS.h>

namespace MenuNativeIcon {
namespace {
bool readDisc(void *context, Word offset, Byte *out, Word bytes) {
    DVDFileInfo *file = static_cast<DVDFileInfo *>(context);
    if ((offset & 31) || (reinterpret_cast<u32>(out) & 31) ||
        !range(offset, bytes, file->mLen)) return false;
    const Word aligned = (bytes + 31) & ~31u;
    DCInvalidateRange(out, aligned);
    return DVDReadPrio(file, out, aligned, offset, 2) == static_cast<s32>(aligned);
}
}

bool loadBoo(void *workspace, unsigned int workspaceBytes, void *out, unsigned int capacity) {
    if (!workspace || (reinterpret_cast<u32>(workspace) & 31) ||
        workspaceBytes < sizeof(Workspace)) return false;
    DVDFileInfo file = {};
    if (!DVDOpen("/data/scene/casino0.szs", &file)) return false;
    const bool result = extract(readDisc, &file, file.mLen, *static_cast<Workspace *>(workspace),
                                static_cast<Byte *>(out), capacity);
    DVDClose(&file);
    return result;
}

bool scaleController(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity) {
    return shrinkController(static_cast<const Byte *>(source), sourceBytes,
                            static_cast<Byte *>(out), capacity);
}
bool scalePianta(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity) {
    return shrinkPianta(static_cast<const Byte *>(source), sourceBytes,
                        static_cast<Byte *>(out), capacity);
}
bool scaleGlasses(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity) {
    return shrinkGlasses(static_cast<const Byte *>(source), sourceBytes,
                         static_cast<Byte *>(out), capacity);
}
bool scaleMario(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity) {
    return shrinkMario(static_cast<const Byte *>(source), sourceBytes,
                       static_cast<Byte *>(out), capacity);
}
bool scaleTitle(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity) {
    return shrinkTitle(static_cast<const Byte *>(source), sourceBytes,
                       static_cast<Byte *>(out), capacity);
}
}
