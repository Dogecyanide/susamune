#include "susamune/hud_editor_preview.hxx"
#include "susamune/susamune_cfg.h"
#include "Dolphin/mem.h"
#include "SMS/GC2D/GCConsole2.hxx"

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace HudEditorPreview {
namespace {
constexpr unsigned kMaxPanes = 12;
constexpr unsigned kGeometrySize = 0xB4 - 0x14;

struct Counter {
    u32 tag;
    u16 root, first, last;
};
const Counter kCounters[] = {
    {'\0c_0', 0x108, 0x0C8, 0x0DC},
#if defined(SUSAMUNE_VERSION_JP)
    {'\0r_0', 0x428, 0x42C, 0x440},
#else
    {'\0r_0', 0x42C, 0x430, 0x444},
#endif
    {'\0d_0', 0x160, 0x148, 0x15C},
    {'\0m_0', 0x3A8, 0x38C, 0x3A4},
    {'\0s_0', 0x140, 0x128, 0x13C},
};
struct PaneState {
    J2DPane *pane;
    u8 geometry[kGeometrySize];
    u8 alpha, alphaCopy;
    bool visible;
};
struct DrawState {
    PaneState panes[kMaxPanes];
    unsigned count;
    bool active;
} sDraw;

static_assert(__builtin_offsetof(J2DPane, mRect) == 0x14 &&
              __builtin_offsetof(J2DPane, _B4) == 0xB4,
              "HUD preview geometry range changed");

bool append(J2DPane *pane) {
    if (!pane || sDraw.count == kMaxPanes) return false;
    for (unsigned i = 0; i < sDraw.count; ++i)
        if (sDraw.panes[i].pane == pane) return false;
    sDraw.panes[sDraw.count++].pane = pane;
    return true;
}

bool collect(J2DScreen *screen, J2DPane *root) {
    sDraw.count = 0;
    if (!append(screen) || !append(root)) return false;
    const unsigned childrenOffset = reinterpret_cast<u8 *>(&screen->mChildrenList) -
        reinterpret_cast<u8 *>(screen);
    for (J2DPane *pane = root;;) {
        JSUPtrList *parent = pane->mPtrLink.mParentList;
        if (!parent) return false;
        if (parent == &screen->mChildrenList) break;
        pane = reinterpret_cast<J2DPane *>(reinterpret_cast<u8 *>(parent) -
            childrenOffset);
        if (!append(pane)) return false;
    }
    const unsigned firstChild = sDraw.count;
    for (unsigned i = 1; i < sDraw.count; ++i) {
        // Retail counters sit under ROOT; do not pull its sibling counters in.
        if (i > 1 && i < firstChild) continue;
        J2DPane *pane = sDraw.panes[i].pane;
        for (JSUPtrLink *link = pane->mChildrenList.mFirst; link;
             link = link->mNextLink) {
            if (link->mParentList != &pane->mChildrenList ||
                !append(static_cast<J2DPane *>(link->mItemPtr))) return false;
        }
    }
    return true;
}

void originalBounds(TGCConsole2 *console, unsigned offset) {
    const u8 *wrapper = *reinterpret_cast<const u8 *const *>(
        reinterpret_cast<const u8 *>(console) + offset);
    if (!wrapper) return;
    // TBlendPane adds a vptr before TBoundPane's pane/bounds prefix.
    for (unsigned word = 0; word < 2; ++word) {
        J2DPane *pane = reinterpret_cast<J2DPane *const *>(wrapper)[word];
        for (unsigned i = 1; i < sDraw.count; ++i) {
            if (sDraw.panes[i].pane != pane) continue;
            memcpy(&pane->mRect, wrapper + (word + 1) * sizeof(void *),
                   sizeof(pane->mRect));
            return;
        }
    }
}
}  // namespace

bool beginDraw(TGCConsole2 *console, unsigned color) {
    if (sDraw.active || !console || !console->mMainScreen) return false;
    if (color == SUSAMUNE_CREATION_LIFE_TEXT) color = SUSAMUNE_CREATION_LIVES_BG;
    if (color < SUSAMUNE_CREATION_COIN_BG ||
        color > SUSAMUNE_CREATION_SHINES_BG) return false;
    const Counter &counter = kCounters[color - SUSAMUNE_CREATION_COIN_BG];
    J2DScreen *screen = console->mMainScreen;
    if (!collect(screen, screen->search(counter.tag))) return false;
    for (unsigned i = 0; i < sDraw.count; ++i) {
        PaneState &saved = sDraw.panes[i];
        memcpy(saved.geometry, &saved.pane->mRect, sizeof(saved.geometry));
        saved.alpha = saved.pane->mAlpha;
        saved.alphaCopy = saved.pane->mAlphaCopy;
        saved.visible = saved.pane->mIsVisible;
        saved.pane->mAlpha = 255;
        saved.pane->mIsVisible = true;
    }
    // Hidden counters retain their exit-animation offsets, even while paused.
    originalBounds(console, counter.root);
    for (unsigned offset = counter.first; offset <= counter.last; offset += 4)
        originalBounds(console, offset);
    if (color == SUSAMUNE_CREATION_RED_BG) {
        J2DPane *timer = screen->search('\0t_0');
        JUTRect &bounds = sDraw.panes[1].pane->mRect;
        // startAppearRedCoin lifts the settled card above a visible timer.
        const int dy = timer && timer->mIsVisible ? -73 : 0;
        bounds.mY1 += dy;
        bounds.mY2 += dy;
    }
    sDraw.active = true;
    return true;
}

void endDraw() {
    if (!sDraw.active) return;
    for (unsigned i = 0; i < sDraw.count; ++i) {
        PaneState &saved = sDraw.panes[i];
        memcpy(&saved.pane->mRect, saved.geometry, sizeof(saved.geometry));
        saved.pane->mAlpha = saved.alpha;
        saved.pane->mAlphaCopy = saved.alphaCopy;
        saved.pane->mIsVisible = saved.visible;
    }
    sDraw.active = false;
}
}  // namespace HudEditorPreview
