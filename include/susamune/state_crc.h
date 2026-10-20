#ifndef SUSAMUNE_STATE_CRC_H
#define SUSAMUNE_STATE_CRC_H

enum { TW_CRC_WORKSPACE_BYTES = 4096, TW_CRC_WORKSPACE_ALIGNMENT = 4 };

#ifdef __cplusplus
extern "C" {
#endif
// Caller owns an aligned table disjoint from all checksum input.
int TWCrcSharedInit(void *workspace, unsigned int bytes);
// Seed and result retain the unfinished, reflected CRC representation.
unsigned int TWCrcSharedUpdate(const void *workspace, unsigned int crc,
                              const void *data, unsigned int bytes);
#ifdef __cplusplus
}
#endif
#endif
