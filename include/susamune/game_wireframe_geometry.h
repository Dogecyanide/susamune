#pragma once

namespace GameWireframeGeometry {
using Byte = unsigned char;
constexpr unsigned kMaxListBytes = 1024 * 1024;
constexpr unsigned kMaxStride = 160;
constexpr unsigned kBatchVertices = 60000;

inline unsigned read16(const Byte *p) { return (unsigned(p[0]) << 8) | p[1]; }
inline unsigned read32(const Byte *p) {
    return (unsigned(p[0]) << 24) | (unsigned(p[1]) << 16) |
           (unsigned(p[2]) << 8) | p[3];
}
inline unsigned scalarBytes(unsigned type) {
    return type < 2 ? 1 : type < 4 ? 2 : type == 4 ? 4 : 0;
}
inline unsigned attributeBytes(unsigned mode, unsigned direct, unsigned indices = 1) {
    return mode == 0 ? 0 : mode == 1 ? direct : (mode - 1) * indices;
}

// J3D writes these commands directly, bypassing the SDK's cached VCD/VAT.
inline unsigned descriptorStride(const Byte *data, unsigned size) {
    if (!data || size != 0xc0) return 0;
    unsigned regs[5] = {}, seen = 0;
    for (unsigned pos = 0; pos < size;) {
        const unsigned command = data[pos++];
        if (!command) continue;
        if (command == 0x08) {
            if (size - pos < 5) return 0;
            const unsigned id = data[pos++], value = read32(data + pos);
            pos += 4;
            if (id >= 0x50 && id <= 0x90 && !(id & 15)) {
                const unsigned index = (id - 0x50) >> 4;
                regs[index] = value;
                seen |= 1u << index;
            } else if (!((id >= 0xa0 && id <= 0xab) || (id >= 0xb0 && id <= 0xbb))) {
                return 0;
            }
        } else if (command == 0x10) {
            if (size - pos < 8 || read32(data + pos) != 0x1008) return 0;
            pos += 8;
        } else return 0;
    }
    if (seen != 31 || (regs[0] >> 17) || (regs[1] >> 16)) return 0;
    const unsigned lo = regs[0], hi = regs[1], a = regs[2], b = regs[3], c = regs[4];
    if (!((lo >> 9) & 3)) return 0;
    unsigned stride = 0;
    for (unsigned i = 0; i < 9; ++i) stride += (lo >> i) & 1;
    const unsigned posBytes = scalarBytes((a >> 1) & 7);
    const unsigned nrmBytes = scalarBytes((a >> 10) & 7);
    if (!posBytes || (!nrmBytes && ((lo >> 11) & 3))) return 0;
    stride += attributeBytes((lo >> 9) & 3, (2 + (a & 1)) * posBytes);
    const bool nbt = a & (1u << 9), index3 = a & (1u << 31);
    if (index3 && !nbt) return 0;
    stride += attributeBytes((lo >> 11) & 3, (nbt ? 9 : 3) * nrmBytes, index3 ? 3 : 1);
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned mode = (lo >> (13 + i * 2)) & 3;
        const unsigned type = (a >> (14 + i * 4)) & 7;
        if (mode && type > 5) return 0;
        const unsigned bytes = type == 0 || type == 3 ? 2 : type == 1 || type == 4 ? 3 : 4;
        stride += attributeBytes(mode, bytes);
    }
    for (unsigned i = 0; i < 8; ++i) {
        const unsigned fmt = i == 0 ? a >> 21 : i < 5 ? b >> ((i - 1) * 9) : c >> (5 + (i - 5) * 9);
        const unsigned mode = (hi >> (i * 2)) & 3;
        const unsigned bytes = scalarBytes((fmt >> 1) & 7);
        if (mode && !bytes) return 0;
        stride += attributeBytes(mode, (1 + (fmt & 1)) * bytes);
    }
    return stride <= kMaxStride ? stride : 0;
}

