#ifndef SUSAMUNE_STATE_EXPORT_PLAN_H
#define SUSAMUNE_STATE_EXPORT_PLAN_H
#include "state_storage.h"

#define SUSAMUNE_STATE_EXPORT_PLAN 0x51504C31u
#define SUSAMUNE_STATE_EXPORT_PLAN_VERSION 2u
#define SUSAMUNE_STATE_EXPORT_QUICK 0u
#define SUSAMUNE_STATE_EXPORT_DEFLATE 1u
#define SUSAMUNE_STATE_EXPORT_PLAN_BLOCKS 256u
#define SUSAMUNE_STATE_EXPORT_DIRECTORY_SIZE 0x8000u
#define SUSAMUNE_STATE_EXPORT_BLOCK_SIZE 0x20000u

/* Shared-stage request data only; archive bytes keep their existing format. */
struct SusamuneStateExportRange { unsigned int offset, size; };
struct SusamuneStateExportPlan {
    unsigned int magic, version, count, rawBytes;
    unsigned int packedBytes, metadataCrc, checksum, kind;
    struct SusamuneStateExportRange blocks[SUSAMUNE_STATE_EXPORT_PLAN_BLOCKS];
};
typedef char StateExportPlanSize[sizeof(struct SusamuneStateExportPlan) == 2080 ? 1 : -1];

static inline unsigned int SusamuneStateExportPlanCrc(const struct SusamuneStateExportPlan *p) {
    const unsigned int zero = 0;
    unsigned int crc = SusamuneStateCrcUpdate(~0u, p, 24);
    crc = SusamuneStateCrcUpdate(crc, &zero, 4);
    return ~SusamuneStateCrcUpdate(crc, (const unsigned char *)p + 28, sizeof(*p) - 28);
}

static inline int SusamuneStateExportPlanValid(const struct SusamuneStateExportPlan *p,
        const struct SusamuneStateArchiveHeader *h, unsigned int capacity) {
    unsigned int i, packed, minimum, maximum;
    if (!p || !h || p->magic != SUSAMUNE_STATE_EXPORT_PLAN ||
        p->version != SUSAMUNE_STATE_EXPORT_PLAN_VERSION || !p->count ||
        p->count > SUSAMUNE_STATE_EXPORT_PLAN_BLOCKS || p->kind > SUSAMUNE_STATE_EXPORT_DEFLATE ||
        p->rawBytes != h->rawSize || p->packedBytes != h->packedSize ||
        p->metadataCrc != h->metadataCrc || p->checksum != SusamuneStateExportPlanCrc(p)) return 0;
    packed = p->kind == SUSAMUNE_STATE_EXPORT_QUICK ? 8 : 0;
    minimum = p->kind == SUSAMUNE_STATE_EXPORT_QUICK ? 9 : 1;
    maximum = SUSAMUNE_STATE_EXPORT_BLOCK_SIZE + (p->kind == SUSAMUNE_STATE_EXPORT_QUICK ? 8 : 0);
    for (i = 0; i < SUSAMUNE_STATE_EXPORT_PLAN_BLOCKS; ++i) {
        const struct SusamuneStateExportRange *r = &p->blocks[i];
        if (i >= p->count) {
            if (r->offset || r->size) return 0;
        } else {
            if (r->offset < SUSAMUNE_STATE_EXPORT_DIRECTORY_SIZE || (r->offset & 31u) ||
                r->size < minimum || r->size > maximum ||
                r->offset > capacity || r->size > capacity - r->offset ||
                packed > h->packedSize || r->size > h->packedSize - packed) return 0;
            packed += r->size;
        }
    }
    return packed == h->packedSize;
}

static inline unsigned int SusamuneStateExportWord(const unsigned char *p) {
    return (unsigned int)p[0] << 24 | (unsigned int)p[1] << 16 |
           (unsigned int)p[2] << 8 | p[3];
}

static inline unsigned int SusamuneStateExportBlockRaw(const unsigned char *p,
        unsigned int size, int last) {
    unsigned int raw, packed;
    if (!p || size < 9 || size > SUSAMUNE_STATE_EXPORT_BLOCK_SIZE + 8) return 0;
    raw = SusamuneStateExportWord(p);
    packed = SusamuneStateExportWord(p + 4);
    if (!raw || raw > SUSAMUNE_STATE_EXPORT_BLOCK_SIZE ||
        (!last && raw != SUSAMUNE_STATE_EXPORT_BLOCK_SIZE) ||
        (packed & 0x7fffffffu) != size - 8 ||
        ((packed & 0x80000000u) ? size - 8 != raw : size - 8 >= raw)) return 0;
    return raw;
}
#endif
