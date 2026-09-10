"""Run the PPC storage service against a mocked ARM mailbox and page buffers."""

import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GhostStoragePagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-ghost-pages-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = r'''
#define IS_EMULATOR 0
#define SUSAMUNE_VERSION_JP 1
#include "susamune/ghost_storage.hxx"
extern "C" void *memcpy(void *out,const void *in,size_t size) {
    u8 *to=(u8*)out;const u8 *from=(const u8*)in;
    for(size_t i=0;i<size;i++)to[i]=from[i];return out;
}
extern "C" void *memset(void *out,int value,size_t size) {
    for(size_t i=0;i<size;i++)((u8*)out)[i]=(u8)value;return out;
}
extern "C" int memcmp(const void *a,const void *b,size_t size) {
    for(size_t i=0;i<size;i++)if(((u8*)a)[i]!=((u8*)b)[i])return ((u8*)a)[i]-((u8*)b)[i];
    return 0;
}
static SusamuneGhostStorageMailbox mailbox;
static SusamuneGhostCatalogPage pages[2];
static u8 payload[SUSAMUNE_GHOST_STORAGE_PAYLOAD_SIZE];
#undef SUSAMUNE_GHOST_STORAGE_PPC_PTR
#undef SUSAMUNE_GHOST_STORAGE_DATA_PPC_PTR
#undef SUSAMUNE_GHOST_CATALOG_CACHE_PPC_BASE
#define SUSAMUNE_GHOST_STORAGE_PPC_PTR (&::mailbox)
#define SUSAMUNE_GHOST_STORAGE_DATA_PPC_PTR (payload)
#define SUSAMUNE_GHOST_CATALOG_CACHE_PPC_BASE (pages)
#define SUSAMUNE_CRASH_EVENT_STORAGE 1
static int testProfile,playbackImports,observerImports,observerStops,checkpoints;
static bool pinned,preparing,hasTrack,acceptImport;
static u32 savedToken,saveDuration,selectedToken;
void DCInvalidateRange(void*,u32){}
void DCFlushRange(void*,u32){}
namespace CrashReport { void note(u32,u32,u32){} }
struct Menu {void toast(const char*){}};static Menu *gMenu;
namespace ILing {
    int pbProfile(){return testProfile;}
    const char *pbProfileName(int){return "Profile";}
}
namespace Records {void onGhostSaved(u32 value){saveDuration=value;}}
namespace RecordsPersistence {void checkpoint(){checkpoints++;}}
namespace Ghost {
    bool playbackPinned(){return pinned;}
    void clearPlayback(){pinned=false;}
    bool observerPreparing(){return preparing;}
    void stopObserver(){observerStops++;preparing=false;}
    bool hasSaveableTrack(){return hasTrack;}
    bool copySaveableName(char *out,u32 size,u32 *token){
        if(size)out[0]=0;*token=selectedToken;return hasTrack;
    }
    bool exportLatest(void *out,u32,u8,const char*,u32 *size,u32 *token){
        memset(out,0,SUSAMUNE_GHOST_FILE_HEADER_SIZE);
        ((SusamuneGhostFileHeader*)out)->durationQf=1234;
        *size=SUSAMUNE_GHOST_FILE_HEADER_SIZE;*token=selectedToken;return hasTrack;
    }
    void releaseSavedRecording(u32 token){savedToken=token;}
    bool importPlayback(const void*,u32,bool){playbackImports++;pinned=acceptImport;return acceptImport;}
    bool importObserverTrack(const void*,u32,bool){observerImports++;return acceptImport;}
}
'''
        production = (ROOT / "src/ghost_storage.cpp").read_text(encoding="utf-8")
        source += re.sub(r'^#include[^\n]*\n', '', production, flags=re.MULTILINE)
        source += r'''
using namespace GhostStorage;
#define CHECK(value) do { if(!(value)) return __LINE__; } while(0)
#define EXPORT extern "C" __declspec(dllexport) int
static void reset() {
    memset(&mailbox,0,sizeof(mailbox));memset(payload,0,sizeof(payload));
    testProfile=playbackImports=observerImports=observerStops=checkpoints=0;
    pinned=false;preparing=hasTrack=acceptImport=true;
    savedToken=saveDuration=0;selectedToken=42;
    mailbox.response.responseMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;
    mailbox.response.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;
    mailbox.response.flags=SUSAMUNE_GHOST_RESPONSE_READY;
    init();sRefreshQueued[0]=sRefreshQueued[1]=false;
}
static void info(SusamuneGhostSlotInfo *out,bool imported) {
    memset(out,0,sizeof(*out));out->generation=17;
    out->flags=SUSAMUNE_GHOST_SLOT_PRESENT|(imported?SUSAMUNE_GHOST_SLOT_IMPORTED:0);
    out->gameId=SUSAMUNE_GHOST_GAME_ID_JP;out->region=SUSAMUNE_GHOST_REGION_JP;
    out->canonicalVersion=SUSAMUNE_GHOST_FILE_VERSION_V4;
    out->requiredFeatures=SUSAMUNE_GHOST_SUPPORTED_REQUIRED_FEATURES_V4;
    out->sampleCodec=SUSAMUNE_GHOST_CODEC_POSE_ATTACHMENTS;
    out->recordingMode=SUSAMUNE_GHOST_RECORDING_POSE_QF;
    out->sampleIntervalQf=SUSAMUNE_GHOST_TRANSFORM_INTERVAL_QF;
    out->sampleCount=2;out->durationQf=8;
    out->payloadSize=SUSAMUNE_GHOST_V4_SAMPLE_DATA_OFFSET+2*SUSAMUNE_GHOST_POSE_SAMPLE_SIZE;
    out->resultQf=SUSAMUNE_GHOST_RESULT_QF_NONE;
    out->routeArea=2;out->routeParentArea=SUSAMUNE_GHOST_ROUTE_PARENT_NONE;
    out->routeVariant=SUSAMUNE_GHOST_ROUTE_VARIANT_NONE;
    out->nameLength=1;out->name[0]='A';
}
static void makePage(u32 total,u32 firstId=800,u64 duration=0) {
    SusamuneGhostCatalogPage *page=(SusamuneGhostCatalogPage*)payload;
    memset(page,0,sizeof(*page));page->magic=SUSAMUNE_GHOST_CATALOG_PAGE_MAGIC;
    page->version=SUSAMUNE_GHOST_CATALOG_PAGE_VERSION;
    page->first=mailbox.request.slot;page->totalCount=total;
    u32 remain=total>page->first?total-page->first:0;
    page->count=remain<SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES?remain:SUSAMUNE_GHOST_CATALOG_PAGE_ENTRIES;
    if(!duration)duration=(u64)total*8;
    page->totalDurationQfLo=(u32)duration;page->totalDurationQfHi=(u32)(duration>>32);
    const bool imported=mailbox.request.profile==SUSAMUNE_GHOST_IMPORTED_PROFILE;
    for(u32 i=0;i<page->count;i++) {
        page->entries[i].id=imported?0:firstId+i;info(&page->entries[i].info,imported);
        if(imported) {
            const char leaf[]="pageAA.smsghost";
            memcpy(page->entries[i].leaf,leaf,sizeof(leaf));
            page->entries[i].leaf[4]='A'+page->first/16;
            page->entries[i].leaf[5]='A'+i;
        }
    }
}
static void ack(s32 status=0,u32 generation=17,u32 resolved=800) {
    SusamuneGhostStorageResponse *response=&mailbox.response;
    memset(response,0,sizeof(*response));response->responseMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;
    response->protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;
    response->flags=SUSAMUNE_GHOST_RESPONSE_READY;response->ackSeq=mailbox.request.requestSeq;
    response->profile=mailbox.request.profile;response->generation=generation;response->status=status;
    if(!status) {
        const u16 command=mailbox.request.command;
        if(command==SUSAMUNE_GHOST_CMD_LIST||command==SUSAMUNE_GHOST_CMD_IMPORT_SCAN) {
            response->payloadSize=sizeof(SusamuneGhostCatalogPage);
            response->slotCount=((SusamuneGhostCatalogPage*)payload)->count;
        } else {
            response->slot=command==SUSAMUNE_GHOST_CMD_SAVE?resolved:mailbox.request.slot;
            if(command==SUSAMUNE_GHOST_CMD_LOAD)response->payloadSize=SUSAMUNE_GHOST_FILE_HEADER_SIZE;
        }
    }
    update();
}
static void ready(bool imported=false,u32 offset=0,u32 total=64,u32 firstId=800) {
    refreshPage(imported,offset);makePage(total,firstId);ack();
}
EXPORT wide_catalog() {
    reset();CHECK(refreshPage(false,48));makePage(50000,70000,0x100000010ull);ack();
    CHECK(catalogReady()&&totalCount(false)==50000&&pageCount(false)==16);
    CHECK(pageOffset(false)==48&&totalDurationQf()==0x100000010ull);
    Identity selected;CHECK(copyIdentity(false,15,&selected)&&selected.id==70015);
    CHECK(!slot(16)&&!slot(-1)&&!copyIdentity(false,16,&selected));
    ready(true,16,60);CHECK(importedCatalogReady()&&totalCount(true)==60);
    CHECK(pageCount(true)==16&&importedOverflowCount()==0);
    return 0;
}
EXPORT invalid_catalog(int test) {
    reset();CHECK(refreshPage(test==4,0));makePage(test==5?1:16);
    SusamuneGhostCatalogPage *page=(SusamuneGhostCatalogPage*)payload;
    switch(test) {
        case 0:page->magic=0;break;
        case 1:page->count=17;break;
        case 2:page->first=16;break;
        case 3:page->entries[1].id=page->entries[0].id;break;
        case 4:page->entries[0].leaf[0]='/';break;
        case 5:page->entries[1].id=99;break;
        case 6:page->totalDurationQfHi=1;break;
        case 7:page->entries[0].info.sampleCount=0;break;
    }
    ack();CHECK(!catalogReady()&&!importedCatalogReady());return 0;
}
EXPORT queued_page() {
    reset();CHECK(refreshPage(false,0));
    SusamuneGhostStorageRequest request=mailbox.request;
    payload[0]=0xCA;CHECK(refreshPage(false,32));
    CHECK(!memcmp(&request,&mailbox.request,sizeof(request))&&payload[0]==0xCA);
    makePage(64);ack();CHECK(!busy()&&!catalogReady()&&pageOffset(false)==32);
    update();CHECK(busy()&&mailbox.request.slot==32);
    makePage(64,900);ack();CHECK(catalogReady()&&slot(0)&&pageOffset(false)==32);
    return 0;
}
EXPORT offpage_load(int imported) {
    reset();ready(imported,0);Identity selected;CHECK(copyIdentity(imported,0,&selected));
    ready(imported,16,64,900);CHECK(identityValid(selected)&&load(selected));
    CHECK(mailbox.request.slot==selected.id&&mailbox.request.expectedGeneration==17);
    if(imported)CHECK(mailbox.request.payloadSize==96&&!memcmp(payload,selected.leaf,96));
    else CHECK(mailbox.request.payloadSize==0);
    ack();CHECK(playbackImports==1&&isLoaded(selected));
    if(imported)CHECK(loadedImported());else CHECK(loadedSlot()==800);
    ready(imported,32,64,1000);CHECK(isLoaded(selected));
    CHECK(remove(selected));ack();CHECK(!pinned&&!isLoaded(selected));return 0;
}
EXPORT namespace_and_staleness(int test) {
    reset();ready();Identity selected;CHECK(copyIdentity(false,0,&selected));
    if(test==0) {testProfile=1;CHECK(!identityValid(selected)&&!load(selected));return 0;}
    CHECK(loadObserver(selected,false));
    if(test==1)onSavestateLoaded();
    if(test==2)preparing=false;
    ack(0,test==3?18:17);
    CHECK(observerImports==0&&observerStops>0&&!busy());return 0;
}
EXPORT allocate_save(int test) {
    reset();CHECK(!catalogReady());
    if(test==0) {CHECK(!saveNew(43)&&!busy());return 0;}
    CHECK(saveNew(42)&&mailbox.request.slot==SUSAMUNE_GHOST_SLOT_AUTO);
    CHECK(mailbox.request.payloadSize==SUSAMUNE_GHOST_FILE_HEADER_SIZE);
    if(test==1) {ack(0,1,70000);CHECK(savedToken==42&&saveDuration==1234&&checkpoints==1);}
    if(test==2) {ack(SUSAMUNE_GHOST_STATUS_IO(1));CHECK(!savedToken&&!checkpoints);}
    if(test==3) {
        for(u32 i=0;i<=1800;i++)update();
        CHECK(timedOut()&&busy()&&!savedToken);ack(0,1,70000);
        CHECK(!timedOut()&&!busy()&&savedToken==42);
    }
    return 0;
}
EXPORT import_scan(int queued) {
    reset();if(queued)CHECK(refreshPage(false,0));
    CHECK(scanImports());
    if(queued) {makePage(0);ack();update();}
    CHECK(mailbox.request.command==SUSAMUNE_GHOST_CMD_IMPORT_SCAN);
    CHECK(mailbox.request.profile==SUSAMUNE_GHOST_IMPORTED_PROFILE&&mailbox.request.slot==0);
    makePage(100);ack();CHECK(importedCatalogReady()&&totalCount(true)==100);return 0;
}
EXPORT empty_final_page() {
    reset();CHECK(refreshPage(false,32));makePage(32);ack();
    CHECK(pageOffset(false)==16);update();CHECK(mailbox.request.slot==16);
    makePage(32);ack();CHECK(pageCount(false)==16);return 0;
}
EXPORT zero_generation(int imported) {
    reset();CHECK(refreshPage(imported,0));makePage(1);
    ((SusamuneGhostCatalogPage*)payload)->entries[0].info.generation=0;ack();
    Identity selected;CHECK(copyIdentity(imported,0,&selected)&&selected.generation==0);
    CHECK(load(selected)&&mailbox.request.expectedGeneration==0);ack(0,0);
    CHECK(playbackImports==1&&isLoaded(selected));return 0;
}
EXPORT unsafe_record(int imported) {
    reset();CHECK(refreshPage(imported,0));makePage(1);
    SusamuneGhostSlotInfo *raw=&((SusamuneGhostCatalogPage*)payload)->entries[0].info;
    memset(raw,0,sizeof(*raw));raw->flags=SUSAMUNE_GHOST_SLOT_UNSAFE;
    if(imported)raw->flags|=SUSAMUNE_GHOST_SLOT_PRESENT|SUSAMUNE_GHOST_SLOT_IMPORTED;
    raw->status=SUSAMUNE_GHOST_STATUS_SLOT_UNSAFE;ack();
    Identity selected;CHECK(copyIdentity(imported,0,&selected));
    CHECK(!load(selected)&&!exportShare(selected)&&remove(selected));return 0;
}
EXPORT identity_integrity() {
    reset();ready(true);Identity first,other;CHECK(copyIdentity(true,0,&first));
    CHECK(copyIdentity(true,1,&other)&&!sameIdentity(first,other));
    other=first;other.name[0]='B';CHECK(sameIdentity(first,other));
    other.leaf[0]='/';CHECK(!identityValid(other)&&!remove(other));
    first.name[0]=' ';char name[48];CHECK(copyIdentityName(first,name,sizeof(name)));
    CHECK(!memcmp(name,"Unnamed ghost",14));return 0;
}
'''
        cfile = work / "paging.cpp"
        cfile.write_text(source, encoding="ascii")
        library = work / "paging.dll"
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fno-builtin", "-fno-exceptions", "-fno-rtti",
                        "-fuse-ld=lld", "-Xlinker", "/noentry", "-I", str(ROOT / "include"),
                        str(cfile), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def check_cases(self, name, cases):
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(getattr(self.dll, name)(case), 0,
                                 "PPC fixture assertion failed at generated source line")

    def test_catalogs_page_beyond_old_counts_and_ten_hour_quota(self):
        self.assertEqual(self.dll.wide_catalog(), 0)

    def test_malformed_pages_are_never_published(self):
        self.check_cases("invalid_catalog", range(8))

    def test_queued_page_preserves_mailbox_and_ignores_old_page_ack(self):
        self.assertEqual(self.dll.queued_page(), 0)

    def test_copied_selections_load_and_delete_after_page_changes(self):
        self.check_cases("offpage_load", range(2))

    def test_profile_changes_and_stale_observer_loads_are_rejected(self):
        self.check_cases("namespace_and_staleness", range(4))

    def test_auto_save_uses_selected_recording_and_waits_for_ack(self):
        self.check_cases("allocate_save", range(4))

    def test_import_scan_keeps_its_command_when_idle_or_queued(self):
        self.check_cases("import_scan", range(2))

    def test_deleting_last_page_returns_to_remaining_records(self):
        self.assertEqual(self.dll.empty_final_page(), 0)

    def test_zero_crc_and_wrapped_personal_generation_are_valid(self):
        self.check_cases("zero_generation", range(2))

    def test_quarantined_files_remain_visible_and_deletable(self):
        self.check_cases("unsafe_record", range(2))

    def test_import_identity_uses_exact_leaf_and_names_remain_visible(self):
        self.assertEqual(self.dll.identity_integrity(), 0)


if __name__ == "__main__":
    unittest.main()
