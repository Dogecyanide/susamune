#if defined(__powerpc__)
#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"
#endif

#include "../vendor/miniz/state_miniz_config.h"
#include "../vendor/miniz/miniz.h"
#if defined(__powerpc__)
// A single named text section otherwise keeps unused miniz convenience APIs
// alive with the streaming codec. Separate their sections so the linker can
// discard them, including an out-of-line initializer when all callers inline it.
#define MINIZ_SEPARATE_API(name) \
    extern "C" __typeof__(name) name \
        __attribute__((section(".foxtrot.text.miniz." #name)));
MINIZ_SEPARATE_API(mz_free)
MINIZ_SEPARATE_API(miniz_def_alloc_func)
MINIZ_SEPARATE_API(miniz_def_free_func)
MINIZ_SEPARATE_API(miniz_def_realloc_func)
MINIZ_SEPARATE_API(tdefl_init)
MINIZ_SEPARATE_API(tdefl_compress_buffer)
MINIZ_SEPARATE_API(tdefl_create_comp_flags_from_zip_params)
MINIZ_SEPARATE_API(tdefl_get_adler32)
MINIZ_SEPARATE_API(tdefl_get_prev_return_status)
MINIZ_SEPARATE_API(tdefl_compress_mem_to_heap)
MINIZ_SEPARATE_API(tdefl_compress_mem_to_mem)
MINIZ_SEPARATE_API(tdefl_compress_mem_to_output)
MINIZ_SEPARATE_API(tdefl_write_image_to_png_file_in_memory)
MINIZ_SEPARATE_API(tdefl_write_image_to_png_file_in_memory_ex)
MINIZ_SEPARATE_API(tinfl_decompress_mem_to_callback)
MINIZ_SEPARATE_API(tinfl_decompress_mem_to_heap)
MINIZ_SEPARATE_API(tinfl_decompress_mem_to_mem)
#undef MINIZ_SEPARATE_API
#endif
// Both Quick blocks and Deflate use the same checked Adler implementation.
// Keep one copy rather than inlining its packed-byte loop into each caller.
extern "C" __typeof__(mz_adler32) mz_adler32 __attribute__((noinline));
#include "../vendor/miniz/miniz.c"
#include "../vendor/miniz/miniz_tdef.c"
#include "../vendor/miniz/miniz_tinfl.c"
#include "../vendor/lz4/state_lz4_config.h"
#if defined(__powerpc__)
// Keep vendor functions separate so unused LZ4 entry points can be discarded.
#pragma clang section text="" rodata="" data="" bss=""
#endif
#include "../vendor/lz4/lz4.c"
#if defined(__powerpc__)
#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"
#endif
#include "susamune/state_codec.hxx"
#include "susamune/state_slot_pool.h"

namespace StateCodec {
namespace {

typedef __UINTPTR_TYPE__ Address;
const unsigned int kMaxSize = 0xffffffffu;
struct InflateWorkspace {
    tinfl_decompressor state;
    unsigned char ring[TINFL_LZ_DICT_SIZE];
};
const unsigned int kQuickBlock = 0x20000;
const unsigned int kQuickMagic = 0x4D534C34; // MSL4, independent bounded LZ4 blocks.
struct QuickWorkspace {
    LZ4_stream_t state;
    unsigned char raw[kQuickBlock];
    unsigned char packed[LZ4_COMPRESSBOUND(kQuickBlock)];
    bool zero;
};

bool zeroBlock(const unsigned char *bytes, unsigned int size) {
    typedef unsigned int Word __attribute__((__may_alias__));
    while (size && (reinterpret_cast<Address>(bytes) & 3u)) {
        if (*bytes++) return false;
        --size;
    }
    while (size >= 16) {
        const Word *words = reinterpret_cast<const Word *>(bytes);
        if (words[0] | words[1] | words[2] | words[3]) return false;
        bytes += 16; size -= 16;
    }
    while (size--) if (*bytes++) return false;
    return true;
}
unsigned int zeroAdler(unsigned int adler, unsigned int size) {
    const unsigned int low = (adler & 65535u) % 65521u;
    return low | ((((adler >> 16) + (size % 65521u) * low) % 65521u) << 16);
}
bool packedZero(const unsigned char *bytes, unsigned int size, unsigned int raw) {
    if (raw < 32 || size != (raw - 25) / 255 + 11 ||
        bytes[0] != 0x1f || bytes[1] || bytes[2] != 1 || bytes[3]) return false;
    bytes += 4;
    unsigned int left = raw - 25;
    while (left >= 255) { if (*bytes++ != 255) return false; left -= 255; }
    return bytes[0] == left && bytes[1] == 0x50 && zeroBlock(bytes + 2, 5);
}
void fillZero(unsigned char *bytes, unsigned int size) {
    typedef unsigned int Word __attribute__((__may_alias__));
    while (size && (reinterpret_cast<Address>(bytes) & 3u)) { *bytes++ = 0; --size; }
    while (size >= 16) {
        // Keep the bounded word stores instead of lowering this to byte memset.
        volatile Word *words = reinterpret_cast<volatile Word *>(bytes);
        words[0] = words[1] = words[2] = words[3] = 0;
        bytes += 16; size -= 16;
    }
    while (size--) *bytes++ = 0;
}

// This workspace always reserves LZ4's complete worst-case output. Keep the
// same compressor/table selection as LZ4_compress_fast_extState, without
// linking its two additional limited-output compressor specializations.
__attribute__((noinline, section(".text.moonshineQuickLz4")))
int quickLz4Block(QuickWorkspace *work, const unsigned char *bytes, unsigned int raw) {
    work->zero = false;
    if (!raw || raw > kQuickBlock) return 0;
    if (raw >= 32 && zeroBlock(bytes, raw)) {
        // Exactly LZ4's one literal, offset-one run and five trailing literals.
        work->zero = true;
        unsigned char *out = work->packed;
        *out++ = 0x1f; *out++ = 0; *out++ = 1; *out++ = 0;
        unsigned int left = raw - 25;
        while (left >= 255) { *out++ = 255; left -= 255; }
        *out++ = left; *out++ = 0x50;
        for (unsigned int i = 0; i < 5; ++i) *out++ = 0;
        return out - work->packed;
    }
    LZ4_stream_t_internal *ctx =
        &LZ4_initStream(&work->state, sizeof(work->state))->internal_donotuse;
    const char *source = reinterpret_cast<const char *>(bytes);
    char *dest = reinterpret_cast<char *>(work->packed);
    if (raw < LZ4_64Klimit)
        return LZ4_compress_generic(ctx, source, dest, raw, NULL, 0,
            notLimited, byU16, noDict, noDictIssue, 8);
    const tableType_t table = sizeof(void *) == 4 && (uptrval)source > LZ4_DISTANCE_MAX
        ? byPtr : byU32;
    return LZ4_compress_generic(ctx, source, dest, raw, NULL, 0,
        notLimited, table, noDict, noDictIssue, 8);
}
const unsigned int kWorkSize =
    ((sizeof(tdefl_compressor) > sizeof(InflateWorkspace)
        ? sizeof(tdefl_compressor) : sizeof(InflateWorkspace)) + 31u) & ~31u;
static_assert(sizeof(unsigned int) == 4, "codec sizes must be 32 bits");
static_assert(kWorkSize <= kWorkspaceLimit, "savestate codec workspace exceeded");
static_assert(sizeof(QuickWorkspace) <= kWorkSize, "fast codec workspace exceeded");

bool rangeValid(const void *data, unsigned int size) {
    return !size || (data && reinterpret_cast<Address>(data) <=
                                ~Address(0) - size);
}

bool overlaps(const void *a, unsigned int as, const void *b, unsigned int bs) {
    if (!as || !bs) return false;
    const Address ap = reinterpret_cast<Address>(a);
    const Address bp = reinterpret_cast<Address>(b);
    return ap < bp + bs && bp < ap + as;
}

__attribute__((noinline)) Status checkSource(void *workspace, unsigned int workspaceBytes,
                   const ReadSpan *source, unsigned int count,
                   unsigned int *total) {
    *total = 0;
    if (!workspace || (reinterpret_cast<Address>(workspace) & 31u) ||
        !rangeValid(workspace, workspaceBytes) || !source ||
        !count || count > kMaxReadSpans ||
        !rangeValid(source, count * sizeof(ReadSpan))) return INVALID_ARGUMENT;
    if (workspaceBytes < kWorkSize) return WORKSPACE_TOO_SMALL;
    if (overlaps(source, count * sizeof(ReadSpan), workspace, workspaceBytes))
        return INVALID_ARGUMENT;
    for (unsigned int i = 0; i < count; ++i) {
        if (!rangeValid(source[i].data, source[i].size) ||
            source[i].size > kMaxSize - *total ||
            overlaps(source[i].data, source[i].size, workspace, workspaceBytes))
            return INVALID_ARGUMENT;
        *total += source[i].size;
    }
    return *total ? SUCCESS : INVALID_ARGUMENT;
}

Status checkOutput(void *workspace, unsigned int workspaceBytes,
                   const ReadSpan *source, unsigned int sourceCount,
                   const WriteSpan *output, unsigned int outputCount,
                   unsigned int *total) {
    *total = 0;
    if (!output || !outputCount || outputCount > kMaxSpans ||
        !rangeValid(output, outputCount * sizeof(WriteSpan)) ||
        overlaps(output, outputCount * sizeof(WriteSpan), workspace, workspaceBytes))
        return INVALID_ARGUMENT;
    for (unsigned int i = 0; i < outputCount; ++i) {
        const WriteSpan &span = output[i];
        if (!rangeValid(span.data, span.size) || span.size > kMaxSize - *total ||
            overlaps(span.data, span.size, workspace, workspaceBytes) ||
            overlaps(span.data, span.size, source, sourceCount * sizeof(ReadSpan)) ||
            overlaps(span.data, span.size, output, outputCount * sizeof(WriteSpan)))
            return INVALID_ARGUMENT;
        for (unsigned int j = 0; j < sourceCount; ++j)
            if (overlaps(span.data, span.size, source[j].data, source[j].size))
                return INVALID_ARGUMENT;
        for (unsigned int j = 0; j < i; ++j)
            if (overlaps(span.data, span.size, output[j].data, output[j].size))
                return INVALID_ARGUMENT;
        *total += span.size;
    }
    return SUCCESS;
}

struct PackSink {
    const WriteSpan *spans;
    unsigned int count;
    unsigned int written;
};

__attribute__((noinline)) int packOutput(const void *data, int length, void *context) {
    PackSink *sink = static_cast<PackSink *>(context);
    if (length < 0 || static_cast<unsigned int>(length) > kMaxSize - sink->written)
        return 0;
    unsigned int offset = sink->written;
    unsigned int remaining = static_cast<unsigned int>(length);
    sink->written += remaining;
    if (!sink->spans) return 1;
    const unsigned char *bytes = static_cast<const unsigned char *>(data);
    for (unsigned int i = 0; i < sink->count && remaining; ++i) {
        const WriteSpan &span = sink->spans[i];
        if (offset >= span.size) { offset -= span.size; continue; }
        const unsigned int room = span.size - offset;
        const unsigned int amount = remaining < room ? remaining : room;
        StateSlotPoolCopyForward(static_cast<unsigned char *>(span.data) + offset, bytes, amount);
        bytes += amount;
        remaining -= amount;
        offset = 0;
    }
    // Keep counting after capacity runs out; the caller can preserve old slots.
    return 1;
}

struct ScatterSink {
    const WriteSpan *spans;
    unsigned int count, index, offset;
    CopyBytes copy;
    void *context;

    unsigned char *reserve(unsigned int size, DirectBytes direct) {
        while (index < count && offset == spans[index].size) { ++index; offset = 0; }
        if (index == count || size > spans[index].size - offset) return NULL;
        unsigned char *destination = static_cast<unsigned char *>(spans[index].data) + offset;
        if (copy && (!direct || !direct(context, destination, size))) return NULL;
        offset += size;
        return destination;
    }

    bool put(const unsigned char *bytes, unsigned int size) {
        while (size) {
            while (index < count && offset == spans[index].size) {
                ++index;
                offset = 0;
            }
            if (index == count) return false;
            const unsigned int room = spans[index].size - offset;
            const unsigned int amount = size < room ? size : room;
            void *destination = static_cast<unsigned char *>(spans[index].data) + offset;
            if (copy) copy(context, destination, bytes, amount);
            else memcpy(destination, bytes, amount);
            bytes += amount;
            size -= amount;
            offset += amount;
        }
        return true;
    }
};

typedef bool (*EmitBytes)(void *, const void *, unsigned int);

bool deflateBytes(void *context, const void *bytes, unsigned int size) {
    return tdefl_compress_buffer(static_cast<tdefl_compressor *>(context),
                                bytes, size, TDEFL_NO_FLUSH) == TDEFL_STATUS_OKAY;
}

ZeroRange zeroIntersection(ZeroRange zero, unsigned int offset, unsigned int size) {
    // Both ranges have already been checked against the complete raw length.
    if (!zero.size || zero.offset >= offset + size || offset >= zero.offset + zero.size)
        return {};
    const unsigned int begin = zero.offset > offset ? zero.offset : offset;
    const unsigned int end = zero.offset + zero.size < offset + size
        ? zero.offset + zero.size : offset + size;
    return {begin - offset, end - begin};
}

bool deflateSpan(tdefl_compressor *state, const ReadSpan &span, ZeroRange zero) {
    if (!zero.size) return !span.size || deflateBytes(state, span.data, span.size);
    const unsigned char *bytes = static_cast<const unsigned char *>(span.data);
    if (zero.offset && !deflateBytes(state, bytes, zero.offset)) return false;
    static const unsigned char zeros[256] = {};
    for (unsigned int left = zero.size; left;) {
        const unsigned int amount = left < sizeof(zeros) ? left : sizeof(zeros);
        if (!deflateBytes(state, zeros, amount)) return false;
        left -= amount;
    }
    const unsigned int end = zero.offset + zero.size;
    return end == span.size || deflateBytes(state, bytes + end, span.size - end);
}

struct SpanReader {
    const ReadSpan *spans;
    unsigned int count, index, offset;
    const StreamSource *stream;
    unsigned int logical;

    const unsigned char *peek(unsigned int *size) {
        *size = 0;
        if (stream) {
            if (logical == stream->packedBytes) return NULL;
            ReadSpan next = {};
            if (!stream->read(stream->context, logical, &next) || !next.size ||
                next.size > stream->packedBytes - logical || !rangeValid(next.data, next.size)) return NULL;
            const Address begin = reinterpret_cast<Address>(stream->buffer.data);
            const Address address = reinterpret_cast<Address>(next.data);
            if (address < begin || address - begin > stream->buffer.size ||
                next.size > stream->buffer.size - (address - begin)) return NULL;
            *size = next.size;
            return static_cast<const unsigned char *>(next.data);
        }
        while (index < count && offset == spans[index].size) { ++index; offset = 0; }
        if (index == count) return NULL;
        *size = spans[index].size - offset;
        return static_cast<const unsigned char *>(spans[index].data) + offset;
    }

    void skip(unsigned int size) {
        if (stream) logical += size;
        else offset += size;
    }

    __attribute__((noinline)) const unsigned char *take(unsigned int size, unsigned char *scratch) {
        unsigned int room;
        const unsigned char *data = peek(&room);
        if (data && size <= room) {
            skip(size);
            return data;
        }
        unsigned char *next = scratch;
        while (size && data) {
            const unsigned int amount = size < room ? size : room;
            memcpy(next, data, amount);
            next += amount;
            size -= amount;
            skip(amount);
            if (size) data = peek(&room);
        }
        return size ? NULL : scratch;
    }
};

const unsigned char *quickInput(SpanReader &reader, QuickWorkspace *work,
                               unsigned int offset, unsigned int size, ZeroRange zero) {
    const unsigned char *bytes = reader.take(size, work->raw);
    zero = zeroIntersection(zero, offset, size);
    if (bytes && zero.size) {
        if (bytes != work->raw) memcpy(work->raw, bytes, size);
        memset(work->raw + zero.offset, 0, zero.size);
        bytes = work->raw;
    }
    return bytes;
}

unsigned int readWord(const unsigned char *p) {
    return (unsigned(p[0]) << 24) | (unsigned(p[1]) << 16) | (unsigned(p[2]) << 8) | p[3];
}

bool packWord(PackSink &sink, unsigned int value) {
    const unsigned char bytes[4] = {static_cast<unsigned char>(value >> 24),
        static_cast<unsigned char>(value >> 16), static_cast<unsigned char>(value >> 8),
        static_cast<unsigned char>(value)};
    return packOutput(bytes, sizeof(bytes), &sink) != 0;
}

Result quickPack(void *workspace, const ReadSpan *source, unsigned int sourceCount,
                 const WriteSpan *output, unsigned int outputCount,
                 unsigned int rawBytes, unsigned int capacity, ZeroRange zero) {
    QuickWorkspace *work = static_cast<QuickWorkspace *>(workspace);
    SpanReader reader = {source, sourceCount, 0, 0};
    PackSink sink = {output, outputCount, 0};
    unsigned int adler = MZ_ADLER32_INIT;
    if (!packWord(sink, kQuickMagic) || !packWord(sink, kQuickBlock))
        return {CODEC_ERROR, 0, rawBytes, 0};
    for (unsigned int done = 0; done < rawBytes;) {
        const unsigned int raw = rawBytes - done < kQuickBlock ? rawBytes - done : kQuickBlock;
        const unsigned char *bytes = quickInput(reader, work, done, raw, zero);
        if (!bytes) return {CODEC_ERROR, 0, rawBytes, 0};
        const int packed = quickLz4Block(work, bytes, raw);
        if (packed <= 0) return {CODEC_ERROR, 0, rawBytes, 0};
        adler = work->zero ? zeroAdler(adler, raw) : mz_adler32(adler, bytes, raw);
        const bool plain = static_cast<unsigned int>(packed) >= raw;
        if (!packWord(sink, raw) || !packWord(sink, plain ? raw | 0x80000000u : static_cast<unsigned int>(packed)))
            return {CODEC_ERROR, 0, rawBytes, 0};
        if (!packOutput(plain ? bytes : work->packed, plain ? raw : packed, &sink))
            return {CODEC_ERROR, 0, rawBytes, 0};
        done += raw;
    }
    return {output && sink.written > capacity ? OUTPUT_FULL : SUCCESS,
            sink.written, rawBytes, adler};
}

Status quickPass(void *workspace, const ReadSpan *source, unsigned int sourceCount,
                 unsigned int compressedBytes, const WriteSpan *output,
                 unsigned int outputCount, unsigned int expectedRaw,
                 unsigned int expectedAdler, CopyBytes copy, void *copyContext,
                 const StreamSource *stream = NULL,
                 EmitBytes emit = NULL, void *emitContext = NULL,
                 DirectBytes directPolicy = NULL, bool verifyAdler = true) {
    QuickWorkspace *work = static_cast<QuickWorkspace *>(workspace);
    SpanReader reader = {source, sourceCount, 0, 0, stream, 0};
    ScatterSink sink = {output, outputCount, 0, 0, copy, copyContext};
    unsigned char header[8];
    if (compressedBytes < 8) return CORRUPT_STREAM;
    const unsigned char *words = reader.take(8, header);
    if (!words || readWord(words) != kQuickMagic || readWord(words + 4) != kQuickBlock)
        return CORRUPT_STREAM;
    unsigned int consumed = 8, decoded = 0, adler = MZ_ADLER32_INIT;
    while (decoded < expectedRaw) {
        if (compressedBytes - consumed < 8) return CORRUPT_STREAM;
        words = reader.take(8, header);
        if (!words) return CORRUPT_STREAM;
        const unsigned int raw = readWord(words), size = readWord(words + 4);
        const bool plain = (size & 0x80000000u) != 0;
        const unsigned int packed = size & 0x7fffffffu;
        const unsigned int block = expectedRaw - decoded < kQuickBlock ? expectedRaw - decoded : kQuickBlock;
        consumed += 8;
        if (raw != block || !packed || packed > compressedBytes - consumed ||
            (plain ? packed != raw : packed >= raw)) return CORRUPT_STREAM;
        const unsigned char *bytes = reader.take(packed, work->packed);
        if (!bytes) return CORRUPT_STREAM;
        // Only a checked whole block with no retained/redirected owner bytes may
        // bypass the copy policy. The permission callback never sees split spans.
        unsigned char *direct = output && !plain ? sink.reserve(raw, directPolicy) : NULL;
        const bool zero = !plain && packedZero(bytes, packed, raw);
        if (!plain) {
            if (zero) fillZero(direct ? direct : work->raw, raw);
            else if (LZ4_decompress_safe(reinterpret_cast<const char *>(bytes),
                    reinterpret_cast<char *>(direct ? direct : work->raw), packed, raw) != static_cast<int>(raw))
                return CORRUPT_STREAM;
            bytes = direct ? direct : work->raw;
        }
        // Repacking validates the same complete raw Adler in the destination
        // encoder. Avoid hashing each decoded Quick block twice on that path.
        if (!emit && verifyAdler) adler = zero ? zeroAdler(adler, raw) : mz_adler32(adler, bytes, raw);
        if (emit && !emit(emitContext, bytes, raw)) return CODEC_ERROR;
        if (output && !direct && !sink.put(bytes, raw)) return CODEC_ERROR;
        consumed += packed;
        decoded += raw;
    }
    return consumed == compressedBytes && (emit || !verifyAdler || adler == expectedAdler) ? SUCCESS : CORRUPT_STREAM;
}

Status inflatePass(void *workspace, const ReadSpan *source,
                   unsigned int sourceCount, unsigned int compressedBytes,
                   const WriteSpan *output, unsigned int outputCount,
                   unsigned int expectedRaw, unsigned int expectedAdler,
                   CopyBytes copy = 0, void *copyContext = 0,
                   const StreamSource *stream = NULL,
                   EmitBytes emit = NULL, void *emitContext = NULL,
                   DirectBytes directPolicy = NULL) {
    SpanReader probe = {source, sourceCount, 0, 0, stream, 0};
    unsigned char prefix[4];
    const unsigned char *magic = compressedBytes >= 4 ? probe.take(4, prefix) : NULL;
    if (magic && readWord(magic) == kQuickMagic)
        return quickPass(workspace, source, sourceCount, compressedBytes, output,
                         outputCount, expectedRaw, expectedAdler, copy, copyContext,
                         stream, emit, emitContext, directPolicy);
    InflateWorkspace *work = static_cast<InflateWorkspace *>(workspace);
    tinfl_init(&work->state);
    ScatterSink sink = {output, outputCount, 0, 0, copy, copyContext};
    unsigned int input = 0, decoded = 0;
    SpanReader reader = {source, sourceCount, 0, 0, stream, 0};
    const unsigned char empty = 0;
    for (;;) {
        unsigned int available;
        const unsigned char *next = reader.peek(&available);
        if (!next && input != compressedBytes) return CORRUPT_STREAM;
        if (!next) next = &empty;
        size_t consumed = available;
        const unsigned int ringOffset = decoded & (TINFL_LZ_DICT_SIZE - 1);
        size_t produced = TINFL_LZ_DICT_SIZE - ringOffset;
        unsigned int flags = TINFL_FLAG_PARSE_ZLIB_HEADER;
        if (consumed < compressedBytes - input) flags |= TINFL_FLAG_HAS_MORE_INPUT;
        const size_t offered = consumed;
        const tinfl_status status = tinfl_decompress(&work->state, next, &consumed,
            work->ring, work->ring + ringOffset, &produced, flags);
        if (consumed > offered || produced > TINFL_LZ_DICT_SIZE - ringOffset ||
            produced > expectedRaw - decoded) return CORRUPT_STREAM;
        input += static_cast<unsigned int>(consumed);
        reader.skip(static_cast<unsigned int>(consumed));
        if (emit && !emit(emitContext, work->ring + ringOffset,
                          static_cast<unsigned int>(produced))) return CODEC_ERROR;
        if (output && !sink.put(work->ring + ringOffset, static_cast<unsigned int>(produced)))
            return CODEC_ERROR;
        decoded += static_cast<unsigned int>(produced);
        if (status == TINFL_STATUS_DONE)
            return input == compressedBytes && decoded == expectedRaw &&
                   tinfl_get_adler32(&work->state) == expectedAdler
                ? SUCCESS : CORRUPT_STREAM;
        if (status < 0 || (!consumed && !produced) ||
            (status == TINFL_STATUS_NEEDS_MORE_INPUT && input == compressedBytes))
            return CORRUPT_STREAM;
    }
}

} // namespace

__attribute__((section(".foxtrot.text.codecWorkspaceSize")))
unsigned int workspaceSize() { return kWorkSize; }

Result compress(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                const WriteSpan *output, unsigned int outputCount, bool compact, bool quick,
                ZeroRange zero) {
    Result result = {INVALID_ARGUMENT, 0, 0, 0};
    result.status = checkSource(workspace, workspaceBytes, source, sourceCount,
                                &result.rawBytes);
    if (result.status != SUCCESS) return result;
    if (zero.offset > result.rawBytes || zero.size > result.rawBytes - zero.offset)
        return {INVALID_ARGUMENT, 0, result.rawBytes, 0};
    unsigned int capacity = 0;
    if (output) {
        result.status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                                    output, outputCount, &capacity);
        if (result.status != SUCCESS) return result;
    }
    if (quick) return quickPack(workspace, source, sourceCount, output, outputCount,
                                result.rawBytes, capacity, zero);
    tdefl_compressor *state = static_cast<tdefl_compressor *>(workspace);
    PackSink sink = {output, outputCount, 0};
    const unsigned int probes = compact ? 8 : 1 | TDEFL_GREEDY_PARSING_FLAG;
    if (tdefl_init(state, packOutput, &sink, TDEFL_WRITE_ZLIB_HEADER | probes) !=
        TDEFL_STATUS_OKAY) { result.status = CODEC_ERROR; return result; }
    for (unsigned int i = 0, offset = 0; i < sourceCount; ++i) {
        if (!deflateSpan(state, source[i], zeroIntersection(zero, offset, source[i].size))) {
            result.status = CODEC_ERROR;
            return result;
        }
        offset += source[i].size;
    }
    if (tdefl_compress_buffer(state, NULL, 0, TDEFL_FINISH) != TDEFL_STATUS_DONE) {
        result.status = CODEC_ERROR;
        return result;
    }
    result.compressedBytes = sink.written;
    result.adler32 = tdefl_get_adler32(state);
    result.status = output && sink.written > capacity ? OUTPUT_FULL : SUCCESS;
    return result;
}

__attribute__((section(".text.moonshineQuickBlocks")))
Result compressQuickBlocks(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                const WriteSpan *destinations, unsigned int destinationCount,
                QuickBlock emit, void *context, ZeroRange zero) {
    Result result = {INVALID_ARGUMENT, 0, 0, 0};
    if (!emit) return result;
    result.status = checkSource(workspace, workspaceBytes, source, sourceCount, &result.rawBytes);
    if (result.status != SUCCESS) return result;
    if (zero.offset > result.rawBytes || zero.size > result.rawBytes - zero.offset)
        return {INVALID_ARGUMENT, 0, result.rawBytes, 0};
    unsigned int capacity;
    result.status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                                destinations, destinationCount, &capacity);
    if (result.status != SUCCESS) return result;
    if (!capacity) return {INVALID_ARGUMENT, 0, result.rawBytes, 0};
    QuickWorkspace *work = static_cast<QuickWorkspace *>(workspace);
    SpanReader reader = {source, sourceCount, 0, 0};
    unsigned int written = 8, adler = MZ_ADLER32_INIT;
    for (unsigned int done = 0; done < result.rawBytes;) {
        const unsigned int raw = result.rawBytes - done < kQuickBlock ? result.rawBytes - done : kQuickBlock;
        const unsigned char *bytes = quickInput(reader, work, done, raw, zero);
        if (!bytes) return {CODEC_ERROR, 0, result.rawBytes, 0};
        const int packed = quickLz4Block(work, bytes, raw);
        if (packed <= 0) return {CODEC_ERROR, 0, result.rawBytes, 0};
        adler = work->zero ? zeroAdler(adler, raw) : mz_adler32(adler, bytes, raw);
        const bool plain = static_cast<unsigned int>(packed) >= raw;
        const unsigned int length = plain ? raw : static_cast<unsigned int>(packed);
        if (written > kMaxSize - 8 - length) return {CODEC_ERROR, 0, result.rawBytes, 0};
        const unsigned int word = plain ? raw | 0x80000000u : length;
        const unsigned char header[8] = {
            static_cast<unsigned char>(raw >> 24), static_cast<unsigned char>(raw >> 16),
            static_cast<unsigned char>(raw >> 8), static_cast<unsigned char>(raw),
            static_cast<unsigned char>(word >> 24), static_cast<unsigned char>(word >> 16),
            static_cast<unsigned char>(word >> 8), static_cast<unsigned char>(word)};
        const ReadSpan block[2] = {{header, sizeof(header)}, {plain ? bytes : work->packed, length}};
        if (!emit(context, block)) return {OUTPUT_FULL, 0, result.rawBytes, 0};
        written += 8 + length;
        done += raw;
    }
    return {SUCCESS, written, result.rawBytes, adler};
}

Status prepareQuickSource(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                const WriteSpan *destinations, unsigned int destinationCount,
                PreparedQuickSource &prepared, ZeroRange zero) {
    unsigned int raw, capacity;
    Status status = checkSource(workspace, workspaceBytes, source, sourceCount, &raw);
    if (status != SUCCESS) return status;
    if (raw > 0x2000000u || zero.offset > raw || zero.size > raw - zero.offset)
        return INVALID_ARGUMENT;
    status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                         destinations, destinationCount, &capacity);
    if (status != SUCCESS) return status;
    if (!capacity || !rangeValid(&prepared, sizeof(prepared)) ||
        overlaps(&prepared, sizeof(prepared), workspace, workspaceBytes) ||
        overlaps(&prepared, sizeof(prepared), source, sourceCount * sizeof(*source)) ||
        overlaps(&prepared, sizeof(prepared), destinations, destinationCount * sizeof(*destinations)))
        return INVALID_ARGUMENT;
    for (unsigned int i = 0; i < sourceCount; ++i)
        if (overlaps(&prepared, sizeof(prepared), source[i].data, source[i].size))
            return INVALID_ARGUMENT;
    for (unsigned int i = 0; i < destinationCount; ++i)
        if (overlaps(&prepared, sizeof(prepared), destinations[i].data, destinations[i].size))
            return INVALID_ARGUMENT;
    prepared = {source, sourceCount, raw, zero};
    return SUCCESS;
}

static void encodePreparedQuickBlockImpl(void *workspace, const PreparedQuickSource &prepared,
                              unsigned int blockIndex, PreparedQuickBlock &block, bool checksum) {
    QuickWorkspace *work = static_cast<QuickWorkspace *>(workspace);
    const unsigned int offset = blockIndex * kQuickBlock;
    const unsigned int remaining = prepared.rawBytes - offset;
    const unsigned int raw = remaining < kQuickBlock ? remaining : kQuickBlock;
    SpanReader reader = {prepared.spans, prepared.spanCount, 0, offset};
    while (reader.offset >= reader.spans[reader.index].size) {
        reader.offset -= reader.spans[reader.index].size;
        ++reader.index;
    }
    const unsigned char *bytes = quickInput(reader, work, offset, raw, prepared.zero);
    const int packed = quickLz4Block(work, bytes, raw);
    const bool plain = static_cast<unsigned int>(packed) >= raw;
    const unsigned int length = plain ? raw : static_cast<unsigned int>(packed);
    const unsigned int word = plain ? raw | 0x80000000u : length;
    for (unsigned int i = 0; i < 4; ++i) {
        block.header[i] = static_cast<unsigned char>(raw >> (24 - 8 * i));
        block.header[i + 4] = static_cast<unsigned char>(word >> (24 - 8 * i));
    }
    block.payload = plain ? bytes : work->packed;
    block.payloadBytes = length;
    block.rawBytes = raw;
    block.adler32 = work->zero ? zeroAdler(MZ_ADLER32_INIT, raw) :
        checksum ? mz_adler32(MZ_ADLER32_INIT, bytes, raw) : 0;
}

void encodePreparedQuickBlock(void *workspace, const PreparedQuickSource &prepared,
                              unsigned int blockIndex, PreparedQuickBlock &block) {
    encodePreparedQuickBlockImpl(workspace, prepared, blockIndex, block, true);
}

void encodePreparedQuickBlockDeferred(void *workspace, const PreparedQuickSource &prepared,
                              unsigned int blockIndex, PreparedQuickBlock &block) {
    encodePreparedQuickBlockImpl(workspace, prepared, blockIndex, block, false);
}

unsigned int checksumPreparedQuickBlock(void *workspace, const PreparedQuickSource &prepared,
                              unsigned int blockIndex, const PreparedQuickBlock &block) {
    if (block.adler32) return block.adler32;
    QuickWorkspace *work = static_cast<QuickWorkspace *>(workspace);
    const unsigned int offset = blockIndex * kQuickBlock;
    SpanReader reader = {prepared.spans, prepared.spanCount, 0, offset};
    while (reader.offset >= reader.spans[reader.index].size) {
        reader.offset -= reader.spans[reader.index].size;
        ++reader.index;
    }
    const unsigned char *bytes = quickInput(reader, work, offset, block.rawBytes, prepared.zero);
    return mz_adler32(MZ_ADLER32_INIT, bytes, block.rawBytes);
}

Result repack(void *workspace, unsigned int workspaceBytes,
              void *packWorkspace, unsigned int packWorkspaceBytes,
              const ReadSpan *source, unsigned int sourceCount,
              const WriteSpan *output, unsigned int outputCount,
              unsigned int expectedRaw, unsigned int expectedAdler, bool compact) {
    Result result = {INVALID_ARGUMENT, 0, 0, 0};
    unsigned int packedBytes, ignored, capacity = 0;
    result.status = checkSource(workspace, workspaceBytes, source, sourceCount, &packedBytes);
    if (result.status != SUCCESS) return result;
    result.status = checkSource(packWorkspace, packWorkspaceBytes, source, sourceCount, &ignored);
    if (result.status != SUCCESS) return result;
    if (!expectedRaw || overlaps(workspace, workspaceBytes, packWorkspace, packWorkspaceBytes)) {
        result.status = INVALID_ARGUMENT;
        return result;
    }
    if (output) {
        result.status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                                    output, outputCount, &capacity);
        if (result.status != SUCCESS) return result;
        result.status = checkOutput(packWorkspace, packWorkspaceBytes, source, sourceCount,
                                    output, outputCount, &ignored);
        if (result.status != SUCCESS) return result;
    }
    tdefl_compressor *state = static_cast<tdefl_compressor *>(packWorkspace);
    PackSink sink = {output, outputCount, 0};
    const unsigned int probes = compact ? 8 : 1 | TDEFL_GREEDY_PARSING_FLAG;
    if (tdefl_init(state, packOutput, &sink, TDEFL_WRITE_ZLIB_HEADER | probes) != TDEFL_STATUS_OKAY) {
        result.status = CODEC_ERROR;
        return result;
    }
    result.status = inflatePass(workspace, source, sourceCount, packedBytes, NULL, 0,
                                expectedRaw, expectedAdler, NULL, NULL, NULL, deflateBytes, state);
    if (result.status != SUCCESS) return result;
    if (tdefl_compress_buffer(state, NULL, 0, TDEFL_FINISH) != TDEFL_STATUS_DONE) {
        result.status = CODEC_ERROR;
        return result;
    }
    if (tdefl_get_adler32(state) != expectedAdler) {
        result.status = CORRUPT_STREAM;
        return result;
    }
    result.compressedBytes = sink.written;
    result.rawBytes = expectedRaw;
    result.adler32 = expectedAdler;
    result.status = output && sink.written > capacity ? OUTPUT_FULL : SUCCESS;
    return result;
}

