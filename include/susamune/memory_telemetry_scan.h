#ifndef MOONSHINE_MEMORY_TELEMETRY_SCAN_H
#define MOONSHINE_MEMORY_TELEMETRY_SCAN_H

struct MemoryPoolSample { unsigned capacity, used, largestFree, tailExtent; };
static inline bool MemoryReadable(unsigned p, unsigned bytes) {
    return !(p & 3u) && p >= 0x80000000u && p <= 0x81800000u - bytes;
}
// Bounded walks reject partly updated lists; sampling must never call an allocator.
template<class Read> bool MemoryWaveSample(unsigned root, Read read, MemoryPoolSample &out) {
    if (!MemoryReadable(root, 44)) return false;
    const unsigned base = read(root + 8), size = read(root + 16), expected = read(root) & 0xffffu;
    if ((read(root) >> 24) != 1 || base < 0x4000u || base >= 0x1000000u ||
        !size || size > 0x1000000u - base || expected > 128) return false;
    MemoryPoolSample value = {size, 0, 0, 0};
    unsigned node = read(root + 20), count = 0, cursor = base;
    while (node && count < 128) {
        if (!MemoryReadable(node, 44) || read(node + 24) != root) return false;
        const unsigned at = read(node + 8), length = read(node + 16);
        if (!length || at < cursor || at > base + size || length > base + size - at) return false;
        const unsigned gap = at - cursor;
        if (gap > value.largestFree) value.largestFree = gap;
        value.used += length; cursor = at + length;
        node = read(node + 28); ++count;
    }
    if (node || count != expected) return false;
    value.tailExtent = cursor - base;
    if (base + size - cursor > value.largestFree) value.largestFree = base + size - cursor;
    out = value; return true;
}
template<class Read> bool MemoryArchiveSample(unsigned manager, unsigned list, Read read, MemoryPoolSample &out) {
    if (!MemoryReadable(manager, 0x70) || !MemoryReadable(list, 12)) return false;
    const unsigned base = read(manager + 0x68), size = read(manager + 0x6c);
    if (read(manager + 0x60) != 0x4000u || read(manager + 0x64) != 0xf40000u ||
        base != 0xf44000u || size != 0xbc000u) return false;
    unsigned node = read(list), count = 0, previous = 0, cursor = base;
    const unsigned expected = read(list + 8);
    if (!expected || expected > 128) return false;
    MemoryPoolSample value = {size, 0, 0, 0};
    while (node && count < 128) {
        if (!MemoryReadable(node, 16) || node < 0x80000004u) return false;
        const unsigned block = read(node);
        if (block != node - 4 || !MemoryReadable(block, 36) ||
            read(node + 4) != list || read(node + 8) != previous) return false;
        const unsigned at = read(block + 20), length = read(block + 24), gap = read(block + 28);
        if (at != cursor || at > base + size || length > base + size - at ||
            gap > base + size - at - length) return false;
        value.used += length;
        if (length) value.tailExtent = at + length - base;
        if (gap > value.largestFree) value.largestFree = gap;
        cursor = at + length + gap; previous = node;
        node = read(node + 12); ++count;
    }
    if (node || count != expected || cursor != base + size || read(list + 4) != previous) return false;
    out = value; return true;
}
template<class Read> bool MemoryExpSample(unsigned heap, unsigned vtable, Read read, MemoryPoolSample &out) {
    if (!MemoryReadable(heap, 0x84) || read(heap) != vtable) return false;
    const unsigned base = read(heap + 0x30), end = read(heap + 0x34), size = read(heap + 0x38);
    if (!MemoryReadable(base, 0) || !MemoryReadable(end, 0) || end < base || size != end - base) return false;
    unsigned node = read(heap + 0x74), previous = 0, previousEnd = base, free = 0, largest = 0, count = 0;
    while (node && count++ < 256) {
        if (!MemoryReadable(node, 16) || node < previousEnd || node > end || end - node < 16 || read(node + 8) != previous) return false;
        const unsigned bytes = read(node + 4);
        if (bytes > end - node - 16 || free > size - bytes) return false;
        free += bytes; if (bytes > largest) largest = bytes;
        previousEnd = node + 16 + bytes; previous = node; node = read(node + 12);
    }
    if (node || read(heap + 0x78) != previous) return false;
    out = {size, size - free, largest, 0}; return true;
}
#endif
