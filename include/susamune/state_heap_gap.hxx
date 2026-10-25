#ifndef SUSAMUNE_STATE_HEAP_GAP_HXX
#define SUSAMUNE_STATE_HEAP_GAP_HXX

#include "state_codec.hxx"

namespace StateHeapGap {
typedef unsigned int Word __attribute__((__may_alias__));
typedef const Word *(*ReadHeader)(unsigned int address, unsigned int bytes, void *context);

// Call with PPC scheduling stopped. A failed check retains the original bytes.
inline StateCodec::ZeroRange inspect(unsigned int address, unsigned int bytes,
    unsigned int vtable, unsigned int rawOffset, ReadHeader read, void *context) {
    const StateCodec::ZeroRange none = {};
    if (!read || !vtable || (address & 3u) || address < 0x80003100u ||
        address >= 0x81800000u || bytes < 0x78u || bytes > 0x81800000u - address ||
        rawOffset > 0xffffffffu - bytes) return none;
    const Word *h = read(address, 0x78u, context);
    if (!h || h[0] != vtable || h[0x18/4] || h[0x1c/4] || h[0x20/4] || h[0x24/4] ||
        h[0x74/4]) return none;
    const unsigned int start = h[0x30/4], end = h[0x34/4];
    const unsigned int head = h[0x6c/4], tail = h[0x70/4];
    if (start < address + 0x78u || start > head || head > tail || tail > end ||
        end != address + bytes || h[0x38/4] != end - start ||
        h[0x68/4] != tail - head || head == tail) return none;

    // Explicit-buffer child heaps need not reserve their storage from the parent.
    const unsigned int count = h[0x44/4], last = h[0x40/4];
    unsigned int link = h[0x3c/4], previous = 0;
    if (count > 64u) return none;
    for (unsigned int i = 0; i < count; ++i) {
        if ((link & 3u) || link < 0x80003148u || link > 0x81800000u - 0x20u) return none;
        const unsigned int child = link - 0x48u;
        const Word *c = read(child, 0x68u, context);
        if (!c || c[0x48/4] != child || c[0x4c/4] != address + 0x3cu ||
            c[0x50/4] != previous) return none;
        const unsigned int childStart = c[0x30/4], childEnd = c[0x34/4];
        if (childStart < child + 0x68u || childEnd < childStart || childEnd > 0x81800000u ||
            c[0x38/4] != childEnd - childStart ||
            (child < tail && head < child + 0x68u) ||
            (childStart < tail && head < childEnd)) return none;
        previous = link;
        link = c[0x54/4];
    }
    if (link || previous != last) return none;
    return {rawOffset + (head - address), tail - head};
}
}
#endif
