#ifndef SUSAMUNE_STATE_STORE_HXX
#define SUSAMUNE_STATE_STORE_HXX

#include "state_quick_producer.hxx"
#include "state_export_plan.h"

namespace StateStore {
enum Kind { QUICK = TW_CHUNK_QUICK, DEFLATE = TW_CHUNK_OPAQUE };
struct Identity {
    unsigned int generation, tag, raw, packed, adler, checksum, kind;
};
struct Store {
    const TWStageMemory *memory;
    void *nativeScratch;
    unsigned int nativeBytes;
    Identity roots[3], candidate;
    TWStageToken transaction;
    unsigned int magic, pending, sealed, pin;
};

// Initialize only an unoccupied, exclusively owned map. No legacy migration.
bool init(Store &store, const TWStageMemory &memory, unsigned int epoch,
          void *nativeScratch = nullptr, unsigned int nativeBytes = 0);
bool valid(const Store &store);
bool begin(Store &store, unsigned int slot, const Identity &expected);
// Synchronous replay only: validate all old payload CRCs before destructive commit.
bool beginDeferredPayload(Store &store, unsigned int slot, const Identity &expected);
bool abort(Store &store);
StateCodec::Result produceQuick(Store &store, void *workspace, unsigned int workspaceBytes,
                               const StateCodec::ReadSpan *source, unsigned int sourceCount,
                               StateCodec::ZeroRange zero = {});
StateCodec::Result produceDeflate(Store &store, void *workspace, unsigned int workspaceBytes,
    const StateCodec::ReadSpan *source, unsigned int sourceCount, bool compact,
    StateCodec::ZeroRange zero = {});
// Begin the replacement first. This keeps its old root pinned during both
// measurement and writing; allocation occurs between those two borrows.
StateCodec::Result repack(Store &store, unsigned int slot, const Identity &expected,
    void *workspace, unsigned int workspaceBytes, void *packWorkspace,
    unsigned int packWorkspaceBytes, bool compact);
bool appendQuick(Store &store, const unsigned char *header, unsigned int headerSize,
                 const unsigned char *payload, unsigned int payloadSize);
bool appendOpaque(Store &store, const void *bytes, unsigned int size);
// Reserve the entire measured Deflate output before invoking compress/repack.
// A failure can leave an abortable candidate, never a reclaimed old root.
unsigned int reserveOpaque(Store &store, unsigned int size,
                           StateCodec::WriteSpan (&output)[TW_BANK_MAX + 1]);
unsigned int pendingChecksum(const Store &store);
// Fully decodes for validation without writing game memory. Identity generation
// is the caller's StoredState generation; this adapter never advances it.
bool seal(Store &store, const Identity &identity, void *workspace, unsigned int workspaceBytes);
// Retained repacks must save physical pool space, including shared blocks.
bool commit(Store &store, const Identity &identity, bool requireSaving = false);
// Failure-only diagnostic; rechecks integrity before reporting final capacity.
bool capacityRefused(const Store &store);
bool clear(Store &store, unsigned int slot, const Identity &expected, unsigned int generation);

unsigned int pin(Store &store, unsigned int slot, const Identity &expected);
bool check(const Store &store, unsigned int sequence, const Identity &expected);
bool unpin(Store &store, unsigned int sequence);
const StateCodec::ReadSpan *spans(const Store &store, unsigned int sequence, unsigned int &count);
StateCodec::Status validateRestore(const Store &store, unsigned int sequence,
    const Identity &expected, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount);
StateCodec::Status restore(const Store &store, unsigned int sequence,
    const Identity &expected, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount,
    StateCodec::CopyBytes copy = nullptr, void *context = nullptr,
    StateCodec::DirectBytes direct = nullptr);
// Immediate RAM restore under one continuous owner. The checked pin never
// escapes between its CRC and decode; long-lived borrows still use restore.
StateCodec::Status restoreSlot(Store &store, unsigned int slot,
    const Identity &expected, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount,
    StateCodec::CopyBytes copy = nullptr, void *context = nullptr,
    StateCodec::DirectBytes direct = nullptr);
// Experimental ordinary RAM load only: Quick roots skip packed CRC and raw Adler.
// Keep SD/import/TAS callers on the checked APIs; Deflate uses checked restoreSlot.
StateCodec::Status restoreSlotExperimental(Store &store, unsigned int slot,
    const Identity &expected, void *workspace, unsigned int workspaceBytes,
    const StateCodec::WriteSpan *output, unsigned int outputCount,
    StateCodec::CopyBytes copy = nullptr, void *context = nullptr,
    StateCodec::DirectBytes direct = nullptr);
// Destination is shared staging, separate from all roots and the reader table.
// Keep the pin and transfer lease until ARM completion and local consumption.
bool exportPlan(const Store &store, unsigned int sequence, const Identity &expected,
                unsigned int metadataCrc, SusamuneStateExportPlan &plan);
}
#endif
