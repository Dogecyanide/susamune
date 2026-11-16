#pragma once
#include "susamune/ghost_fludd.h"
#include "susamune/ghost_world_witness.h"
#include "susamune/ghost_trace_continuation.h"
#include "susamune/ghost_trace_observation.h"

namespace GhostTraceDecode {
enum { kInputBytes = 300, kKnownCapabilities = 0xffffff,
       kFrameInput = 0x80000000u, kInputFrozen = 1, kInputSuppressed = 2 };
enum Result { EVENT, CHUNK_DONE, FAILED };
enum Error { NONE, ARGUMENT, FORMAT, CAPABILITY, BOUNDARY, ORDER, SCHEMA, BASELINE, VALUE };
enum Type { FRAME, INPUT, STAGE_START, VISUAL, RNG, SESSION, IDENTITY, WORLD_WITNESS, CONTINUATION, PROVENANCE, OBSERVATION };
struct RawPad {
    unsigned short buttons;
    signed char stickX, stickY, substickX, substickY;
    unsigned char triggerL, triggerR, analogA, analogB;
    signed char error;
    unsigned char reserved;
};
struct Buttons {
    unsigned held, pressed, released;
    unsigned char analogA, analogB, triggerL, triggerR;
    float analogL, analogR;
    unsigned repeat, heldFrames, repeatState[4];
};
struct Stick { float x, y, magnitude; short angle; signed char rawX, rawY; };
struct SharedPad { Buttons buttons; Stick stick, substick; };
// Canonical scalar fields, not a byte-copy image of the native gamepad.
struct ProcessedPad {
    Buttons buttons;
    Stick stick, substick;
    float meaningAxes[10];
    unsigned meaning;
    union { unsigned pressedMeaning, enabledFrameMeaning; };
    unsigned releasedMeaning;
    unsigned short analogHeld, analogPressed, analogReleased, flags;
    short stickTimer;
    int disabledFrames;
};
struct ControllerWork {
    short stickX, stickY;
    unsigned held, pressed;
    unsigned char analogR, analogL;
    float x, y, magnitude, left, right;
};
struct Input {
    unsigned cue, flags, valid;
    RawPad raw;
    ProcessedPad pad;
    // Pre-checkController memory is observational; retail leaves trigger floats uninitialized.
    ControllerWork work;
    unsigned sharedKnown;
    SharedPad shared;
};
struct Frame {
    unsigned scene, context, retrace, osTick, rngSeed, movementTick, directorState, flags;
};
struct Scene { unsigned char area, episode; unsigned short flags; };
struct StageStart {
    unsigned flags, scene;
    Scene previous, current, next;
    unsigned rngSeed, generation, headBytes, tailBytes, heapBytes;
    unsigned game, discIdentity, tvFormat, cutscene;
    unsigned npcPollutionPhase; // 0xffffffff when absent from legacy captures.
    unsigned observations; // Bits: 0 occlusion, 1 provenance, 2 GPU water height.
    // Borrowed observations only: never use this image as a native restore target.
    const unsigned char *flagBytes;
};
struct Visual {
    unsigned flags;
    int qf;
    unsigned scene;
    float x, y, z;
    short yaw;
    unsigned short animationId, animationPhase, heldNameKey;
    unsigned heldObjectId;
    unsigned char yoshi, visible;
    SusamuneGhostFluddSample fludd;
    unsigned directorTick, attempt, generation;
};
// Caller values identify recorded code sites; they are never callable addresses.
struct Rng {
    unsigned firstSeed, lastSeed, count, callerCount;
    const unsigned char *callers, *indices;
    unsigned caller, result; // Single-call kind 15, whose result need not be libc rand.
};
struct Identity { unsigned game, discIdentity, producerProtocol, region; };
struct Observation { unsigned subtype, bytes; const unsigned char *data; };
struct Event {
    Type type;
    unsigned kind, frame, tick, offset;
    union {
        Frame frameData;
        Input input;
        StageStart stage;
        Visual visual;
        Rng rng;
        Identity identity;
        GhostWorldWitness::Record world;
        MsTraceContinuation continuation;
        const unsigned char *settings;
        unsigned runFlags;
        Observation observation;
    };
};
struct Decoder {
    unsigned version, game, capabilities, error;
    const unsigned char *chunk;
    unsigned bytes, offset, frame, tick, scene, frameSeen, inputSeen, mirrorSeen,runFlags;
    unsigned char previousInput[kInputBytes], previousMirrors[80];
};
// Required capabilities are chosen by the consumer, never inferred from a build ID.
bool begin(Decoder &, unsigned version, unsigned game, unsigned capabilities,
           unsigned requiredCapabilities = 0);
// The caller keeps the checked Reader chunk leased until CHUNK_DONE.
// Pointer fields in Events borrow that chunk and expire when it is released.
bool pushChunk(Decoder &, const void *, unsigned bytes);
Result next(Decoder &, Event &);
bool sameRegion(const Decoder &, unsigned game);
bool decodeVisual(Decoder &, const void *, unsigned bytes, Visual &);
// Necessary capture evidence only; this does not establish deterministic replay.
bool hasPreStageEvidence(const Decoder &, const StageStart &, unsigned targetGame);
bool rngCall(const Rng &, unsigned index, unsigned &caller, unsigned &result, unsigned &seed);
static_assert(sizeof(SharedPad) == 80, "shared button48 + two stick16 scalars");
static_assert(sizeof(RawPad) == 12, "canonical raw controller sample");
}
