#include "susamune/state_crc.hxx"
#include "susamune/state_storage.h"

namespace StateCrc {
namespace {
typedef unsigned int Word __attribute__((__may_alias__));
typedef __UINTPTR_TYPE__ Address;
struct Tables { unsigned int slices[4][256]; };
static_assert(sizeof(Tables) == kWorkspaceBytes, "state CRC workspace size changed");
}

bool init(void *workspace, unsigned int workspaceBytes) {
    if (!workspace || workspaceBytes < kWorkspaceBytes ||
        (reinterpret_cast<Address>(workspace) & (kWorkspaceAlignment - 1)) ||
        reinterpret_cast<Address>(workspace) > ~Address(0) - kWorkspaceBytes)
        return false;
    Tables *tables = static_cast<Tables *>(workspace);
    const unsigned char zero = 0;
    for (unsigned int byte = 0; byte < 256; ++byte)
        tables->slices[0][byte] = SusamuneStateCrcUpdate(byte, &zero, 1);
    for (unsigned int slice = 1; slice < 4; ++slice) {
        for (unsigned int byte = 0; byte < 256; ++byte) {
            const unsigned int previous = tables->slices[slice - 1][byte];
            tables->slices[slice][byte] = (previous >> 8) ^ tables->slices[0][previous & 255];
        }
    }
    return true;
}

unsigned int update(const void *workspace, unsigned int crc,
                    const void *data, unsigned int size) {
    if (!size) return crc;
    const Tables *tables = static_cast<const Tables *>(workspace);
    const unsigned char *bytes = static_cast<const unsigned char *>(data);
    while (size && (reinterpret_cast<Address>(bytes) & 3)) {
        crc = (crc >> 8) ^ tables->slices[0][(crc ^ *bytes++) & 255];
        --size;
    }
    while (size >= 4) {
        unsigned int word = *reinterpret_cast<const Word *>(bytes);
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
        word = __builtin_bswap32(word);
#endif
        crc ^= word;
        crc = tables->slices[3][crc & 255] ^ tables->slices[2][(crc >> 8) & 255] ^
              tables->slices[1][(crc >> 16) & 255] ^ tables->slices[0][crc >> 24];
        bytes += 4;
        size -= 4;
    }
    while (size) {
        crc = (crc >> 8) ^ tables->slices[0][(crc ^ *bytes++) & 255];
        --size;
    }
    return crc;
}

}
