#pragma once

namespace GhostSpinObservation {
enum { kCapacity = 16, kValid = 1 };
// Stable wire IDs; regional inlined copies retain the same order.
enum Caller {
    CONSIDER_JUMP_ROTATE = 1, CHECK_ALL_MOTIONS, CHANGE_PLAYER_JUMPING,
    CHANGE_PLAYER_TRI_JUMP, CONSIDER_ROTATE_JUMP_START, WALK_END, TURN_END,
    TURNING, CONSIDER_ROTATE_START
};
enum Mode { NONE = 0, RECORD = 1, PLAYBACK = 2 };
enum Error { NO_ERROR = 0, OVERFLOW = 1, UNKNOWN_CALLER = 2, BAD_RESULT = 4,
             WRONG_CALLER = 8, WRONG_SEQUENCE = 16, UNDERRUN = 32, WRONG_TICK = 64 };
struct Event { unsigned sequence, caller, result, outDir, valid; };
struct Queue {
    unsigned savedR12, savedR11, savedCr, savedR10;
    unsigned count, error, sequence;
    Event events[kCapacity];
    unsigned mode, read, frame, tick;
    unsigned frames[kCapacity], ticks[kCapacity];
    unsigned nativeR0;
};
static_assert(sizeof(Event) == 20 && sizeof(Queue) == 496 &&
              __builtin_offsetof(Queue, count) == 16 &&
              __builtin_offsetof(Queue, error) == 20 &&
              __builtin_offsetof(Queue, sequence) == 24 &&
              __builtin_offsetof(Queue, events) == 28 &&
              __builtin_offsetof(Queue, mode) == 348 &&
              __builtin_offsetof(Queue, read) == 352 &&
              __builtin_offsetof(Queue, frame) == 356 &&
              __builtin_offsetof(Queue, tick) == 360 &&
              __builtin_offsetof(Queue, frames) == 364 &&
              __builtin_offsetof(Queue, ticks) == 428 &&
              __builtin_offsetof(Queue, nativeR0) == 492, "spin observer assembly layout");

// The owner keeps this queue alive until uninstall succeeds, and drains it on
// the game thread before advancing the recording's frame or movement tick.
bool install(Queue &, Mode = RECORD);
bool uninstall(Mode owner = NONE);
}
