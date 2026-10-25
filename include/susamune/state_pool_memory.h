#ifndef SUSAMUNE_STATE_POOL_MEMORY_H
#define SUSAMUNE_STATE_POOL_MEMORY_H

#include "susamune/state_slot_pool.h"

/* Callers supply compiled bank addresses and sizes, never archive fields.
 * Zero sizes disable banks for older launchers. */
enum { STATE_POOL_MEMORY_BANKS = 5 };
typedef struct StatePoolMemory {
    unsigned char *banks[STATE_POOL_MEMORY_BANKS];
    unsigned int sizes[STATE_POOL_MEMORY_BANKS];
} StatePoolMemory;

typedef struct StatePoolMemorySpan {
    unsigned char *data;
    unsigned int size;
} StatePoolMemorySpan;

typedef __UINTPTR_TYPE__ StatePoolAddress;

#ifdef __cplusplus
#define SUSAMUNE_POOL_SHARED_INLINE inline
#else
#define SUSAMUNE_POOL_SHARED_INLINE static inline
#endif

SUSAMUNE_POOL_SHARED_INLINE int StatePoolMemoryBufferValid(const void *data, unsigned int size) {
    return !size || (data && (StatePoolAddress)data <= ~(StatePoolAddress)0 - size);
}

SUSAMUNE_POOL_SHARED_INLINE int StatePoolMemoryValid(const StatePoolMemory *memory) {
    if (!memory || !memory->sizes[0]) return 0;
    unsigned int total = 0;
    for (unsigned int i = 0; i < STATE_POOL_MEMORY_BANKS; ++i) {
        const unsigned int size = memory->sizes[i];
        if (size > ~0u - total || !StatePoolMemoryBufferValid(memory->banks[i], size)) return 0;
        total += size;
        if (!size) continue;
        const StatePoolAddress a = (StatePoolAddress)memory->banks[i];
        for (unsigned int j = 0; j < i; ++j) {
            const StatePoolAddress b = (StatePoolAddress)memory->banks[j];
            if (memory->sizes[j] && a < b + memory->sizes[j] && b < a + size) return 0;
        }
    }
    return 1;
}

static inline unsigned int StatePoolMemoryCapacity(const StatePoolMemory *memory) {
    if (!StatePoolMemoryValid(memory)) return 0;
    unsigned int total = 0;
    for (unsigned int i = 0; i < STATE_POOL_MEMORY_BANKS; ++i) total += memory->sizes[i];
    return total;
}

SUSAMUNE_POOL_SHARED_INLINE int StatePoolMemoryRangeValid(const StatePoolMemory *memory,
                                           unsigned int offset, unsigned int size) {
    const unsigned int capacity = StatePoolMemoryCapacity(memory);
    return capacity && offset <= capacity && size <= capacity - offset;
}

/* Returns the first physical piece of a completely validated logical range. */
static inline int StatePoolMemorySpanAt(const StatePoolMemory *memory,
                                       unsigned int offset, unsigned int size,
                                       StatePoolMemorySpan *span) {
    if (!span || !StatePoolMemoryRangeValid(memory, offset, size)) return 0;
    span->data = 0;
    span->size = 0;
    if (!size) return 1;
    for (unsigned int bank = 0; bank < STATE_POOL_MEMORY_BANKS; ++bank) {
        if (offset < memory->sizes[bank]) {
            const unsigned int available = memory->sizes[bank] - offset;
            span->data = memory->banks[bank] + offset;
            span->size = size < available ? size : available;
            return 1;
        }
        offset -= memory->sizes[bank];
    }
    return 0;
}

/* External copies reject bank aliases; use logical Move for internal overlap. */
static inline int StatePoolMemoryExternalBuffer(const StatePoolMemory *memory,
                                               const void *data, unsigned int size) {
    if (!StatePoolMemoryValid(memory) || !StatePoolMemoryBufferValid(data, size)) return 0;
    if (!size) return 1;
    const StatePoolAddress address = (StatePoolAddress)data;
    for (unsigned int i = 0; i < STATE_POOL_MEMORY_BANKS; ++i) {
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
        StateSlotPoolCopyForward(span.data, bytes, span.size);
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
        StateSlotPoolCopyForward(bytes, span.data, span.size);
        bytes += span.size;
        offset += span.size;
        size -= span.size;
    }
    return 1;
}

/* Direction follows logical offsets, independent of physical bank order. */
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
            StateSlotPoolCopyForward(to.data, from.data, count);
            destination += count;
            source += count;
        } else {
            const unsigned int lastSource = source + size - 1;
            const unsigned int lastDestination = destination + size - 1;
            if (!StatePoolMemorySpanAt(memory, lastSource, 1, &from) ||
                !StatePoolMemorySpanAt(memory, lastDestination, 1, &to)) return 0;
            unsigned int a = lastSource, b = lastDestination;
            for (unsigned int i = 0; i < STATE_POOL_MEMORY_BANKS; ++i) {
                if (a < memory->sizes[i]) break;
                a -= memory->sizes[i];
            }
            for (unsigned int i = 0; i < STATE_POOL_MEMORY_BANKS; ++i) {
                if (b < memory->sizes[i]) break;
                b -= memory->sizes[i];
            }
            ++a; ++b;
            count = a < b ? a : b;
            if (count > size) count = size;
            unsigned char *dst = to.data - (count - 1);
            const unsigned char *src = from.data - (count - 1);
            StateSlotPoolCopyBackward(dst, src, count);
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

#undef SUSAMUNE_POOL_SHARED_INLINE
#endif
