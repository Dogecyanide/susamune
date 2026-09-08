#if defined(__powerpc__)
#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"
#endif

#include "../vendor/miniz/state_miniz_config.h"
#include "../vendor/miniz/miniz.c"
#include "../vendor/miniz/miniz_tdef.c"
#include "../vendor/miniz/miniz_tinfl.c"
#include "susamune/state_codec.hxx"

namespace StateCodec {
namespace {

typedef __UINTPTR_TYPE__ Address;
const unsigned int kMaxSize = 0xffffffffu;
struct InflateWorkspace {
    tinfl_decompressor state;
    unsigned char ring[TINFL_LZ_DICT_SIZE];
};
const unsigned int kWorkSize =
    ((sizeof(tdefl_compressor) > sizeof(InflateWorkspace)
        ? sizeof(tdefl_compressor) : sizeof(InflateWorkspace)) + 31u) & ~31u;
static_assert(sizeof(unsigned int) == 4, "codec sizes must be 32 bits");
static_assert(kWorkSize <= kWorkspaceLimit, "savestate codec workspace exceeded");

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

Status checkSource(void *workspace, unsigned int workspaceBytes,
                   const ReadSpan *source, unsigned int count,
                   unsigned int *total) {
    *total = 0;
    if (!workspace || (reinterpret_cast<Address>(workspace) & 31u) ||
        !rangeValid(workspace, workspaceBytes) || !source ||
        !count || count > kMaxSpans ||
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

int packOutput(const void *data, int length, void *context) {
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
        memcpy(static_cast<unsigned char *>(span.data) + offset, bytes, amount);
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

Status inflatePass(void *workspace, const ReadSpan *source,
                   unsigned int sourceCount, unsigned int compressedBytes,
                   const WriteSpan *output, unsigned int outputCount,
                   unsigned int expectedRaw, unsigned int expectedAdler,
                   CopyBytes copy = 0, void *copyContext = 0) {
    InflateWorkspace *work = static_cast<InflateWorkspace *>(workspace);
    tinfl_init(&work->state);
    ScatterSink sink = {output, outputCount, 0, 0, copy, copyContext};
    unsigned int input = 0, decoded = 0, spanIndex = 0, spanOffset = 0;
    const unsigned char empty = 0;
    for (;;) {
        while (spanIndex < sourceCount && spanOffset == source[spanIndex].size) {
            ++spanIndex;
            spanOffset = 0;
        }
        const unsigned char *next = &empty;
        size_t consumed = 0;
        if (spanIndex < sourceCount) {
            next = static_cast<const unsigned char *>(source[spanIndex].data) + spanOffset;
            consumed = source[spanIndex].size - spanOffset;
        }
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
        spanOffset += static_cast<unsigned int>(consumed);
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

unsigned int workspaceSize() { return kWorkSize; }

Result compress(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                const WriteSpan *output, unsigned int outputCount, bool compact) {
    Result result = {INVALID_ARGUMENT, 0, 0, 0};
    result.status = checkSource(workspace, workspaceBytes, source, sourceCount,
                                &result.rawBytes);
    if (result.status != SUCCESS) return result;
    unsigned int capacity = 0;
    if (output) {
        result.status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                                    output, outputCount, &capacity);
        if (result.status != SUCCESS) return result;
    }
    tdefl_compressor *state = static_cast<tdefl_compressor *>(workspace);
    PackSink sink = {output, outputCount, 0};
    const unsigned int probes = compact ? 8 : 1 | TDEFL_GREEDY_PARSING_FLAG;
    if (tdefl_init(state, packOutput, &sink, TDEFL_WRITE_ZLIB_HEADER | probes) !=
        TDEFL_STATUS_OKAY) { result.status = CODEC_ERROR; return result; }
    for (unsigned int i = 0; i < sourceCount; ++i) {
        if (source[i].size && tdefl_compress_buffer(state, source[i].data,
                source[i].size, TDEFL_NO_FLUSH) != TDEFL_STATUS_OKAY) {
            result.status = CODEC_ERROR;
            return result;
        }
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

Status decompress(void *workspace, unsigned int workspaceBytes,
                  const ReadSpan *source, unsigned int sourceCount,
                  const WriteSpan *output, unsigned int outputCount,
                  unsigned int expectedRaw, unsigned int expectedAdler,
                  CopyBytes copy, void *copyContext) {
    unsigned int compressedBytes, capacity;
    Status status = checkSource(workspace, workspaceBytes, source, sourceCount,
                                &compressedBytes);
    if (status != SUCCESS) return status;
    status = checkOutput(workspace, workspaceBytes, source, sourceCount,
                         output, outputCount, &capacity);
    if (status != SUCCESS) return status;
    if (!expectedRaw || capacity != expectedRaw) return INVALID_ARGUMENT;
    status = inflatePass(workspace, source, sourceCount, compressedBytes, NULL, 0,
                         expectedRaw, expectedAdler);
    if (status != SUCCESS) return status;
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
                  CopyBytes copy, void *copyContext) {
    unsigned int compressedBytes, capacity;
    Status status = checkSource(workspace, workspaceBytes, source, sourceCount, &compressedBytes);
    if (status != SUCCESS) return status;
    status = checkOutput(workspace, workspaceBytes, source, sourceCount, output, outputCount, &capacity);
    if (status != SUCCESS) return status;
    if (!expectedRaw || capacity != expectedRaw) return INVALID_ARGUMENT;
    status = inflatePass(workspace, source, sourceCount, compressedBytes,
                         output, outputCount, expectedRaw, expectedAdler, copy, copyContext);
    return status == SUCCESS ? SUCCESS : COMMIT_FAILED;
}

} // namespace StateCodec
