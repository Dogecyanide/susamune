#ifndef SUSAMUNE_STATE_STORAGE_HXX
#define SUSAMUNE_STATE_STORAGE_HXX
#include <Dolphin/types.h>
#include "susamune/state_storage.h"
struct SusamuneStateExportPlan;
namespace StateStorage {
struct ResultToken { u32 generation; };
struct Result {
    u32 command, status, id;
    SusamuneStateArchiveHeader header;
    const void *metadata;
    char name[SUSAMUNE_STATE_NAME_BYTES];
    SusamuneStateWindowReceipt window;
    SusamuneTasManifest project;
    ResultToken token;
};
void init();
void update();
bool available();
bool busy();
bool quiet();
void *stagingBase();
u32 stagingSize();
u32 archiveCapacity();
// Shared-only input window; the second codec workspace uses these same bytes.
void *tailWindowBase();
u32 tailWindowSize();
u32 configId();
bool startExport(const SusamuneStateArchiveHeader &, const void *metadata, u32 poolOffset,
                 const SusamuneTasRequest *project = nullptr);
typedef bool (*BuildExportPlan)(void *, SusamuneStateExportPlan &, u32 metadataCrc);
// Builder runs under STATE ownership. Keep its root pin through result consumption.
bool startPlannedExport(const SusamuneStateArchiveHeader &, const void *metadata,
                        BuildExportPlan, void *context, const SusamuneTasRequest *project = nullptr);
bool startImport(u32 id, u32 expectedHeaderCrc, u32 packedSize, u32 freePoolOffset,
                 const SusamuneTasRequest *project = nullptr);
bool startWindow(u32 id, u32 expectedHeaderCrc, u32 packedSize, u32 offset, u32 size,
                 const SusamuneTasRequest *project = nullptr);
bool startImportWindow(u32 id, u32 expectedHeaderCrc, u32 packedSize, u32 offset, u32 size,
                       const SusamuneTasRequest *project = nullptr);
bool startTapeExport(const SusamuneStateArchiveHeader &, const SusamuneTasTakeData &,
                     const void *frames, const void *transitions, const SusamuneTasRequest &);
bool startTapeImport(const SusamuneTasManifest &);
// Pointers remain borrowed until consumeResult, including failed validation.
bool tapePayload(const Result &, SusamuneTasTakeData &, const void *&frames, const void *&transitions);
bool refresh(u32 afterId = 0);
bool rename(u32 id, u32 expectedHeaderCrc, const char *name);
bool remove(u32 id, u32 expectedHeaderCrc);
// Cancellation retains ownership until the ARM has closed the old operation.
bool cancel();
// A copied Result retains its borrow until explicitly consumed.
bool takeResult(Result &);
bool consumeResult(ResultToken, bool keepOwner = false);
bool consumeResult(const Result &, bool keepOwner = false);
// End a local owner retained between stream windows; never cancels remote work.
bool releaseOwner();
// Discard a timed-out request only after its real terminal receipt arrives.
void abandon();
void discardCancelledResult();
bool takeProjectResult(Result &);
bool projectBegin(const char *name);
bool projectRead(u32 id, u32 expectedCrc);
bool projectCommit(const SusamuneTasManifest &, u32 previousCrc);
bool projectCatalog(u32 afterId = 0);
bool projectRename(u32 id, u32 expectedCrc, const char *name);
bool projectDelete(u32 id, u32 expectedCrc);
bool catalogReady();
const SusamuneStateCatalog &catalog();
}
#endif
