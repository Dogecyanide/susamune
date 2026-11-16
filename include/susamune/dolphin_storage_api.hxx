#ifndef SUSAMUNE_DOLPHIN_STORAGE_API_HXX
#define SUSAMUNE_DOLPHIN_STORAGE_API_HXX
#include "dolphin_files.hxx"
#include "dolphin_http.hxx"
#include "dolphin_dns.hxx"
#include "dolphin_ghost_library.hxx"
#define DOLPHIN_STORAGE_API_BASE (DOLPHIN_HTTPS_IMAGE_BASE+0x100u)
#define DOLPHIN_STORAGE_API_MAGIC 0x4d535431u
#define DOLPHIN_ACCOUNT_WORK_BASE (DOLPHIN_LIBRARY_WORK_BASE+0x8000u)
#define DOLPHIN_ACCOUNT_WORK_SIZE 0x8000u
struct DolphinStorageHost {
    decltype(&DolphinFiles::read) read;
    decltype(&DolphinFiles::write) write;
    decltype(&DolphinFiles::create) create;
    decltype(&DolphinFiles::remove) remove;
    decltype(&DolphinFiles::take) fileTake;
    decltype(&DolphinHttp::begin) httpBegin;
    decltype(&DolphinHttp::update) httpUpdate;
    decltype(&DolphinHttp::take) httpTake;
    decltype(&DolphinGhostLibrary::begin) ghostBegin;
    decltype(&DolphinGhostLibrary::update) ghostUpdate;
    decltype(&DolphinGhostLibrary::take) ghostTake;
    unsigned (*seconds)();
    decltype(&DolphinFiles::list) list;
    bool (*inspectGhost)(const void *,u32,SusamuneGhostFileHeader *);
    unsigned (*milliseconds)();
    unsigned (*networkState)();
    bool (*networkBegin)();
    void (*networkStopIfIdle)();
    decltype(&DolphinNetwork::resolve) resolve;
    decltype(&DolphinNetwork::dnsResult) dnsResult;
    decltype(&DolphinNetwork::cancelResolve) cancelResolve;
};
struct DolphinStorageApi {
    unsigned magic,version,apiBytes;
    bool (*begin)(const SusamuneGhostStorageRequest &,const DolphinStorageHost *);
    void (*update)();
    bool (*take)(SusamuneGhostStorageResponse *);
    bool (*libraryBegin)(const SusamuneGhostStorageRequest &,const DolphinStorageHost *,unsigned);
    void (*libraryUpdate)();
    bool (*libraryTake)(SusamuneGhostStorageResponse *);
};
const DolphinStorageApi *dolphinStorageApi();
const DolphinStorageHost *dolphinStorageHost();
#endif