Status validate(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                unsigned int expectedRaw, unsigned int expectedAdler) {
    unsigned int compressedBytes;
    const Status status = checkSource(workspace, workspaceBytes, source, sourceCount,
                                      &compressedBytes);
    if (status != SUCCESS) return status;
    if (!expectedRaw) return INVALID_ARGUMENT;
    return inflatePass(workspace, source, sourceCount, compressedBytes, NULL, 0,
                       expectedRaw, expectedAdler);
}

__attribute__((noinline)) Status validateRestore(void *workspace, unsigned int workspaceBytes,
                  const ReadSpan *source, unsigned int sourceCount,
                  const WriteSpan *output, unsigned int outputCount,
                  unsigned int expectedRaw, unsigned int expectedAdler) {
    unsigned int compressedBytes, capacity;
    Status status = checkSource(workspace, workspaceBytes, source, sourceCount,
                                &compressedBytes);
    if (status != SUCCESS) return status;
    status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                         output, outputCount, &capacity);
    if (status != SUCCESS) return status;
    if (!expectedRaw || capacity != expectedRaw) return INVALID_ARGUMENT;
    return inflatePass(workspace, source, sourceCount, compressedBytes, NULL, 0,
                       expectedRaw, expectedAdler);
}

Status decompress(void *workspace, unsigned int workspaceBytes,
                  const ReadSpan *source, unsigned int sourceCount,
                  const WriteSpan *output, unsigned int outputCount,
                  unsigned int expectedRaw, unsigned int expectedAdler,
                  CopyBytes copy, void *copyContext) {
    Status status = validateRestore(workspace, workspaceBytes, source, sourceCount,
        output, outputCount, expectedRaw, expectedAdler);
    if (status != SUCCESS) return status;
    unsigned int compressedBytes = 0;
    for (unsigned int i = 0; i < sourceCount; ++i) compressedBytes += source[i].size;
    // Validated immutable input makes the second pass identical. Never disguise
    // a broken ownership invariant as a harmless preflight rejection.
    status = inflatePass(workspace, source, sourceCount, compressedBytes,
                         output, outputCount, expectedRaw, expectedAdler,
                         copy, copyContext);
    return status == SUCCESS ? SUCCESS : COMMIT_FAILED;
}

