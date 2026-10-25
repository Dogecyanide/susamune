#include "susamune/native_hud_precision.hxx"
#include "susamune/qft_timer.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/settings.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/creation_extras.hxx"
#include "Dolphin/mem.h"
#include "JSystem/J2D/J2DScreen.hxx"
#include "JSystem/J2D/J2DPicture.hxx"
#include "SMS/System/MarDirector.hxx"

#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace NativeHudPrecision {
namespace {
constexpr unsigned kMatrixSlot = 10;
constexpr unsigned kDrawSlot = 8;
constexpr unsigned kVtableWords = 11;
typedef void (*MakeMatrix)(J2DPane *, int, int);
typedef void (*DrawSelf)(J2DPicture *, int, int, Mtx *);

struct BorrowedPane {
    J2DPane *pane;
    void **original;
    void *table[kVtableWords];
    JUTRect clip;
};

struct DrawState {
    BorrowedPane panes[4];
    J2DPicture *digits[6];
    JUTTexture *textures[6];
    JUTTexture *extraTexture;
    int clipAdvance;
    int clipRise;
    bool active;
    bool extra;
    bool decimal;
};

DrawState sDraw;
TMarDirector *sDirector;
u8 sDigits[7];
bool sValid;

void formatDigits(s32 qf, u8 digits[7]) {
    const u32 count = qf > 0 ? (u32)qf : 0;
    u32 millis = count >= 719281 ? 5999999 :
        count / 120 * 1001 + count % 120 * 1001 / 120;
    if (millis > 5999999) millis = 5999999;
    const u32 minutes = millis / 60000;
    const u32 seconds = millis / 1000 % 60;
    digits[0] = minutes / 10;
    digits[1] = minutes % 10;
    digits[2] = seconds / 10;
    digits[3] = seconds % 10;
    digits[4] = millis / 100 % 10;
    digits[5] = millis / 10 % 10;
    digits[6] = millis % 10;
}

void makeMatrix(J2DPane *pane, int x, int y) {
    for (unsigned i = 0; i < 3; ++i) {
        BorrowedPane &saved = sDraw.panes[i];
        if (saved.pane != pane) continue;
        reinterpret_cast<MakeMatrix>(saved.original[kMatrixSlot])(pane, x, y);
        // Retail intersects descendant scissors after this matrix callback.
        // Grow the clipping window, keeping the six original digit sizes.
        pane->mClipRect.mX2 += sDraw.clipAdvance;
        if (sDraw.clipRise < 0) pane->mClipRect.mY1 += sDraw.clipRise;
        else pane->mClipRect.mY2 += sDraw.clipRise;
        return;
    }
}

void drawLastDigit(J2DPicture *picture, int x, int y, Mtx *matrix) {
    const DrawSelf original = reinterpret_cast<DrawSelf>(sDraw.panes[2].original[kDrawSlot]);
    original(picture, x, y, matrix);
    // Pane positions are parent-relative; their own glyph rotation is separate.
    // Extrapolate the two composed positions rather than rotating spacing again.
    Mtx &world = *reinterpret_cast<Mtx *>(picture->_84);
    const Mtx &previous = *reinterpret_cast<const Mtx *>(sDraw.digits[4]->_84);
    float translation[3];
    for (unsigned row = 0; row < 3; ++row) {
        translation[row] = world[row][3];
        world[row][3] += world[row][3] - previous[row][3];
    }
    JUTTexture *texture = picture->mTextures[0];
    picture->mTextures[0] = sDraw.extraTexture;
    sDraw.extra = true;
    original(picture, x, y, matrix);
    sDraw.extra = false;
    picture->mTextures[0] = texture;
    for (unsigned row = 0; row < 3; ++row) world[row][3] = translation[row];
}

void drawDecimal(J2DPicture *picture, int x, int y, Mtx *matrix) {
    const DrawSelf original = reinterpret_cast<DrawSelf>(sDraw.panes[3].original[kDrawSlot]);
    const JUTRect bounds = picture->mRect;
    const u32 binding = picture->mBinding;
    const int cut = (bounds.mY2 - bounds.mY1) / 2;
    Mtx &world = *reinterpret_cast<Mtx *>(picture->_84);
    float translation[3];
    for (unsigned row = 0; row < 3; ++row) {
        translation[row] = world[row][3];
        world[row][3] += world[row][1] * cut;
    }
    // Bottom binding crops the native colon's lower dot without scaling its art.
    picture->mRect.mY2 -= cut;
    picture->mBinding = (binding & ~BindingTop) | BindingBottom;
    original(picture, x, y, matrix);
    picture->mRect = bounds;
    picture->mBinding = binding;
    for (unsigned row = 0; row < 3; ++row) world[row][3] = translation[row];
}
}

void capture(bool practiceHolding) {
    sValid = false;
    // The setup thread reuses old HUD storage until it publishes stage readiness.
    if (!gpMarDirector || RetailInput::stageDirector() != gpMarDirector ||
        !gpMarDirector->_260)
        return;
    s32 qf = 0;
    bool stopped = false;
    if (!gQFTTimer.currentQf(&qf, &stopped) || !gpMarDirector ||
        !gpMarDirector->mGCConsole || gpMarDirector->mGCConsole->mIsTimerMoving)
        return;
    QFTTimer::SavestateData sidecar;
    gQFTTimer.captureSavestate(sidecar);
    const u8 *bytes = reinterpret_cast<const u8 *>(&sidecar);
    // Existing 96-byte sidecar: retail ownership at 92, stop reason at 2.
    // Ownership remains set after a race stops; its final result stays 2DP.
    const u8 visibility = gSettings.get(SETTING_TIMER_SUNSHINE_VISIBILITY);
    if (bytes[92] || visibility == 2 || (visibility == 1 && (!stopped || !bytes[2])))
        return;
    if (!stopped) {
        if (PracticeSession::paused()) {
            if (practiceHolding) qf -= 4;
        } else {
            s32 transition;
            u16 target;
            if (gQFTTimer.transitionEntryQf(&transition, &target)) qf = transition;
        }
    }
    formatDigits(qf, sDigits);
    sDirector = gpMarDirector;
    sValid = true;
}

