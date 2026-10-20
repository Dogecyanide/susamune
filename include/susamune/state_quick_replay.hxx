#ifndef SUSAMUNE_STATE_QUICK_REPLAY_HXX
#define SUSAMUNE_STATE_QUICK_REPLAY_HXX
#define SUSAMUNE_QUICK_CHECKSUM_REUSE 1

#include "state_store.hxx"

namespace StateCodec { struct PreparedQuickBlock; }
namespace StateQuickReplay {

struct Source {
    void *context;
    unsigned int rawBytes;
    void (*encode)(void *, unsigned int block, StateCodec::PreparedQuickBlock &);
    bool (*admitted)(void *);
    // Optional deferred raw checksum, used only when no exact cached block matches.
    unsigned int (*checksum)(void *, unsigned int block, const StateCodec::PreparedQuickBlock &);
};
struct Plan;
enum Status { READY, INVALID, FULL, SOURCE_BUSY };
struct Stats { unsigned int cachedBytes, spilledBlocks, replayRawBytes, movedBytes; };

unsigned int workspaceSize();
// Scratch is the exclusively owned transfer tail, outside the candidate prefix.
// Source, descriptors, callback context and codec work remain immutable/disjoint
// through commit. encode/checksum are total for every admitted block; they may
// only borrow codec work. admitted checks ownership/quiescence, not contents.
Status prepare(StateStore::Store &, unsigned int slot, const StateStore::Identity &expected,
               const Source &, void *scratch, unsigned int scratchBytes, Plan *&);
StateCodec::Result result(const Plan &);
unsigned int checksum(const Plan &);
Stats stats(const Plan &);
// Every false return precedes destructive writes. Cancellation ends at commit.
bool commit(Plan &, const StateStore::Identity &);
bool abort(Plan &);

}
#endif
