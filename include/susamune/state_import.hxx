#ifndef SUSAMUNE_STATE_IMPORT_HXX
#define SUSAMUNE_STATE_IMPORT_HXX
#include "state_store.hxx"

namespace StateImport {
struct Cursor {
    TWStageToken transaction;
    unsigned int total, offset, kind;
};
enum Status { MORE, COMPLETE, INVALID, FULL };
bool begin(const StateStore::Store &, Cursor &, unsigned int packedBytes);
// Borrowed windows start at cursor.offset. An incomplete final Quick block
// is reread with the next window; no partial payload survives the borrow.
Status append(StateStore::Store &, Cursor &, const void *bytes, unsigned int size);
}
#endif
