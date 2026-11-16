#ifndef SUSAMUNE_STATE_QUICK_REPLAY_HXX
#define SUSAMUNE_STATE_QUICK_REPLAY_HXX
#define SUSAMUNE_QUICK_CHECKSUM_REUSE 1
#ifndef SUSAMUNE_SAVE_SPILL_EXPERIMENT
#define SUSAMUNE_SAVE_SPILL_EXPERIMENT 0
#endif

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
struct SpillCache {
    void *data;
    unsigned int bytes;
    void *context;
    // Confirms the frozen exclusive lease and disjoint codec/source spans.
    bool (*admitted)(void *, const void *, unsigned int);
};
struct Plan;
enum Status { READY, INVALID, FULL, SOURCE_BUSY };
struct Stats { unsigned int cachedBytes, spilledBlocks, replayRawBytes, movedBytes; };

// Requires the same exclusive frozen owner as replay. Every refusal precedes
// writes; retained generations/raw bytes stay unchanged. tag must be pure.
bool refineRetained(StateStore::Store &, unsigned int slots, void *workspace, unsigned int workspaceBytes,
                    void *scratch, unsigned int scratchBytes,
                    unsigned int (*tag)(unsigned int slot, unsigned int packed));

unsigned int workspaceSize();
// Scratch is the exclusively owned transfer tail, outside the candidate prefix.
// Source, descriptors, callback context and codec work remain immutable/disjoint
// through commit. The optional experiment borrows a separate leased span of up
// to 500 KiB; include that span in prepareQuickSource output admission too.
// encode/checksum are total for every admitted block; they may
// only borrow codec work. admitted checks ownership/quiescence, not contents.
Status prepare(StateStore::Store &, unsigned int slot, const StateStore::Identity &expected,
               const Source &, void *scratch, unsigned int scratchBytes, Plan *&);
// Disabled builds refuse this entry point without beginning a transaction.
#if SUSAMUNE_SAVE_SPILL_EXPERIMENT
Status prepareWithSpill(StateStore::Store &, unsigned int slot, const StateStore::Identity &expected,
               const Source &, void *scratch, unsigned int scratchBytes, Plan *&, const SpillCache &);
#else
inline Status prepareWithSpill(StateStore::Store &, unsigned int, const StateStore::Identity &,
               const Source &, void *, unsigned int, Plan *&out, const SpillCache &) {
    out = nullptr;
    return INVALID;
}
#endif
StateCodec::Result result(const Plan &);
unsigned int checksum(const Plan &);
Stats stats(const Plan &);
// Every false return precedes destructive writes. Cancellation ends at commit.
bool commit(Plan &, const StateStore::Identity &);
bool abort(Plan &);

}
#endif