bool beginDraw(J2DScreen *screen) {
    if (sDraw.active || !sValid || !screen || sDirector != gpMarDirector ||
        RetailInput::stageDirector() != gpMarDirector || !gpMarDirector ||
        !gpMarDirector->_260 || !gpMarDirector->mGCConsole)
        return false;
    TGCConsole2 *console = gpMarDirector->mGCConsole;
    if (console->mMainScreen != screen || console->mIsTimerMoving) return false;
    J2DPane *root = screen->search('\0t_0');
    J2DPane *normal = screen->search('\0t_1');
    if (!root || !normal || !root->mIsVisible || !normal->mIsVisible) return false;
    J2DPicture *digits[6];
    for (unsigned i = 0; i < 6; ++i) {
        J2DPane *pane = screen->search('t_n1' + i);
        if (!pane || pane->mTypeMagic != 'PIC1' || !pane->mIsVisible) return false;
        digits[i] = static_cast<J2DPicture *>(pane);
        if (digits[i]->mTextureCount != 1 || !digits[i]->mTextures[0]) return false;
    }
    // All three retail setTimer implementations index this same texture table.
    JUTTexture *const *numbers = reinterpret_cast<JUTTexture *const *>(
        reinterpret_cast<const u8 *>(console) + 0xE0);
    for (unsigned i = 0; i < 7; ++i)
        if (!numbers[sDigits[i]]) return false;
    const int advance = digits[5]->mRect.mX1 - digits[4]->mRect.mX1;
    const int rise = digits[5]->mRect.mY1 - digits[4]->mRect.mY1;
    if (advance <= 0 || advance > 64 || rise < -32 || rise > 32) return false;
    J2DPane *panes[] = {root, normal, digits[5]};
    for (unsigned i = 0; i < 3; ++i) {
        BorrowedPane &saved = sDraw.panes[i];
        saved.pane = panes[i];
        saved.original = *reinterpret_cast<void ***>(panes[i]);
        memcpy(saved.table, saved.original, sizeof(saved.table));
        saved.table[kMatrixSlot] = reinterpret_cast<void *>(makeMatrix);
        saved.clip = panes[i]->mClipRect;
    }
    sDraw.panes[2].table[kDrawSlot] = reinterpret_cast<void *>(drawLastDigit);
    sDraw.decimal = false;
    if (gSettings.get(SETTING_NATIVE_TIMER_DECIMAL_SEPARATOR) == 1) {
        J2DPane *separator = screen->search('t_c2');
        if (separator && separator->mTypeMagic == 'PIC1' && separator->mIsVisible) {
            J2DPicture *picture = static_cast<J2DPicture *>(separator);
            if (picture->mTextureCount == 1 && picture->mTextures[0] &&
                picture->mRect.mY2 > picture->mRect.mY1 &&
                !picture->mMirrorFlags && !picture->mRotate90) {
                BorrowedPane &saved = sDraw.panes[3];
                saved.pane = picture;
                saved.original = *reinterpret_cast<void ***>(picture);
                memcpy(saved.table, saved.original, sizeof(saved.table));
                saved.table[kDrawSlot] = reinterpret_cast<void *>(drawDecimal);
                *reinterpret_cast<void ***>(picture) = saved.table;
                sDraw.decimal = true;
            }
        }
    }
    const unsigned scale = gCreationExtras.nativeTimerStyle().scale;
    const unsigned percent = scale >= 50 && scale <= 200 ? scale : 100;
    sDraw.clipAdvance = (advance * percent + 99) / 100;
    const int height = ((rise < 0 ? -rise : rise) * percent + 99) / 100;
    sDraw.clipRise = rise < 0 ? -height : height;
    sDraw.extraTexture = numbers[sDigits[6]];
    for (unsigned i = 0; i < 6; ++i) {
        sDraw.digits[i] = digits[i];
        sDraw.textures[i] = digits[i]->mTextures[0];
        digits[i]->mTextures[0] = numbers[sDigits[i]];
    }
    for (unsigned i = 0; i < 3; ++i)
        *reinterpret_cast<void ***>(panes[i]) = sDraw.panes[i].table;
    sDraw.active = true;
    sDraw.extra = false;
    return true;
}

void endDraw() {
    if (!sDraw.active) return;
    for (unsigned i = 0; i < 6; ++i)
        sDraw.digits[i]->mTextures[0] = sDraw.textures[i];
    for (unsigned i = 0; i < 3; ++i) {
        BorrowedPane &saved = sDraw.panes[i];
        *reinterpret_cast<void ***>(saved.pane) = saved.original;
        saved.pane->mClipRect = saved.clip;
    }
    if (sDraw.decimal)
        *reinterpret_cast<void ***>(sDraw.panes[3].pane) = sDraw.panes[3].original;
    sDraw.active = false;
}

unsigned normalDigits() { return sDraw.active ? 7 : 6; }
bool extraDigit() { return sDraw.extra; }
}
