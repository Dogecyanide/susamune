#pragma once
namespace GhostTraceInitialFlags {

enum { kImageBytes = 896, kCardBits = 948, kGameBits = 29, kStageBits = 100 };

// This is a semantic snapshot, not the native FlagManager image.
struct Snapshot {
    int cardInts[21], gameInts[5], stageInts[100];
    unsigned char cardBools[119], gameBools[4], stageBools[13];
};
static_assert(sizeof(int) == 4 && sizeof(Snapshot) == 640, "initial flag snapshot layout");

struct Access {
    void* context;
    int (*getFlag)(void*, unsigned);
    void (*setFlag)(void*, unsigned, int);
};

// The caller supplies the actual scenario-table count and freezes game updates.
bool validate(const Snapshot&, unsigned scenarioCount);
bool decode(Snapshot& out, const unsigned char* image, unsigned bytes, unsigned scenarioCount);
bool capture(Snapshot& out, const Access&);
// Comparison never applies file values and permits all live integer states.
bool matchesImage(const unsigned char* image, unsigned bytes, const Access&);
bool apply(const Snapshot&, unsigned scenarioCount, const Access&);

// Only a trusted capture may use this path; incoming value limits do not apply.
bool restore(const Snapshot& backup, const Access&);

}
