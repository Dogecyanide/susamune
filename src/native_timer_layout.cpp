#include "susamune/native_timer_layout.hxx"

#include "Dolphin/mem.h"
#include "JSystem/J2D/J2DScreen.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MarDirector.hxx"
#include "susamune/native_timer_transform.h"
#include "susamune/settings.hxx"

extern "C" void *retailPaneVtable[] asm("__vt__7J2DPane");
extern "C" void *retailPictureVtable[] asm("__vt__10J2DPicture");
extern "C" void *retailTextVtable[] asm("__vt__10J2DTextBox");

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace NativeTimerLayout {
namespace {

constexpr unsigned kMaxPanes = 32;
constexpr unsigned kVtableWords = 11;
constexpr unsigned kMakeMatrixSlot = 10;
constexpr unsigned kGeometryBytes = 0xB4 - 0x24;
typedef void (*MakeMatrix)(J2DPane *, int, int);

struct PaneState {
    J2DPane *pane;
    void **vtable;
    u8 geometry[kGeometryBytes];
    u8 alphaCopy;
};

struct DrawState {
    PaneState panes[kMaxPanes];
    void *drawVtables[3][kVtableWords];
    int rootRect[4];
    unsigned count;
    int percent;
    bool active;
};

DrawState sDraw;

static_assert(__builtin_offsetof(J2DPane, mCRect) == 0x24,
              "J2DPane draw bounds moved");
static_assert(__builtin_offsetof(J2DPane, mScreenMtx) == 0x54,
              "J2DPane local matrix moved");
static_assert(__builtin_offsetof(J2DPane, _B4) == 0xB4,
              "J2DPane global matrix end moved");
static_assert(sizeof(DrawState) <= 0x1500, "timer draw snapshot grew");

void makeDrawMatrix(J2DPane *pane, int x, int y) {
    for (unsigned i = 0; i < sDraw.count; ++i) {
        PaneState &saved = sDraw.panes[i];
        if (saved.pane != pane) continue;
        reinterpret_cast<MakeMatrix>(saved.vtable[kMakeMatrixSlot])(pane, x, y);

        JUTRect &bounds = pane->mCRect;
        if (i == 0) {
            SusamuneTimerScaleBasis(&pane->mScreenMtx[0][0], sDraw.percent);
            bounds.mX2 = bounds.mX1 + SusamuneTimerScaleCeil(
                bounds.mX2 - bounds.mX1, sDraw.percent);
            bounds.mY2 = bounds.mY1 + SusamuneTimerScaleCeil(
                bounds.mY2 - bounds.mY1, sDraw.percent);
        } else {
            bounds.mX1 = SusamuneTimerScaleFloor(bounds.mX1, sDraw.percent);
            bounds.mY1 = SusamuneTimerScaleFloor(bounds.mY1, sDraw.percent);
            bounds.mX2 = SusamuneTimerScaleCeil(bounds.mX2, sDraw.percent);
            bounds.mY2 = SusamuneTimerScaleCeil(bounds.mY2, sDraw.percent);
        }
        pane->mClipRect = bounds;
        return;
    }
}

bool collect(J2DPane *root) {
    sDraw.count = 1;
    sDraw.panes[0].pane = root;
    for (unsigned i = 0; i < sDraw.count; ++i) {
        J2DPane *pane = sDraw.panes[i].pane;
        void **vtable = *reinterpret_cast<void ***>(pane);
        if (vtable != retailPaneVtable && vtable != retailPictureVtable &&
            vtable != retailTextVtable) return false;
        for (JSUPtrLink *link = pane->mChildrenList.mFirst; link;
             link = link->mNextLink) {
            if (sDraw.count == kMaxPanes || !link->mItemPtr ||
                link->mParentList != &pane->mChildrenList) return false;
            J2DPane *child = static_cast<J2DPane *>(link->mItemPtr);
            for (unsigned j = 0; j < sDraw.count; ++j)
                if (sDraw.panes[j].pane == child) return false;
            sDraw.panes[sDraw.count++].pane = child;
        }
    }
    return true;
}

}  // namespace

bool beginDraw(J2DScreen *screen) {
    if (sDraw.active) return false;
    const unsigned x = gSettings.get(SETTING_NATIVE_TIMER_X);
    const unsigned y = gSettings.get(SETTING_NATIVE_TIMER_Y);
    const unsigned scale = gSettings.get(SETTING_NATIVE_TIMER_SCALE);
    if (x > 32 || y > 24 || scale > 10 ||
        (x == 16 && y == 12 && scale == 5) || !screen ||
        gpApplication.mContext != TApplication::CONTEXT_DIRECT_STAGE ||
        !gpMarDirector || !gpMarDirector->_260 ||
        !gpMarDirector->mGCConsole ||
        gpMarDirector->mGCConsole->mMainScreen != screen) return false;
    J2DPane *root = screen->search('\0t_0');
    if (!root || !root->mIsVisible || !collect(root)) return false;

    memcpy(sDraw.rootRect, &root->mRect, sizeof(sDraw.rootRect));
    sDraw.percent = 50 + scale * 10;
    void **const originals[] = {
        retailPaneVtable, retailPictureVtable, retailTextVtable,
    };
    for (unsigned i = 0; i < 3; ++i) {
        memcpy(sDraw.drawVtables[i], originals[i], sizeof(sDraw.drawVtables[i]));
        sDraw.drawVtables[i][kMakeMatrixSlot] = reinterpret_cast<void *>(makeDrawMatrix);
    }
    for (unsigned i = 0; i < sDraw.count; ++i) {
        PaneState &saved = sDraw.panes[i];
        saved.vtable = *reinterpret_cast<void ***>(saved.pane);
        memcpy(saved.geometry, &saved.pane->mCRect, sizeof(saved.geometry));
        saved.alphaCopy = saved.pane->mAlphaCopy;
    }
    sDraw.active = true;
    root->add((static_cast<int>(x) - 16) * 10,
              (static_cast<int>(y) - 12) * 10);
    // Retail draw rebuilds matrices before clipping and walking children.
    // Lend each pane its original vtable with only that draw step wrapped.
    for (unsigned i = 0; i < sDraw.count; ++i) {
        PaneState &saved = sDraw.panes[i];
        const unsigned type = saved.vtable == retailPaneVtable ? 0 :
                              saved.vtable == retailPictureVtable ? 1 : 2;
        *reinterpret_cast<void ***>(saved.pane) = sDraw.drawVtables[type];
    }
    return true;
}

void endDraw() {
    if (!sDraw.active) return;
    for (unsigned i = 0; i < sDraw.count; ++i) {
        PaneState &saved = sDraw.panes[i];
        *reinterpret_cast<void ***>(saved.pane) = saved.vtable;
        memcpy(&saved.pane->mCRect, saved.geometry, sizeof(saved.geometry));
        saved.pane->mAlphaCopy = saved.alphaCopy;
    }
    memcpy(&sDraw.panes[0].pane->mRect, sDraw.rootRect, sizeof(sDraw.rootRect));
    sDraw.active = false;
}

}  // namespace NativeTimerLayout
