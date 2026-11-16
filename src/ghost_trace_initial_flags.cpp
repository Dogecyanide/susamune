#include "susamune/ghost_trace_initial_flags.hxx"

namespace GhostTraceInitialFlags {
namespace {

int readInt(const unsigned char* p) {
    const unsigned value = static_cast<unsigned>(p[0]) << 24 |
        static_cast<unsigned>(p[1]) << 16 | static_cast<unsigned>(p[2]) << 8 | p[3];
    return value <= 0x7fffffffu ? static_cast<int>(value) : -1 - static_cast<int>(~value);
}

void decodeInts(int* out, const unsigned char* image, unsigned count) {
    for (unsigned i = 0; i < count; ++i) out[i] = readInt(image + 4 * i);
}

void decodeBools(unsigned char* out, const unsigned char* image, unsigned count) {
    const unsigned bytes = (count + 7) / 8;
    for (unsigned i = 0; i < bytes; ++i) out[i] = image[i];
    if (count & 7) out[bytes - 1] &= (1u << (count & 7)) - 1;
}



void captureInts(int* out, unsigned first, unsigned count, const Access& access) {
    for (unsigned i = 0; i < count; ++i) out[i] = access.getFlag(access.context, first + i);
}

bool captureBools(unsigned char* out, unsigned first, unsigned count, const Access& access) {
    for (unsigned i = 0; i < (count + 7) / 8; ++i) out[i] = 0;
    for (unsigned i = 0; i < count; ++i) {
        const int value = access.getFlag(access.context, first + i);
        if (value != 0 && value != 1) return false;
        out[i >> 3] |= static_cast<unsigned>(value) << (i & 7);
    }
    return true;
}

void writeInts(const int* values, unsigned first, unsigned count, const Access& access) {
    for (unsigned i = 0; i < count; ++i) access.setFlag(access.context, first + i, values[i]);
}

void writeBools(const unsigned char* bits, unsigned first, unsigned count, const Access& access) {
    for (unsigned i = 0; i < count; ++i)
        access.setFlag(access.context, first + i, (bits[i >> 3] >> (i & 7)) & 1u);
}

}

bool validate(const Snapshot& value, unsigned scenarioCount) {
    if (!scenarioCount || scenarioCount > 256 || (value.cardBools[118] & 0xf0u) ||
        (value.gameBools[3] & 0xe0u) || (value.stageBools[12] & 0xf0u)) return false;

    // Negative scores can become indices in the retail digit renderer.
    const int* card = value.cardInts;
    if (static_cast<unsigned>(card[0]) > 0x7ffffffeu || static_cast<unsigned>(card[1]) > 99 ||
        static_cast<unsigned>(card[2]) > 3500 || static_cast<unsigned>(card[3]) > 3000 ||
        static_cast<unsigned>(card[4]) > 3000 || static_cast<unsigned>(card[20]) > 4000) return false;
    for (unsigned i = 5; i < 20; ++i) if (static_cast<unsigned>(card[i]) > 999) return false;

    const int* game = value.gameInts;
    // Practice can clear a shine flag without changing the displayed total.
    if (static_cast<unsigned>(game[0]) > 120 || static_cast<unsigned>(game[1]) > 750 ||
        game[2] < 0 || game[2] > 999 || game[3] < 0 ||
        static_cast<unsigned>(game[3]) >= scenarioCount || (static_cast<unsigned>(game[4]) > 5 || game[4] == 3)) return false;

    // Initial snapshots precede retail's stage reset; red-coin progress can remain from the previous area.
    if (static_cast<unsigned>(value.stageInts[0]) > 8 || value.stageInts[3] < 0 || value.stageInts[3] > 3) return false;
    for (unsigned i = 1; i < 100; ++i) if (i != 3 && value.stageInts[i]) return false;
    return true;
}

bool decode(Snapshot& out, const unsigned char* image, unsigned bytes, unsigned scenarioCount) {
    if (!image || bytes != kImageBytes) return false;
    Snapshot candidate;
    decodeBools(candidate.cardBools, image, kCardBits);
    decodeInts(candidate.cardInts, image + 0x078, 21);
    decodeBools(candidate.gameBools, image + 0x0cc, kGameBits);
    decodeInts(candidate.gameInts, image + 0x0d0, 5);
    decodeBools(candidate.stageBools, image + 0x0e4, kStageBits);
    decodeInts(candidate.stageInts, image + 0x0f4, 100);
    if (!validate(candidate, scenarioCount)) return false;
    out = candidate;
    return true;
}

bool capture(Snapshot& out, const Access& access) {
    if (!access.getFlag) return false;
    Snapshot candidate;
    if (!captureBools(candidate.cardBools, 0x10000, kCardBits, access) ||
        !captureBools(candidate.gameBools, 0x30000, kGameBits, access) ||
        !captureBools(candidate.stageBools, 0x50000, kStageBits, access)) return false;
    captureInts(candidate.cardInts, 0x20000, 21, access);
    captureInts(candidate.gameInts, 0x40000, 5, access);
    captureInts(candidate.stageInts, 0x60000, 100, access);
    out = candidate;
    return true;
}

bool matchesImage(const unsigned char* image,unsigned bytes,const Access& access) {
    if(!image||bytes!=kImageBytes||!access.getFlag)return false;
    const unsigned offsets[]={0,0x078,0x0cc,0x0d0,0x0e4,0x0f4};
    const unsigned counts[]={kCardBits,21,kGameBits,5,kStageBits,100};
    for(unsigned group=0;group<6;++group)for(unsigned i=0;i<counts[group];++i) {
        const int expected=(group&1)?readInt(image+offsets[group]+4*i):
            ((image[offsets[group]+(i>>3)]>>(i&7))&1u);
        if(access.getFlag(access.context,((group+1)<<16)+i)!=expected)return false;
    }
    return true;
}
bool restore(const Snapshot& value, const Access& access) {
    if (!access.setFlag) return false;
    writeBools(value.cardBools, 0x10000, kCardBits, access);
    writeBools(value.gameBools, 0x30000, kGameBits, access);
    writeBools(value.stageBools, 0x50000, kStageBits, access);
    writeInts(value.cardInts, 0x20000, 21, access);
    writeInts(value.gameInts, 0x40000, 5, access);
    writeInts(value.stageInts, 0x60000, 100, access);
    return true;
}

bool apply(const Snapshot& value, unsigned scenarioCount, const Access& access) {
    return validate(value, scenarioCount) && restore(value, access);
}

}
