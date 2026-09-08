#ifndef SUSAMUNE_STATE_STORAGE_H
#define SUSAMUNE_STATE_STORAGE_H

#include "susamune/mem2_map.h"

#define SUSAMUNE_STATE_STORAGE_MAGIC 0x4D535354u
#define SUSAMUNE_STATE_STORAGE_VERSION 1u
#define SUSAMUNE_STATE_ARCHIVE_MAGIC 0x4D535341u
#define SUSAMUNE_STATE_ARCHIVE_VERSION 1u
#define SUSAMUNE_STATE_METADATA_SIZE 7168u
#define SUSAMUNE_STATE_CATALOG_COUNT 8u
#define SUSAMUNE_STATE_CHUNK_SIZE 0x4000u
#define SUSAMUNE_STATE_MAX_ARCHIVE_ID 99999999u

enum SusamuneStateCommand {
    SUSAMUNE_STATE_CMD_NONE, SUSAMUNE_STATE_CMD_EXPORT,
    SUSAMUNE_STATE_CMD_IMPORT, SUSAMUNE_STATE_CMD_CATALOG,
    SUSAMUNE_STATE_CMD_CANCEL
};
enum SusamuneStateStatus {
    SUSAMUNE_STATE_OK, SUSAMUNE_STATE_UNAVAILABLE, SUSAMUNE_STATE_IO_ERROR,
    SUSAMUNE_STATE_BAD_FILE, SUSAMUNE_STATE_FULL, SUSAMUNE_STATE_NOT_FOUND,
    SUSAMUNE_STATE_CANCELLED, SUSAMUNE_STATE_STALE, SUSAMUNE_STATE_WRONG_CONFIG,
    SUSAMUNE_STATE_BAD_REQUEST
};

/* Big-endian on disk. No file-controlled pointers or allocation offsets. */
struct SusamuneStateArchiveHeader {
    unsigned int magic, version, headerSize, metadataSize;
    unsigned int packedSize, rawSize, gameId, buildCrc;
    unsigned int snapshotVersion, configId, metadataCrc, payloadCrc;
    unsigned int headerCrc, sceneKey, reserved[2];
    char name[32];
};
struct SusamuneStateCatalogEntry {
    unsigned int id, packedSize, metadataSize, rawSize;
    unsigned int gameId, buildCrc, headerCrc, sceneKey;
    char name[32];
};
struct SusamuneStateRequest {
    unsigned int seq, command, id, session;
    unsigned int poolOffset, packedSize, expectedHeaderCrc, reserved;
};
struct SusamuneStateResponse {
    unsigned int magic, version, ackSeq, status;
    unsigned int resultId, transferred, available, configId;
};
struct SusamuneStateReceipt {
    unsigned int session, command, id, seq;
    unsigned int metadataSize, packedSize, headerCrc, reserved;
};
struct SusamuneStateCatalog {
    unsigned int count, afterId, nextId, more, reserved[4];
    struct SusamuneStateCatalogEntry entries[SUSAMUNE_STATE_CATALOG_COUNT];
};
struct SusamuneStateStorageMailbox {
    struct SusamuneStateRequest request;
    struct SusamuneStateResponse response;
    struct SusamuneStateReceipt receipt;
    struct SusamuneStateArchiveHeader header;
    struct SusamuneStateCatalog catalog;
    unsigned char metadata[SUSAMUNE_STATE_METADATA_SIZE];
};
typedef char StateHeaderSize[sizeof(struct SusamuneStateArchiveHeader) == 96 ? 1 : -1];
typedef char StateCatalogSize[sizeof(struct SusamuneStateCatalogEntry) == 64 ? 1 : -1];
typedef char StateMailboxSize[sizeof(struct SusamuneStateStorageMailbox) == 7904 &&
    sizeof(struct SusamuneStateStorageMailbox) <= SUSAMUNE_STATE_STORAGE_SIZE ? 1 : -1];

static inline unsigned int SusamuneStateCrcUpdate(unsigned int crc,
        const void *data, unsigned int size) {
    const unsigned char *p = (const unsigned char *)data;
    unsigned int i, bit;
    for (i = 0; i < size; ++i) {
        crc ^= p[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((0u - (crc & 1u)) & 0xEDB88320u);
    }
    return crc;
}
static inline unsigned int SusamuneStateCrc(const void *data, unsigned int size) {
    return ~SusamuneStateCrcUpdate(0xFFFFFFFFu, data, size);
}
static inline unsigned int SusamuneStateHeaderCrc(const struct SusamuneStateArchiveHeader *h) {
    const unsigned char *p = (const unsigned char *)h;
    const unsigned int zero = 0;
    unsigned int crc = SusamuneStateCrcUpdate(0xFFFFFFFFu, p, 48);
    crc = SusamuneStateCrcUpdate(crc, &zero, 4);
    return ~SusamuneStateCrcUpdate(crc, p + 52, sizeof(*h) - 52);
}
static inline int SusamuneStateGameValid(unsigned int id) {
    return id == 0x474D534Au || id == 0x474D5345u || id == 0x474D5350u;
}
static inline int SusamuneStateHeaderValid(const struct SusamuneStateArchiveHeader *h) {
    unsigned int i;
    if (h->magic != SUSAMUNE_STATE_ARCHIVE_MAGIC || h->version != SUSAMUNE_STATE_ARCHIVE_VERSION ||
        h->headerSize != sizeof(*h) || !h->metadataSize || h->metadataSize > SUSAMUNE_STATE_METADATA_SIZE ||
        !h->packedSize || h->packedSize > SUSAMUNE_STATE_POOL_EXPANDED_SIZE ||
        !h->rawSize || h->rawSize > 0x02000000u || !SusamuneStateGameValid(h->gameId) ||
        !h->buildCrc || !h->snapshotVersion || !h->configId || h->reserved[0] || h->reserved[1] ||
        h->headerCrc != SusamuneStateHeaderCrc(h)) return 0;
    for (i = 0; i < sizeof(h->name); ++i) {
        if (!h->name[i]) return 1;
        if ((unsigned char)h->name[i] < 32 || (unsigned char)h->name[i] > 126) return 0;
    }
    return 0;
}
static inline int SusamuneStatePoolRange(unsigned int offset, unsigned int size) {
    return size && offset <= SUSAMUNE_STATE_POOL_EXPANDED_SIZE &&
        size <= SUSAMUNE_STATE_POOL_EXPANDED_SIZE - offset;
}
static inline int SusamuneStateImportRange(unsigned int offset, unsigned int size) {
    return size && size <= SUSAMUNE_STATE_POOL_EXPANDED_SIZE &&
        offset <= SUSAMUNE_STATE_POOL_EXPANDED_SIZE &&
        (size <= SUSAMUNE_STATE_STAGING_SIZE ||
         size - SUSAMUNE_STATE_STAGING_SIZE <= SUSAMUNE_STATE_POOL_EXPANDED_SIZE - offset);
}

#endif