Status decompressVerified(void *workspace, unsigned int workspaceBytes,
                  const ReadSpan *source, unsigned int sourceCount,
                  const WriteSpan *output, unsigned int outputCount,
                  unsigned int expectedRaw, unsigned int expectedAdler,
                  CopyBytes copy, void *copyContext, DirectBytes direct) {
    unsigned int compressedBytes, capacity;
    Status status = checkSource(workspace, workspaceBytes, source, sourceCount, &compressedBytes);
    if (status != SUCCESS) return status;
    status = checkOutput(workspace, workspaceBytes, source, sourceCount, output, outputCount, &capacity);
    if (status != SUCCESS) return status;
    if (!expectedRaw || capacity != expectedRaw) return INVALID_ARGUMENT;
    status = inflatePass(workspace, source, sourceCount, compressedBytes,
                         output, outputCount, expectedRaw, expectedAdler, copy, copyContext,
                         NULL, NULL, NULL, direct);
    return status == SUCCESS ? SUCCESS : COMMIT_FAILED;
}

Status decompressExperimental(void *workspace, unsigned int workspaceBytes,
                  const ReadSpan *source, unsigned int sourceCount,
                  const WriteSpan *output, unsigned int outputCount,
                  unsigned int expectedRaw, unsigned int expectedAdler,
                  CopyBytes copy, void *copyContext, DirectBytes direct) {
    unsigned int compressedBytes, capacity;
    Status status = checkSource(workspace, workspaceBytes, source, sourceCount, &compressedBytes);
    if (status != SUCCESS) return status;
    status = checkOutput(workspace, workspaceBytes, source, sourceCount, output, outputCount, &capacity);
    if (status != SUCCESS) return status;
    if (!expectedRaw || capacity != expectedRaw) return INVALID_ARGUMENT;
    status = quickPass(workspace, source, sourceCount, compressedBytes,
                      output, outputCount, expectedRaw, expectedAdler, copy, copyContext,
                      NULL, NULL, NULL, direct, false);
    return status == SUCCESS ? SUCCESS : COMMIT_FAILED;
}

