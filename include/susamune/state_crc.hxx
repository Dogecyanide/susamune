#ifndef SUSAMUNE_STATE_CRC_HXX
#define SUSAMUNE_STATE_CRC_HXX

#include "state_crc.h"

namespace StateCrc {

const unsigned int kWorkspaceBytes = TW_CRC_WORKSPACE_BYTES;
const unsigned int kWorkspaceAlignment = TW_CRC_WORKSPACE_ALIGNMENT;

// Borrows the same 4 KiB of the existing idle codec workspace.
// Initialize again after any codec operation;
// retain exclusive ownership until every checksum span has been consumed.
bool init(void *workspace, unsigned int workspaceBytes);

// Same unfinished-CRC seed/result as SusamuneStateCrcUpdate. The initialized
// workspace and nonempty input must be valid, disjoint, caller-owned ranges.
unsigned int update(const void *workspace, unsigned int crc,
                    const void *data, unsigned int size);

}
#endif
