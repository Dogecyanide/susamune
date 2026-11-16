#pragma once

namespace GhostTraceReader {
enum Status { NEED_DATA, CHUNK_READY, COMPLETE, FAILED };
enum Error { NONE, ARGUMENT, SHORT_READ, HEADER, CHUNK, COMPRESSION, CHECKSUM, RECORD, CAPTURE_FAILED };
struct Read { unsigned offset, bytes; void *destination; };
struct Reader {
    unsigned fileBytes, offset, pending, phase, version, game, run, capabilities;
    unsigned chunks, expectedChunks, chunkBytes, filled, expectedHash, hash, firstFrame, lastFrame;
    unsigned frame, tick, blockRaw, blockStored, codec, error;
    unsigned char *output, *packed;
    unsigned char header[64] __attribute__((aligned(32)));
};
// Caller leases 512 KiB output and 16 KiB packed scratch from the shared arena.
bool begin(Reader &, unsigned fileBytes, void *output, unsigned outputBytes,
           void *packed, unsigned packedBytes);
Status status(const Reader &);
// Only one read may be outstanding; accept it before requesting the next.
bool nextRead(Reader &, Read &);
bool acceptRead(Reader &, unsigned bytes);
bool releaseChunk(Reader &);
// The previous output may remain borrowed; the caller owns the new output exclusively.
bool releaseChunk(Reader &, void *nextOutput, unsigned outputBytes);
bool sameRegion(const Reader &, unsigned gameId);
}
