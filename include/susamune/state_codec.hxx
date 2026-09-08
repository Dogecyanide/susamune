#ifndef SUSAMUNE_STATE_CODEC_HXX
#define SUSAMUNE_STATE_CODEC_HXX

namespace StateCodec {

struct ReadSpan { const void *data; unsigned int size; };
struct WriteSpan { void *data; unsigned int size; };
typedef void (*CopyBytes)(void *context, void *destination,
                          const void *source, unsigned int size);
enum Status {
    SUCCESS,
    INVALID_ARGUMENT,
    WORKSPACE_TOO_SMALL,
    OUTPUT_FULL,
    CORRUPT_STREAM,
    CODEC_ERROR,
    COMMIT_FAILED,
};
struct Result {
    Status status;
    unsigned int compressedBytes;
    unsigned int rawBytes;
    unsigned int adler32;
};

const unsigned int kMaxSpans = 64;
const unsigned int kWorkspaceLimit = 0x50000;
const unsigned int kWorkspaceAlignment = 32;
unsigned int workspaceSize();

// Output spans are capacities, concatenated in order. A null output counts only.
// OUTPUT_FULL still reports the complete required size; partial output is invalid.
Result compress(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                const WriteSpan *output, unsigned int outputCount = 2);

// Input spans contain exactly the stream's bytes, excluding allocation padding.
Status validate(void *workspace, unsigned int workspaceBytes,
                const ReadSpan *source, unsigned int sourceCount,
                unsigned int expectedRaw, unsigned int expectedAdler);

// Validates the whole stream before writing. Source and span descriptors must
// remain immutable, with exclusive workspace ownership, through both passes.
// COMMIT_FAILED means writes may have begun: the caller must not resume gameplay.
// An optional copy policy runs only after validation, and must not fail or mutate
// source/workspace/descriptors. The caller validates its policy before this call.
Status decompress(void *workspace, unsigned int workspaceBytes,
                  const ReadSpan *source, unsigned int sourceCount,
                  const WriteSpan *output, unsigned int outputCount,
                  unsigned int expectedRaw, unsigned int expectedAdler,
                  CopyBytes copy = 0, void *copyContext = 0);

} // namespace StateCodec
#endif
