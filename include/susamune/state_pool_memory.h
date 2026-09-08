#ifndef SUSAMUNE_STATE_POOL_MEMORY_H
#define SUSAMUNE_STATE_POOL_MEMORY_H

#include "susamune/state_slot_pool.h"

/* Callers supply compiled bank addresses and sizes, never archive fields.
 * A zero second size disables that bank for an older launcher. */
typedef struct StatePoolMemory {
    unsigned char *banks[2];
    unsigned int sizes[2];
} StatePoolMemory;

typedef struct StatePoolMemorySpan {
    unsigned char *data;
    unsigned int size;
} StatePoolMemorySpan;

typedef __UINTPTR_TYPE__ StatePoolAddress;

static inline int StatePoolMemoryBufferValid(const void *data, unsigned int size) {
    return !size || (data && (StatePoolAddress)data <= ~(StatePoolAddress)0 - size);
}

static inline int StatePoolMemoryValid(const StatePoolMemory *memory) {
    if (!memory || !memory->sizes[0] ||
        memory->sizes[1] > ~0u - memory->sizes[0]) return 0;
    for (unsigned int i = 0; i < 2; ++i)
        if (!StatePoolMemoryBufferValid(memory->banks[i], memory->sizes[i])) return 0;
    if (memory->sizes[1]) {
        const StatePoolAddress a = (StatePoolAddress)memory->banks[0];
        const StatePoolAddress b = (StatePoolAddress)memory->banks[1];
        if (a < b + memory->sizes[1] && b < a + memory->sizes[0]) return 0;
    }
    return 1;
}

static inline unsigned int StatePoolMemoryCapacity(const StatePoolMemory *memory) {
    return StatePoolMemoryValid(memory) ? memory->sizes[0] + memory->sizes[1] : 0;
}

static inline int StatePoolMemoryRangeValid(const StatePoolMemory *memory,
                                           unsigned int offset, unsigned int size) {
    if (!StatePoolMemoryValid(memory)) return 0;
    const unsigned int capacity = memory->sizes[0] + memory->sizes[1];
    return offset <= capacity && size <= capacity - offset;
}

/* Returns the first physical piece of a completely validated logical range. */
static inline int StatePoolMemorySpanAt(const StatePoolMemory *memory,
                                       unsigned int offset, unsigned int size,
                                       StatePoolMemorySpan *span) {
    if (!span || !StatePoolMemoryRangeValid(memory, offset, size)) return 0;
    span->data = 0;
    span->size = 0;
    if (!size) return 1;
    unsigned int bank = 0;
    if (offset >= memory->sizes[0]) { bank = 1; offset -= memory->sizes[0]; }
    const unsigned int available = memory->sizes[bank] - offset;
    span->data = memory->banks[bank] + offset;
    span->size = size < available ? size : available;
    return 1;
}

/* External copies reject bank aliases; use logical Move for internal overlap. */
static inline int StatePoolMemoryExternalBuffer(const StatePoolMemory *memory,
                                               const void *data, unsigned int size) {
    if (!StatePoolMemoryValid(memory) || !StatePoolMemoryBufferValid(data, size)) return 0;
    if (!size) return 1;
    const StatePoolAddress address = (StatePoolAddress)data;
    for (unsigned int i = 0; i < 2; ++i) {
        const StatePoolAddress base = (StatePoolAddress)memory->banks[i];
        if (memory->sizes[i] && address < base + memory->sizes[i] && base < address + size)
            return 0;
    }
    return 1;
}

static inline int StatePoolMemoryCopyIn(const StatePoolMemory *memory,
                                       unsigned int offset, const void *source,
                                       unsigned int size) {
    if (!StatePoolMemoryRangeValid(memory, offset, size) ||
        !StatePoolMemoryExternalBuffer(memory, source, size)) return 0;
    const unsigned char *bytes = (const unsigned char *)source;
    while (size) {
        StatePoolMemorySpan span;
        if (!StatePoolMemorySpanAt(memory, offset, size, &span)) return 0;
        for (unsigned int i = 0; i < span.size; ++i) span.data[i] = bytes[i];
        bytes += span.size;
        offset += span.size;
        size -= span.size;
    }
    return 1;
}

static inline int StatePoolMemoryCopyOut(const StatePoolMemory *memory,
                                        unsigned int offset, void *destination,
                                        unsigned int size) {
    if (!StatePoolMemoryRangeValid(memory, offset, size) ||
        !StatePoolMemoryExternalBuffer(memory, destination, size)) return 0;
    unsigned char *bytes = (unsigned char *)destination;
    while (size) {
        StatePoolMemorySpan span;
        if (!StatePoolMemorySpanAt(memory, offset, size, &span)) return 0;
        for (unsigned int i = 0; i < span.size; ++i) bytes[i] = span.data[i];
        bytes += span.size;
        offset += span.size;
        size -= span.size;
    }
    return 1;
}

