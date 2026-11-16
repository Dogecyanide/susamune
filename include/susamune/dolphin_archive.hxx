#ifndef SUSAMUNE_DOLPHIN_ARCHIVE_HXX
#define SUSAMUNE_DOLPHIN_ARCHIVE_HXX
#include "dolphin_storage_api.hxx"
#define DOLPHIN_ARCHIVE_API_BASE (DOLPHIN_HTTPS_IMAGE_BASE+0x140u)
#define DOLPHIN_ARCHIVE_API_MAGIC 0x4d415231u
struct DolphinArchiveApi {
    unsigned magic,version,apiBytes;
    void (*initialize)(const DolphinStorageHost *,unsigned);
    void (*update)();
};
namespace DolphinArchive { void initialize(); void update(); }
#endif
