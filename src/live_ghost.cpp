#include "susamune/live_ghost.hxx"
#include "susamune/live_race.hxx"

#if TIMEWARP_LIVE_RACING
#include "Dolphin/MTX.h"
#include "Dolphin/math.h"
#include "SMS/Camera/PolarSubCamera.hxx"
#include "susamune/ghost_format.h"
#include "susamune/live_race_wire.h"
#include "susamune/creation_extras.hxx"
#include "susamune/fludd_colors.hxx"
#include "susamune/input_display.hxx"
#include "susamune/mario_colors.hxx"
#include "susamune/metadata_display.hxx"
#include "susamune/practice_session.hxx"
#include "susamune/qft_display.hxx"
#include "susamune/stage_loader.hxx"
#include "susamune/warp_wheel.hxx"
#include "susamune/menu.hxx"
#include "susamune/settings.hxx"

#pragma clang section rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

namespace LiveGhost {
namespace {
static const char kOpponent[] = "Opponent";
// Snapshot interpolation: poses carry the sender's millisecond clock and are
// shown about 100 ms in the past, longer when packets arrive unevenly. Past the
// newest pose the opponent keeps its last velocity for a moment, then holds.
const unsigned int kSamples = 8, kMinDelayMs = 100;  // kSamples: a power of two
const unsigned int kExtrapolateMs = 175, kStaleMs = 1000;
struct Sample { Ghost::VisualState pose; u32 remoteMs, receivedMs; SusamunePracticeInput input; };
struct State {
    Sample samples[kSamples];
    Ghost::VisualState latched;
    SusamunePracticeInput latchedInput;
    u32 first, count, sequence, sceneEpoch, originMs, token, latchedMs;  // ring of samples
    // Local minus remote clock along the fastest path seen, the average lateness
    // beyond it, and the playback delay that follows that lateness.
    u32 offset, jitter, delayMs, creep;  // delayMs: added to kMinDelayMs
    f32 correctionX, correctionY, correctionZ;
    u32 correctionMs, tickMs;
    bool received, visible, timed;
    char name[17];
};
#pragma clang section bss=""
State s;
State sExtra[Channels - 1];
unsigned sChannel;
State &currentState() { return sChannel ? sExtra[sChannel - 1] : s; }
struct Channel {
    unsigned previous;
    Channel(unsigned value) : previous(sChannel) { sChannel = value; }
    ~Channel() { sChannel = previous; }
};
#pragma clang section bss=".foxtrot.bss"
bool sInputsShown = true;
static_assert(sizeof(State) < 2048, "live ghost stays within its scalar budget");

s32 delta(u32 a, u32 b) { return static_cast<s32>(a - b); }
Sample &at(u32 i) { State &s = currentState(); return s.samples[(s.first + i) & (kSamples - 1)]; }
bool finite(f32 x) {
    // Bit validation remains effective under the game's fast-math build flags.
    union { f32 value; u32 bits; } word = {x};
    return (word.bits & 0x7fffffffu) <= 0x49742400u;
}
bool valid(const Ghost::VisualState &p) {
    return finite(p.x) && finite(p.y) && finite(p.z) &&
        p.animationId <= SUSAMUNE_GHOST_ANIMATION_ID_MAX &&
        p.animationPhase <= SUSAMUNE_GHOST_ANIMATION_PHASE_MAX &&
        p.yoshi <= SUSAMUNE_GHOST_V4_YOSHI_UNKNOWN &&
        (!p.yoshi || (p.animationId >= 0xb6u && p.animationId <= 0xc6u)) &&
        SusamuneGhostVisualValid(reinterpret_cast<const unsigned char *>(&p.fludd), 1) &&
        (!(p.fludd.mode & SUSAMUNE_GHOST_VISUAL_YOSHI) || p.yoshi != 0);
}
void newTimeline(u32 remoteMs) {
    State &s = currentState();
    s.count = 0;
    s.originMs = remoteMs;
    s.correctionMs = 0;
    if (!++s.token) ++s.token;
}
bool discontinuity(const Ghost::VisualState &a, const Ghost::VisualState &b) {
    const f32 x = a.x - b.x, y = a.y - b.y, z = a.z - b.z;
    return x * x + y * y + z * z > 1000000.0f;
}
// Positions continue along a to b for up to kExtrapolateMs past b; the angle
// and animation stop at b.
Ghost::VisualState interpolate(const Sample &a, const Sample &b, u32 time) {
    const s32 duration = delta(b.remoteMs, a.remoteMs);  // positive: submit keeps order
    s32 ahead = delta(time, a.remoteMs);
    if (ahead < 0) ahead = 0;
    if (ahead > duration + static_cast<s32>(kExtrapolateMs)) ahead = duration + kExtrapolateMs;
    const f32 t = static_cast<f32>(ahead) / duration, turn = t > 1 ? 1 : t;
    Ghost::VisualState p = t >= 1 ? b.pose : a.pose;
    p.x = a.pose.x + (b.pose.x - a.pose.x) * t;
    p.y = a.pose.y + (b.pose.y - a.pose.y) * t;
    p.z = a.pose.z + (b.pose.z - a.pose.z) * t;
    const s16 yaw = static_cast<s16>(static_cast<u16>(b.pose.yaw) -
                                       static_cast<u16>(a.pose.yaw));
    p.yaw = static_cast<s16>(a.pose.yaw + static_cast<s32>(yaw * turn));
    if (a.pose.animationId == b.pose.animationId && a.pose.yoshi == b.pose.yoshi) {
        const s32 phase = ((static_cast<s32>(b.pose.animationPhase) -
                           a.pose.animationPhase + 2048) & 4095) - 2048;
        p.animationPhase = static_cast<u16>((a.pose.animationPhase +
            static_cast<s32>(phase * turn)) & 4095);
    }
    return p;
}
}

void reset() {
    State &s = currentState();
    u32 token = s.token + 1u;
    if (!token) ++token;
    s = {};
    s.token = token;
    setName(kOpponent, 8);
}

bool setName(const char *name, unsigned int length) {
    State &s = currentState();
    if (!name || !length || length > 16) return false;
    for (unsigned int i = 0; i < length; ++i)
        if (static_cast<unsigned char>(name[i]) < 0x20u ||
            static_cast<unsigned char>(name[i]) > 0x7eu) return false;
    for (unsigned int i = 0; i < length; ++i) s.name[i] = name[i];
    s.name[length] = 0;
    return true;
}

bool submit(const Ghost::VisualState &pose, u32 sequence, u32 remoteMs,
            u32 sceneEpoch, u32 receivedMs, const SusamunePracticeInput *input) {
    State &s = currentState();
    if (!valid(pose) || (input && ((input->buttons & ~MSR_INPUT_BUTTON_MASK) ||
        input->error || input->flags))) return false;
    const bool newScene = !s.received || sceneEpoch != s.sceneEpoch;
    if (s.received && newScene && delta(sceneEpoch, s.sceneEpoch) <= 0) return false;
    if (!newScene && (delta(sequence, s.sequence) <= 0 ||
        delta(remoteMs, at(s.count - 1).remoteMs) <= 0 ||
        delta(receivedMs, at(s.count - 1).receivedMs) < 0)) return false;
    if (newScene || delta(remoteMs, at(s.count - 1).remoteMs) > 1000 ||
        discontinuity(pose, at(s.count - 1).pose)) newTimeline(remoteMs);
    if (s.count == kSamples) { ++s.first; --s.count; }
    // The fastest packet sets the clock offset; it creeps up 1 ms per 32 later
    // packets so a new route or clock drift is followed. Creeping every packet
    // slowed playback ~3% and then snapped it forward, mostly between 25 and
    // 30 Hz senders (PAL and NTSC).
    const u32 lag = receivedMs - remoteMs;
    if (!s.timed || delta(lag, s.offset) < 0) { s.offset = lag; s.timed = true; }
    const u32 late = lag - s.offset;
    s.jitter = (s.jitter * 7 + (late > 67u ? 67u : late)) / 8;
    if (late && !(++s.creep & 31)) ++s.offset;
    Sample &slot = at(s.count++);
    slot.pose = pose; slot.remoteMs = remoteMs; slot.receivedMs = receivedMs;
    slot.input = input ? *input : SusamunePracticeInput{};
    s.sequence = sequence;
    s.sceneEpoch = sceneEpoch;
    s.received = true;
    if (s.count > 1 && s.latched.recordingToken == s.token &&
        delta(s.latchedMs, at(s.count - 2).remoteMs) > 0) {
        // Blend back from a predicted pose when fresh movement corrects it.
        const Ghost::VisualState corrected = interpolate(at(s.count - 2), slot, s.latchedMs);
        s.correctionX = s.latched.x - corrected.x;
        s.correctionY = s.latched.y - corrected.y;
        s.correctionZ = s.latched.z - corrected.z;
        s.correctionMs = 100;
    }
    return true;
}


void tick(u32 localNowMs, bool canDisplaySameCanonicalScene) {
    State &s = currentState();
    s.visible = false;
    if (!canDisplaySameCanonicalScene || !s.count) return;
    const Sample &last = at(s.count - 1);
    const s32 age = delta(localNowMs, last.receivedMs);
    if (age < 0 || static_cast<u32>(age) > kStaleMs) return;
    // Two send intervals plus twice the lateness (100-200 ms), eased 1 ms per
    // frame so the opponent never jumps when the delay changes.
    const u32 extra = s.jitter > 17 ? 2 * s.jitter - 34 : 0;
    if (s.delayMs < extra) ++s.delayMs;
    else if (s.delayMs > extra) --s.delayMs;
    // Playback advances on the local clock between packet arrivals.
    u32 time = localNowMs - s.offset - kMinDelayMs - s.delayMs;
    if (delta(time, at(0).remoteMs) < 0) time = at(0).remoteMs;
    if (s.latched.recordingToken == s.token && delta(time, s.latchedMs) < 0)
        time = s.latchedMs;
    s.latched = last.pose;
    s.latchedInput = last.input;
    if (s.count > 1) {
        unsigned int i = 1;
        while (i + 1 < s.count && delta(time, at(i).remoteMs) > 0) ++i;
        s.latched = interpolate(at(i - 1), at(i), time);
        // Hold the matching sample; interpolating buttons invents inputs.
        s.latchedInput = delta(time, at(i).remoteMs) < 0
            ? at(i - 1).input : at(i).input;
    }
    const u32 elapsed = localNowMs - s.tickMs;
    if (elapsed >= s.correctionMs) s.correctionMs = 0;
    else s.correctionMs -= elapsed;
    const f32 correction = s.correctionMs * 0.01f;
    s.latched.x += s.correctionX * correction;
    s.latched.y += s.correctionY * correction;
    s.latched.z += s.correctionZ * correction;
    s.tickMs = localNowMs;
    // Cosmetic water time is local to this remote timeline, never the game timer.
    // 120 per second; u32 holds a 16-day timeline.
    s.latched.visualQf = (time - s.originMs) * 3u / 25u;
    s.latched.recordingToken = s.token;
    s.latchedMs = time;
    s.visible = s.latched.visible;
}


bool visualState(Ghost::VisualState *out) {
    State &s = currentState();
    if (!out || !s.visible) return false;
    *out = s.latched;
    return true;
}

bool inputState(SusamunePracticeInput *out) {
    State &s = currentState();
    if (!out || !s.visible) return false;
    *out = s.latchedInput;
    return true;
}

bool inputsShown() { return sInputsShown && !LiveRace::groupState(); }
void setInputsShown(bool shown) { sInputsShown = shown; }

void drawName(Menu *menu) {
    State &s = currentState();
    if (!menu || menu->shown() || !s.visible || !gpCamera ||
        !LiveRace::opponentShown() ||
        Ghost::observerPreparing() || Ghost::observerStatsSuppressed()) return;
    Vec position = {gpCamera->mTranslation.x, gpCamera->mTranslation.y, gpCamera->mTranslation.z};
    Vec up = {gpCamera->mUpVector.x, gpCamera->mUpVector.y, gpCamera->mUpVector.z};
    Vec target = {gpCamera->mTargetPos.x, gpCamera->mTargetPos.y, gpCamera->mTargetPos.z};
    // A NaN or infinite camera value fails these ranges or makes the projected
    // depth and position non-finite, which the checks below reject.
    const f32 fovy = gpCamera->mProjectionFovy, aspect = gpCamera->mProjectionAspect;
    const f32 near = gpCamera->mProjectionNear, far = gpCamera->mProjectionFar;
    if (!(fovy >= 1 && fovy <= 170 && aspect >= 0.5f && aspect <= 2 &&
          near > 0 && near < far && far <= 1000000)) return;
    Vec source = {s.latched.x, s.latched.y + 140.0f, s.latched.z}, viewPosition;
    Mtx view;
    C_MTXLookAt(view, &position, &up, &target);
    PSMTXMultVec(view, &source, &viewPosition);
    const f32 depth = -viewPosition.z;
    if (!finite(depth) || !(depth >= near && depth <= far) ||
        !finite(viewPosition.x) || !finite(viewPosition.y)) return;
    const f32 cot = 1.0f / tanf(fovy * 0.00872664626f);
    const f32 x = viewPosition.x * cot / (aspect * depth);
    const f32 y = viewPosition.y * cot / depth;
    if (!finite(x) || !finite(y) || !(x >= -1 && x <= 1 && y >= -1 && y <= 1)) return;
    const int width = Menu::textWidth(s.name, 12);
    if (width <= 0 || width > 624) return;
    int left = static_cast<int>((x * 0.5f + 0.5f) * 640) - width / 2;
    int top = static_cast<int>((0.5f - y * 0.5f) * 480) - 14;
    if (left < 8) left = 8;
    if (left > 632 - width) left = 632 - width;
    if (top < 8) top = 8;
    if (top > 456) top = 456;
    menu->fillBox(left - 3, top - 2, width + 6, 17, JUtility::TColor(0, 0, 0, 130));
    menu->drawText(s.name, left, top, 12, 12, JUtility::TColor(190, 250, 255, 255));
}

void drawInputs(Menu *menu) {
    State &s = currentState();
    if (!menu || menu->shown() || !inputsShown() ||
        PracticeSession::hideHud() || PracticeSession::ownsGameplayInput() ||
        Ghost::observerPreparing() || Ghost::observerStatsSuppressed() ||
        StageLoader::modal() || StageLoader::resultOwnsInput() ||
        WarpWheel::shown() || WarpWheel::promptPending() ||
        gQftDisplay.editing() || gInputDisplay.editing() ||
        gMetadataDisplay.editing() || gCreationExtras.editing() ||
        MarioColors::editing() || FluddColors::editing()) return;
    SusamunePracticeInput input;
    if (!inputState(&input)) return;
    gInputDisplay.drawSnapshot(menu, input, 460, 350, 65, nullptr);
    int size = 12;
    while (size > 8 && Menu::textWidth(s.name, size) > 148) --size;
    menu->drawText(s.name, 460, 335, size, size, JUtility::TColor(220, 240, 255, 255));
}
void resetAll() { for (unsigned i = 0; i < Channels; ++i) { Channel scope(i); reset(); } }
void resetFor(unsigned i) { if (i < Channels) { Channel scope(i); reset(); } }
bool setNameFor(unsigned i, const char *name, unsigned length) {
    if (i >= Channels) return false;
    Channel scope(i); return setName(name, length);
}
bool submitFor(unsigned i, const Ghost::VisualState &p, u32 sequence, u32 remoteMs,
               u32 epoch, u32 now, const SusamunePracticeInput *input) {
    if (i >= Channels) return false;
    Channel scope(i); return submit(p, sequence, remoteMs, epoch, now, input);
}
void tickFor(unsigned i, u32 now, bool sameScene) {
    if (i >= Channels) return;
    Channel scope(i); tick(now, sameScene);
}
bool visualStateFor(unsigned i, Ghost::VisualState *out) {
    if (i >= Channels) return false;
    Channel scope(i); return LiveGhost::visualState(out);
}
void drawNameFor(unsigned i, Menu *menu) {
    if (i >= Channels) return;
    Channel scope(i); drawName(menu);
}
}
#endif
