#ifndef SUSAMUNE_STATE_QUICK_PRODUCER_HXX
#define SUSAMUNE_STATE_QUICK_PRODUCER_HXX
#include "state_root_reader.h"

struct TWQuickProducer {
    const TWStageMemory *memory;
    TWStageToken token;
};

static inline bool TWQuickEmit(void *context, const StateCodec::ReadSpan (&encoded)[2]) {
    const TWQuickProducer *producer = static_cast<const TWQuickProducer *>(context);
    return TWRAppendParts(producer->memory, producer->token,
        static_cast<const unsigned char *>(encoded[0].data), encoded[0].size,
        static_cast<const unsigned char *>(encoded[1].data), encoded[1].size);
}

static inline bool TWQuickSeparate(const void *a, unsigned int as, const void *b, unsigned int bs) {
    return TWBankBufferValid(a, as) && TWBankBufferValid(b, bs) &&
        ((TWBankAddress)a + as <= (TWBankAddress)b || (TWBankAddress)b + bs <= (TWBankAddress)a);
}

/* Begin under one exclusive lease before calling. Any refusal leaves the old
 * roots intact; Abort the candidate. Validate decoded state before Commit. */
static inline StateCodec::Result TWQuickProduce(const TWStageMemory *memory, TWStageToken token,
    void *workspace, unsigned int workspaceBytes,
    const StateCodec::ReadSpan *source, unsigned int sourceCount,
    StateCodec::ZeroRange zero = {}) {
    if (!TWRIdle(memory) || !TWSLayout(memory) || !TWSTokenMatches(memory, token) ||
        !TWQuickSeparate(workspace, workspaceBytes, memory, sizeof(*memory)) ||
        !TWQuickSeparate(workspace, workspaceBytes, memory->pool, sizeof(*memory->pool)))
        return {StateCodec::INVALID_ARGUMENT, 0, 0, 0};
    StateCodec::WriteSpan destinations[TW_BANK_MAX + 1];
    unsigned int count = memory->pool->count;
    for (unsigned int i = 0; i < count; ++i)
        destinations[i] = {memory->pool->banks[i], memory->pool->sizes[i]};
    if (memory->size) destinations[count++] = {memory->staging, memory->size};
    TWQuickProducer producer = {memory, token};
    return StateCodec::compressQuickBlocks(workspace, workspaceBytes, source, sourceCount,
        destinations, count, TWQuickEmit, &producer, zero);
}
#endif