Status validateStream(void *workspace, unsigned int workspaceBytes,
                  const StreamSource &source, unsigned int expectedRaw,
                  unsigned int expectedAdler) {
    unsigned int capacity;
    if (!source.read || !source.packedBytes || !expectedRaw ||
        overlaps(&source, sizeof(source), workspace, workspaceBytes)) return INVALID_ARGUMENT;
    Status status = checkSource(workspace, workspaceBytes, &source.buffer, 1, &capacity);
    if (status != SUCCESS) return status;
    if (overlaps(&source, sizeof(source), source.buffer.data, source.buffer.size)) return INVALID_ARGUMENT;
    return inflatePass(workspace, NULL, 0, source.packedBytes, NULL, 0,
                       expectedRaw, expectedAdler, NULL, NULL, &source);
}

Status decompressStreamVerified(void *workspace, unsigned int workspaceBytes,
                  const StreamSource &source, const WriteSpan *output,
                  unsigned int outputCount, unsigned int expectedRaw,
                  unsigned int expectedAdler, CopyBytes copy, void *copyContext) {
    unsigned int capacity;
    if (!source.read || !source.packedBytes || !expectedRaw ||
        overlaps(&source, sizeof(source), workspace, workspaceBytes)) return INVALID_ARGUMENT;
    Status status = checkSource(workspace, workspaceBytes, &source.buffer, 1, &capacity);
    if (status != SUCCESS) return status;
    if (overlaps(&source, sizeof(source), source.buffer.data, source.buffer.size) ||
        overlaps(output, outputCount * sizeof(WriteSpan), source.buffer.data, source.buffer.size)) return INVALID_ARGUMENT;
    status = checkOutput(workspace, workspaceBytes, &source.buffer, 1, output, outputCount, &capacity);
    if (status != SUCCESS) return status;
    if (capacity != expectedRaw) return INVALID_ARGUMENT;
    for (unsigned int i = 0; i < outputCount; ++i)
        if (overlaps(output[i].data, output[i].size, &source, sizeof(source))) return INVALID_ARGUMENT;
    status = inflatePass(workspace, NULL, 0, source.packedBytes, output, outputCount,
                        expectedRaw, expectedAdler, copy, copyContext, &source);
    return status == SUCCESS ? SUCCESS : COMMIT_FAILED;
}

} // namespace StateCodec
