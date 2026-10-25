#include "susamune/live_playlist.hxx"
#include "susamune/live_race_wire.h"

namespace LivePlaylist {
unsigned hash(const Plan &plan) {
    unsigned value = 2166136261u;
    value = (value ^ 1u) * 16777619u;
    value = (value ^ plan.count) * 16777619u;
    value = (value ^ plan.fastAny) * 16777619u;
    for (unsigned i = 0; i < plan.count; ++i) {
        value = (value ^ plan.items[i].entry) * 16777619u;
        value = (value ^ plan.items[i].episode) * 16777619u;
    }
    return value;
}
unsigned encode(const Plan &plan, unsigned offset, unsigned char *out) {
    if (!plan.count || plan.count > Capacity || offset >= plan.count) return 0;
    const unsigned count = plan.count - offset > ChunkItems ? ChunkItems : plan.count - offset;
    out[0] = Message; out[1] = offset; out[2] = count; out[3] = plan.count;
    MSRWrite32(out + 4, hash(plan));
    out[8] = plan.fastAny; out[9] = 1; out[10] = out[11] = 0;
    for (unsigned i = 0; i < count; ++i) {
        out[12 + i * 2] = plan.items[offset + i].entry;
        out[13 + i * 2] = plan.items[offset + i].episode;
    }
    return HeaderBytes + 2 * count;
}
bool receive(Transfer &state, const unsigned char *data, unsigned bytes,
             unsigned expectedHash, unsigned entryCount) {
    if (bytes < HeaderBytes || data[0] != Message || !data[2] || data[2] > ChunkItems ||
        !data[3] || data[3] > Capacity || data[1] + data[2] > data[3] ||
        bytes != HeaderBytes + 2u * data[2] || MSRRead32(data + 4) != expectedHash ||
        data[8] > 1 || data[9] != 1 || data[10] || data[11]) return false;
    for (unsigned i = 0; i < data[2]; ++i) {
        if (data[12 + 2 * i] >= entryCount || (data[13 + 2 * i] & 0x78u)) return false;
    }
    if (!data[1]) {
        state.received = 0; state.complete = false;
        state.plan.count = data[3]; state.plan.fastAny = data[8]; state.hash = expectedHash;
    }
    if (state.hash != expectedHash || state.received != data[1] ||
        state.plan.count != data[3] || state.plan.fastAny != data[8]) return false;
    for (unsigned i = 0; i < data[2]; ++i) {
        state.plan.items[state.received + i].entry = data[12 + 2 * i];
        state.plan.items[state.received + i].episode = data[13 + 2 * i];
    }
    state.received += data[2];
    if (state.received == state.plan.count) state.complete = hash(state.plan) == expectedHash;
    return state.received != state.plan.count || state.complete;
}
}