/* Direction follows logical offsets; the second physical bank may be lower. */
static inline int StatePoolMemoryMove(const StatePoolMemory *memory,
                                     unsigned int destination, unsigned int source,
                                     unsigned int size) {
    if (!StatePoolMemoryRangeValid(memory, destination, size) ||
        !StatePoolMemoryRangeValid(memory, source, size)) return 0;
    if (destination == source) return 1;
    while (size) {
        StatePoolMemorySpan from, to;
        unsigned int count;
        if (destination < source) {
            if (!StatePoolMemorySpanAt(memory, source, size, &from) ||
                !StatePoolMemorySpanAt(memory, destination, size, &to)) return 0;
            count = from.size < to.size ? from.size : to.size;
            for (unsigned int i = 0; i < count; ++i) to.data[i] = from.data[i];
            destination += count;
            source += count;
        } else {
            const unsigned int lastSource = source + size - 1;
            const unsigned int lastDestination = destination + size - 1;
            if (!StatePoolMemorySpanAt(memory, lastSource, 1, &from) ||
                !StatePoolMemorySpanAt(memory, lastDestination, 1, &to)) return 0;
            const unsigned int firstSize = memory->sizes[0];
            const unsigned int a = lastSource - (lastSource < firstSize ? 0 : firstSize) + 1;
            const unsigned int b = lastDestination - (lastDestination < firstSize ? 0 : firstSize) + 1;
            count = a < b ? a : b;
            if (count > size) count = size;
            unsigned char *dst = to.data - (count - 1);
            const unsigned char *src = from.data - (count - 1);
            unsigned int left = count;
            while (left) { --left; dst[left] = src[left]; }
        }
        size -= count;
    }
    return 1;
}

static inline int StateSlotPoolClearBanked(StateSlotPool *pool,
                                          const StatePoolMemory *memory,
                                          unsigned int slot) {
    const unsigned int capacity = StatePoolMemoryCapacity(memory);
    if (!capacity || !StateSlotPoolValid(pool, capacity) || slot >= STATE_SLOT_POOL_COUNT ||
        !pool->slots[slot].size) return 0;
    const unsigned int offset = pool->slots[slot].offset;
    const unsigned int size = pool->slots[slot].size;
    if (!StatePoolMemoryMove(memory, offset, offset + size, pool->used - offset - size))
        __builtin_trap();
    for (unsigned int i = 0; i < STATE_SLOT_POOL_COUNT; ++i)
        if (pool->slots[i].size && pool->slots[i].offset > offset)
            pool->slots[i].offset -= size;
    pool->slots[slot].offset = pool->slots[slot].size = 0;
    pool->used -= size;
    return 1;
}

static inline int StateSlotPoolReclaimForReplaceBanked(StateSlotPool *pool,
    const StatePoolMemory *memory, unsigned int slot, unsigned int packedSize) {
    const unsigned int capacity = StatePoolMemoryCapacity(memory);
    if (!capacity || StateSlotPoolPlanReplace(pool, capacity, slot, packedSize, 0) ==
                         STATE_SLOT_REPLACE_REFUSE) return 0;
    return pool->slots[slot].size ? StateSlotPoolClearBanked(pool, memory, slot) : 1;
}

static inline int StateSlotPoolCommitPreparedBanked(StateSlotPool *pool,
    const StatePoolMemory *memory, unsigned int slot, unsigned int packedSize) {
    const unsigned int capacity = StatePoolMemoryCapacity(memory);
    return capacity && StateSlotPoolCommitPrepared(pool, capacity, slot, packedSize);
}

static inline int StateSlotPoolCommitBanked(StateSlotPool *pool,
    const StatePoolMemory *memory, unsigned int slot, unsigned int packedSize,
    const unsigned char *staging, unsigned int stagingSize) {
    const unsigned int capacity = StatePoolMemoryCapacity(memory);
    const unsigned int first = packedSize < stagingSize ? packedSize : stagingSize;
    if (!capacity || !StateSlotPoolCanCommit(pool, capacity, slot, packedSize, stagingSize) ||
        !StatePoolMemoryExternalBuffer(memory, staging, first)) return 0;
    const unsigned int oldUsed = pool->used;
    if (pool->slots[slot].size && !StateSlotPoolClearBanked(pool, memory, slot))
        __builtin_trap();
    if (!StatePoolMemoryMove(memory, pool->used + first, oldUsed, packedSize - first) ||
        !StatePoolMemoryCopyIn(memory, pool->used, staging, first) ||
        !StateSlotPoolCommitPreparedBanked(pool, memory, slot, packedSize)) __builtin_trap();
    return 1;
}

#endif
