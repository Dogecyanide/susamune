#ifndef SUSAMUNE_CISO_READER_H
#define SUSAMUNE_CISO_READER_H

#define SUSAMUNE_CISO_HEADER_SIZE 0x8000u
#define SUSAMUNE_CISO_BLOCK_SIZE  0x200000u
#define SUSAMUNE_CISO_MAP_COUNT   1024u
#define SUSAMUNE_CISO_EMPTY       0xffffu

/* The same 2 MiB sparse format supported by Nintendont's game reader. */
static int SusamuneCisoMapInit(unsigned short *map,
    const unsigned char *header, unsigned int headerBytes,
    unsigned long long fileSize)
{
    unsigned int i, used = 0;
    if (headerBytes < 8u + SUSAMUNE_CISO_MAP_COUNT ||
        fileSize < SUSAMUNE_CISO_HEADER_SIZE ||
        header[0] != 'C' || header[1] != 'I' || header[2] != 'S' ||
        header[3] != 'O' || header[4] != 0 || header[5] != 0 ||
        header[6] != 0x20 || header[7] != 0)
        return 0;
    for (i = 0; i < SUSAMUNE_CISO_MAP_COUNT; ++i) {
        if (header[8u + i] > 1u)
            return 0;
        map[i] = header[8u + i] ? (unsigned short)used++ :
            SUSAMUNE_CISO_EMPTY;
    }
    return used != 0 &&
        (unsigned long long)used * SUSAMUNE_CISO_BLOCK_SIZE <=
            fileSize - SUSAMUNE_CISO_HEADER_SIZE;
}

/* Returns one bounded physical span; empty blocks have no physical offset. */
static unsigned int SusamuneCisoSpan(const unsigned short *map,
    unsigned long long logical, unsigned int length,
    unsigned long long fileSize, unsigned long long *physical, int *empty)
{
    unsigned long long block = logical / SUSAMUNE_CISO_BLOCK_SIZE;
    unsigned int within = (unsigned int)(logical % SUSAMUNE_CISO_BLOCK_SIZE);
    unsigned int amount = SUSAMUNE_CISO_BLOCK_SIZE - within;
    if (length == 0 || block >= SUSAMUNE_CISO_MAP_COUNT)
        return 0;
    if (amount > length)
        amount = length;
    *empty = map[block] == SUSAMUNE_CISO_EMPTY;
    *physical = 0;
    if (!*empty) {
        *physical = SUSAMUNE_CISO_HEADER_SIZE +
            (unsigned long long)map[block] * SUSAMUNE_CISO_BLOCK_SIZE + within;
        if (*physical > fileSize || amount > fileSize - *physical)
            return 0;
    }
    return amount;
}

#endif