inline unsigned edgeVertices(unsigned primitive, unsigned count) {
    switch (primitive) {
    case 0x80: return count >= 4 && !(count & 3) ? count * 2 : 0;
    case 0x90: return count >= 3 && count % 3 == 0 ? count * 2 : 0;
    case 0x98: return count < 3 ? 0 : count == 3 ? 4 : count * 2 + (count > kBatchVertices);
    case 0xa0: return count >= 3 ? (count - 2) * 6 : 0;
    case 0xa8: return count >= 2 && !(count & 1) ? count : 0;
    case 0xb0: return count >= 2 ? count : 0;
    case 0xb8: return count;
    default: return 0;
    }
}

// No FIFO writes occur until the entire list and expanded output fit their bounds.
inline bool validate(const Byte *data, unsigned size, unsigned stride, unsigned budget,
                     unsigned *outputBytes) {
    if (!data || !size || size > kMaxListBytes || !stride || stride > kMaxStride) return false;
    unsigned output = 0;
    for (unsigned pos = 0; pos < size;) {
        const unsigned command = data[pos++];
        if (!command) continue;
        if ((command & 7) || size - pos < 2) return false;
        const unsigned count = read16(data + pos), vertices = edgeVertices(command, count);
        pos += 2;
        if (!vertices || count > (size - pos) / stride) return false;
        const unsigned batches = command == 0x98 ? (count == 3 ? 1 : 3 + (count > kBatchVertices)) :
            command >= 0xa8 ? 1 : (vertices + kBatchVertices - 1) / kBatchVertices;
        const unsigned bytes = vertices * stride + batches * 3;
        if (bytes > budget - output) return false;
        output += bytes;
        pos += count * stride;
    }
    if (!output) return false;
    *outputBytes = output;
    return true;
}

template <class Sink>
inline void lineStrip(const Byte *data, unsigned count, unsigned stride, unsigned step, Sink &sink) {
    while (count > 1) {
        const unsigned batch = count < kBatchVertices ? count : kBatchVertices;
        sink.begin(0xb0, batch);
        if (step == stride) sink.bytes(data, batch * stride);
        else for (unsigned i = 0; i < batch; ++i) sink.bytes(data + i * step, stride);
        // The shared endpoint joins batches without losing the boundary edge.
        data += (batch - 1) * step;
        count -= batch - 1;
    }
}

template <class Sink>
inline void emit(const Byte *data, unsigned size, unsigned stride, Sink &sink) {
    for (unsigned pos = 0; pos < size;) {
        const unsigned primitive = data[pos++];
        if (!primitive) continue;
        const unsigned count = read16(data + pos);
        pos += 2;
        const Byte *vertices = data + pos;
        pos += count * stride;
        if (primitive == 0x98) {
            if (count == 3) {
                sink.begin(0xb0, 4);
                sink.bytes(vertices, 3 * stride);
                sink.bytes(vertices, stride);
            } else {
                // Strip edges are exactly adjacent vertices and the two parity chains.
                lineStrip(vertices, count, stride, stride, sink);
                lineStrip(vertices, (count + 1) / 2, stride, stride * 2, sink);
                lineStrip(vertices + stride, count / 2, stride, stride * 2, sink);
            }
            continue;
        }
        if (primitive >= 0xa8) {
            sink.begin(primitive, count);
            sink.bytes(vertices, count * stride);
            continue;
        }
        unsigned remaining = edgeVertices(primitive, count), batchLeft = 0;
        const unsigned sides = primitive == 0x80 ? 4 : 3;
        const unsigned step = primitive == 0x80 ? 4 : primitive == 0x90 ? 3 : 1;
        const unsigned faces = primitive == 0x80 || primitive == 0x90 ? count / sides : count - 2;
        for (unsigned face = 0; face < faces; ++face) {
            unsigned indices[4];
            for (unsigned i = 0; i < sides; ++i)
                indices[i] = primitive == 0xa0 ? (i == 0 ? 0 : face + i) : face * step + i;
            for (unsigned side = 0; side < sides; ++side) {
                if (!batchLeft) {
                    batchLeft = remaining < kBatchVertices ? remaining : kBatchVertices;
                    sink.begin(0xa8, batchLeft);
                }
                sink.bytes(vertices + indices[side] * stride, stride);
                sink.bytes(vertices + indices[(side + 1) % sides] * stride, stride);
                batchLeft -= 2;
                remaining -= 2;
            }
        }
    }
}
}
