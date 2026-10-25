#ifndef TIMEWARP_STATE_MULTIBANK_MEMORY_H
#define TIMEWARP_STATE_MULTIBANK_MEMORY_H

#include "susamune/state_slot_pool.h"

/* Bank order is logical, independent of physical addresses. */
enum { TW_BANK_MAX = 5 };
typedef __UINTPTR_TYPE__ TWBankAddress;
typedef struct TWBankMemory {
    unsigned char *banks[TW_BANK_MAX];
    unsigned int sizes[TW_BANK_MAX], count;
} TWBankMemory;
typedef struct TWBankSpan { unsigned char *data; unsigned int size; } TWBankSpan;

static inline int TWBankBufferValid(const void *data, unsigned int size) {
    return !size || (data && (TWBankAddress)data <= ~(TWBankAddress)0 - size);
}

static inline int TWBankValid(const TWBankMemory *memory) {
    if (!memory || !memory->count || memory->count > TW_BANK_MAX) return 0;
    unsigned int total = 0;
    for (unsigned int i = 0; i < TW_BANK_MAX; ++i) {
        if (i >= memory->count) {
            if (memory->banks[i] || memory->sizes[i]) return 0;
            continue;
        }
        const unsigned int size = memory->sizes[i];
        const TWBankAddress base = (TWBankAddress)memory->banks[i];
        if (!size || size > ~0u - total || !TWBankBufferValid(memory->banks[i], size)) return 0;
        for (unsigned int j = 0; j < i; ++j) {
            const TWBankAddress other = (TWBankAddress)memory->banks[j];
            if (base < other + memory->sizes[j] && other < base + size) return 0;
        }
        total += size;
    }
    return 1;
}

static inline unsigned int TWBankCapacity(const TWBankMemory *memory) {
    if (!TWBankValid(memory)) return 0;
    unsigned int total = 0;
    for (unsigned int i = 0; i < memory->count; ++i) total += memory->sizes[i];
    return total;
}

static inline int TWBankRangeValid(const TWBankMemory *memory, unsigned int offset,
                                  unsigned int size) {
    const unsigned int total = TWBankCapacity(memory);
    return total && offset <= total && size <= total - offset;
}

static inline int TWBankSpanAt(const TWBankMemory *memory, unsigned int offset,
                              unsigned int size, TWBankSpan *span) {
    if (!span || !TWBankRangeValid(memory, offset, size)) return 0;
    span->data = 0; span->size = 0;
    if (!size) return 1;
    for (unsigned int i = 0; i < memory->count; ++i) {
        if (offset < memory->sizes[i]) {
            span->data = memory->banks[i] + offset;
            const unsigned int available = memory->sizes[i] - offset;
            span->size = size < available ? size : available;
            return 1;
        }
        offset -= memory->sizes[i];
    }
    return 0;
}

static inline int TWBankExternalBuffer(const TWBankMemory *memory, const void *data,
                                      unsigned int size) {
    if (!TWBankValid(memory) || !TWBankBufferValid(data, size)) return 0;
    if (!size) return 1;
    const TWBankAddress address = (TWBankAddress)data;
    for (unsigned int i = 0; i < memory->count; ++i) {
        const TWBankAddress base = (TWBankAddress)memory->banks[i];
        if (address < base + memory->sizes[i] && base < address + size) return 0;
    }
    return 1;
}

static inline int TWBankCopyIn(const TWBankMemory *memory, unsigned int offset,
                              const void *source, unsigned int size) {
    if (!TWBankRangeValid(memory, offset, size) ||
        !TWBankExternalBuffer(memory, source, size)) return 0;
    const unsigned char *bytes = (const unsigned char *)source;
    while (size) {
        TWBankSpan span;
        if (!TWBankSpanAt(memory, offset, size, &span)) return 0;
        StateSlotPoolCopyForward(span.data, bytes, span.size);
        bytes += span.size; offset += span.size; size -= span.size;
    }
    return 1;
}

/* Move direction follows logical offsets even when physical banks descend. */
static inline int TWBankMove(const TWBankMemory *memory, unsigned int destination,
                            unsigned int source, unsigned int size) {
    if (!TWBankRangeValid(memory, destination, size) ||
        !TWBankRangeValid(memory, source, size)) return 0;
    if (destination == source) return 1;
    while (size) {
        TWBankSpan from, to;
        unsigned int count;
        if (destination < source) {
            if (!TWBankSpanAt(memory, source, size, &from) ||
                !TWBankSpanAt(memory, destination, size, &to)) return 0;
            count = from.size < to.size ? from.size : to.size;
            StateSlotPoolCopyForward(to.data, from.data, count);
            source += count; destination += count;
        } else {
            unsigned int a = source + size - 1, b = destination + size - 1;
            if (!TWBankSpanAt(memory, a, 1, &from) || !TWBankSpanAt(memory, b, 1, &to)) return 0;
            for (unsigned int i = 0; a >= memory->sizes[i]; ++i) a -= memory->sizes[i];
            for (unsigned int i = 0; b >= memory->sizes[i]; ++i) b -= memory->sizes[i];
            count = a < b ? a + 1 : b + 1;
            if (count > size) count = size;
            StateSlotPoolCopyBackward(to.data - count + 1, from.data - count + 1, count);
        }
        size -= count;
    }
    return 1;
}
#endif
