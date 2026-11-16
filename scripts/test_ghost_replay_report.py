"""Actual replay-report worker with checked memory proof and failing FatFS."""
import ctypes as C
import importlib.util
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

P = Path(__file__).resolve().parents[1]
ROOT = P
while not (ROOT / "scripts/ghost_kernel_fixture.h").exists():
    ROOT = ROOT.parent
MAGIC, END, BOOT, FILE_NONCE, RUN, GAME = 0x4d535250, 0x4d535245, 0x12345678, 0x11223344, 0x55667788, 0x474d5350
OK, BAD_REQUEST, BAD_PAYLOAD, NO_STORAGE, IO, EXISTS, STALE = range(7)

def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value

def payload(actors=0):
    size = 320 + actors * 256
    data = bytearray(struct.pack(">16I", MAGIC, 1, 64, size, GAME, FILE_NONCE, RUN, 119,
                                 0, actors, 256, 0, 0x87654321, 511, actors, 0))
    data.extend(bytes((i * 13) & 255 for i in range(256)))
    for i in range(actors):
        data.extend(struct.pack(">2I", (0xdeadbeef + i) & 0xffffffff, 0x80000000 + i))
        data.extend(bytes((i * 7 + n * 11) & 255 for n in range(244)))
        data.extend(bytes(4))
    assert len(data) == size
    return data

ADAPTER = r'''
#include "susamune/ghost_replay_report.h"
#include "susamune/susamune_cfg.h"
typedef int FRESULT;
static struct SusamuneCfg reportCfg;
static struct MoonshineGhostMemoryProof reportProof;
static struct MsReplayReportMailbox reportBox;
static unsigned char reportData[MS_REPLAY_REPORT_MAX_BYTES+64] __attribute__((aligned(32)));
#undef SUSAMUNE_CFG_PHYS_PTR
#define SUSAMUNE_CFG_PHYS_PTR (&reportCfg)
static unsigned closeFailure,readFailure,renameFailure,unlinkFailure,statFailure,openFailure;
static unsigned corruption,sourceReads,cacheErrors,responseWrites,openHandles;
static int f_close(FIL*f){if(closeFailure)return FR_DISK_ERR;int r=fixture_close(f);if(r==FR_OK)--openHandles;return r;}
static int f_open_char(FIL*f,const char*p,unsigned flags){if(openFailure)return FR_DISK_ERR;int r=fixture_open(f,p,flags);if(r==FR_OK)++openHandles;return r;}
static int f_read(FIL*f,void*p,UINT n,UINT*done){if(readFailure){*done=0;return FR_DISK_ERR;}return fixture_read(f,p,n,done);}
static int f_write(FIL*f,const void*p,UINT n,UINT*done){
 unsigned before=f->position;int r=fixture_write(f,p,n,done);
 if(r==FR_OK&&*done&&corruption==1&&before==0&&*done>128)((unsigned char*)testFiles[f->index].bytes)[128]^=1;
 if(r==FR_OK&&*done==32&&corruption==2&&MsReplayReportGet(p)==MS_REPLAY_REPORT_END_MAGIC)((unsigned char*)testFiles[f->index].bytes)[before+31]=1;
 return r;
}
static int f_rename_char(const char*a,const char*b){return renameFailure?FR_DISK_ERR:fixture_rename(a,b);}
static int f_unlink_char(const char*p){return unlinkFailure?FR_DISK_ERR:fixture_unlink(p);}
static int f_stat_char(const char*p,FILINFO*i){return statFailure?FR_DISK_ERR:fixture_stat(p,i);}
static void sync_before_read(void*p,unsigned n){
 __UINTPTR_TYPE__ start=(__UINTPTR_TYPE__)p,base=(__UINTPTR_TYPE__)(reportData+32);
 if(start>=(__UINTPTR_TYPE__)reportData&&start<(__UINTPTR_TYPE__)(reportData+sizeof(reportData))){
  ++sourceReads;if(start<base||start+n<start||start+n>base+MS_REPLAY_REPORT_MAX_BYTES)++cacheErrors;
 }
 fixture_before(p,n);
}
static void sync_after_write(void*p,unsigned n){
 if(p==(void*)&reportBox.response){++responseWrites;if(n!=32)++cacheErrors;}
 else if(p==(void*)&reportBox.request){if(n!=32)++cacheErrors;}
 else ++cacheErrors;
 fixture_after(p,n);
}
'''
EXPORTS = r'''
#define API __declspec(dllexport)
static void proof(unsigned nonce){
 unsigned v[16]={MOONSHINE_GHOST_MEMORY_MAGIC,1,nonce,0x003a1820,0,0x04000000,0x04000000,
  0x90000800,0x935e0000,0x935e0000,0x93600000,0x93600000,0x933e0000,0x93400000,0x474d5350,0};
 memcpy(&reportProof,v,64);reportProof.word[MGM_CHECKSUM]=MoonshineGhostMemoryChecksum(&reportProof);
}
API void reset(unsigned valid){
 testCount=writeCount=writeBytes=readBytes=readCalls=dirCalls=openCalls=maxRead=0;
 failWriteAfter=0xffffffffu;failSync=0;directoryResult=FR_OK;
 closeFailure=readFailure=renameFailure=unlinkFailure=statFailure=openFailure=0;
 corruption=sourceReads=cacheErrors=responseWrites=openHandles=0;storageAvailable=1;
 testStoragePrefix=MOONSHINE_DATA_ROOT;GAME_ID=0x474d5350;reportInitialized=0;
 memset(testFiles,0,sizeof(testFiles));memset(&reportStorage,0xa5,sizeof(reportStorage));
 memset(&reportBox,0xa5,sizeof(reportBox));memset(reportData,0xa5,sizeof(reportData));
 memset(&reportCfg,0,sizeof(reportCfg));reportCfg.magic=SUSAMUNE_CFG_MAGIC;reportCfg.version=SUSAMUNE_CFG_VERSION;reportCfg.flags=MOONSHINE_GHOST_MEMORY_FLAG;
 proof(0x12345678);if(!valid)reportProof.word[MGM_CHECKSUM]^=1;
 GhostReplayReportInit();
}
API void init(void){GhostReplayReportInit();}
API void setProof(unsigned nonce,unsigned valid){proof(nonce);if(!valid)reportProof.word[MGM_CHECKSUM]^=1;}
API void volume(unsigned usb){testStoragePrefix=usb?"1:" MOONSHINE_DATA_ROOT:MOONSHINE_DATA_ROOT;}
API void available(unsigned yes){storageAvailable=yes;}
API void fill(const void*p,unsigned n){if(n<=MS_REPLAY_REPORT_MAX_BYTES)memcpy(reportData+32,p,n);}
API void submit(const void*p){memcpy(&reportBox.request,p,32);}
API const void*response(void){return &reportBox.response;}
API const void*request(void){return &reportBox.request;}
API unsigned pending(void){return GhostReplayReportPending();}
API unsigned phase(void){return REPORT_WRITER->phase;}
API unsigned owned(void){return REPORT_WRITER->owned;}
API unsigned openCount(void){return openHandles;}
API unsigned cached(void){return sourceReads;}
API unsigned syncErrors(void){return cacheErrors;}
API unsigned controlBytes(void){return sizeof(struct ReplayReportWriter);}
API unsigned ackWrites(void){return responseWrites;}
API int step(unsigned count){
 for(unsigned i=0;i<count&&GhostReplayReportPending();++i){
  unsigned beforeWrite=writeBytes,beforeRead=readBytes;
  GhostReplayReportService();
  if(writeBytes-beforeWrite>0x4000||readBytes-beforeRead>0x4000)return -1;
 }
 return GhostReplayReportPending()?1:0;
}
API void fault(unsigned kind,unsigned value){
 switch(kind){
 case 0:closeFailure=value;break;case 1:unlinkFailure=value;break;
 case 2:renameFailure=value;break;case 3:readFailure=value;break;
 case 4:failSync=value;break;case 5:failWriteAfter=value;break;
 case 6:statFailure=value;break;case 7:openFailure=value;break;
 case 8:corruption=value;break;case 9:directoryResult=value;break;
 }
}
API void mutate(unsigned offset,unsigned value){if(offset<MS_REPLAY_REPORT_MAX_BYTES)reportData[32+offset]=(unsigned char)value;}
API const void*source(void){return reportData+32;}
API const void*file(const char*p,unsigned*n){int i=lookup(p);if(i<0){*n=0;return NULL;}*n=testFiles[i].size;return testFiles[i].bytes;}
API void install(const char*name,const void*p,unsigned n){
 int i=lookup(name);if(i<0)i=testCount++;copystr(testFiles[i].path,name);
 testFiles[i].live=1;testFiles[i].writable=0;testFiles[i].bytes=p;testFiles[i].size=n;
}
API unsigned guards(void){
 for(unsigned i=0;i<8;++i)if(reportStorage.before[i]!=0xa5a5a5a5||reportStorage.after[i]!=0xa5a5a5a5)return 0;
 for(unsigned i=0;i<32;++i)if(reportData[i]!=0xa5||reportData[MS_REPLAY_REPORT_MAX_BYTES+32+i]!=0xa5)return 0;
 return 1;
}
'''
class ReplayReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pr62-report-")
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        fixture = (ROOT / "scripts/ghost_kernel_fixture.h").read_text()
        fixture = fixture.replace("#define FIXTURE_FILES 60000", "#define FIXTURE_FILES 20")
        fixture = fixture.replace("#define FIXTURE_WRITES 80", "#define FIXTURE_WRITES 6")
        fixture = fixture.replace("#define FIXTURE_FILE_BYTES 1400000", "#define FIXTURE_FILE_BYTES 400000")
        renames = {"f_close":"fixture_close","f_open_char":"fixture_open","f_read":"fixture_read",
                   "f_write":"fixture_write","f_rename_char":"fixture_rename","f_unlink_char":"fixture_unlink",
                   "f_stat_char":"fixture_stat","sync_before_read":"fixture_before","sync_after_write":"fixture_after"}
        for name, replacement in renames.items():
            fixture = fixture.replace(name + "(", replacement + "(")
        fixture = fixture.replace("static bool SusamuneCfgStorageAvailable(void) { return true; }",
                                  "static unsigned storageAvailable=1;static bool SusamuneCfgStorageAvailable(void){return storageAvailable;}")
        source = (P / "launcher/kernel/GhostReplayReport.c").read_text()
        source = re.sub(r"^#include .*$", "", source, flags=re.M)
        source = source.replace("#define REPORT_WRITER ((struct ReplayReportWriter*)(MS_TRACE_CONTROL_PHYS+MS_REPLAY_REPORT_ARM_OFFSET))",
                                "static struct {unsigned before[8];struct ReplayReportWriter writer;unsigned after[8];}reportStorage;\n#define REPORT_WRITER (&reportStorage.writer)")
        source = source.replace("#define REPORT_BOX ((volatile struct MsReplayReportMailbox*)MS_REPLAY_REPORT_MAILBOX_PHYS)", "#define REPORT_BOX (&reportBox)")
        source = source.replace("#define REPORT_DATA ((const unsigned char*)MS_REPLAY_REPORT_DATA_PHYS)", "#define REPORT_DATA (reportData+32)")
        source = source.replace("(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE", "&reportProof")
        (folder / "test.c").write_text("#define MOONSHINE_GHOST_TRACE 1\n" + fixture + ADAPTER + source + EXPORTS)
        command = ["C:/msys64/mingw64/bin/gcc.exe","-shared","-static","-O2","-std=gnu99","-fno-builtin",
                   "-I",str(P/"include"),"-I",str(ROOT/"include"),"-I",str(ROOT/"include/susamune"),
                   str(folder/"test.c"),"-o",str(folder/"test.dll")]
        result = subprocess.run(command,capture_output=True,text=True,
                                env=dict(os.environ,PATH="C:/msys64/mingw64/bin;"+os.environ["PATH"]))
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        cls.lib=C.CDLL(str(folder/"test.dll"))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.fill.argtypes=[C.c_void_p,C.c_uint]
        cls.lib.submit.argtypes=[C.c_void_p]
        cls.lib.file.argtypes=[C.c_char_p,C.POINTER(C.c_uint)]
        cls.lib.install.argtypes=[C.c_char_p,C.c_void_p,C.c_uint]
        for name in ("response","request","file","source"):
            getattr(cls.lib,name).restype=C.c_void_p

    def setUp(self):
        self.lib.reset(1)
        self.owners=[]

    def response(self):
        return struct.unpack("<8I",C.string_at(self.lib.response(),32))

    def path(self,sequence=1,suffix="bin",usb=False,boot=BOOT):
        return f'{"1:" if usb else ""}/Moonshine data/logs/replay_{boot:08X}_{sequence:08X}.{suffix}'.encode()

    def file(self,path):
        size=C.c_uint();pointer=self.lib.file(path,C.byref(size))
        return C.string_at(pointer,size.value) if pointer else None

    def install(self,path,data):
        owner=C.create_string_buffer(data);self.owners.append(owner)
        self.lib.install(path,owner,len(data))

    def request(self,data,sequence=1,**changes):
        words=[MAGIC,1,BOOT,sequence,len(data),FILE_NONCE,RUN,fnv(data)]
        keys=("magic","version","bootNonce","sequence","payloadBytes","fileNonce","run","checksum")
        for key,value in changes.items():
            words[keys.index(key)]=value
        self.lib.fill(bytes(data),len(data))
        raw=struct.pack("<8I",*words);self.lib.submit(raw);return raw

    def settle(self):
        for _ in range(2000):
            result=self.lib.step(1)
            self.assertNotEqual(result,-1,"Service exceeded16KiB I/O budget")
            if not result:
                self.assertEqual(self.lib.guards(),1)
                self.assertEqual(self.lib.syncErrors(),0)
                return
        self.fail("report worker did not settle")

    def until(self,phase):
        for _ in range(2000):
            if self.lib.phase()==phase:return
            self.assertGreaterEqual(self.lib.step(1),0)
        self.fail(f"phase{phase} not reached")

    def test_minimum_report_matches_payload_and_checked_footer(self):
        data=payload();self.request(data);self.settle()
        self.assertEqual(self.response(),(MAGIC,1,BOOT,1,OK,len(data),0,0))
        expected=bytes(data)+struct.pack(">8I",END,1,BOOT,1,len(data),fnv(data),0,0)
        self.assertEqual(self.file(self.path()),expected)
        self.assertIsNone(self.file(self.path(suffix="part")))
        self.assertEqual(self.lib.openCount(),0)

    def test_maximum_actor_count_and_arbitrary_addresses_are_data_only(self):
        data=payload(1024);self.request(data);self.settle()
        self.assertEqual(self.response()[4:6],(OK,len(data)))
        self.assertEqual(self.file(self.path())[:-32],bytes(data))
        self.assertEqual(C.string_at(self.lib.source(),len(data)),bytes(data))
        self.assertLessEqual(self.lib.controlBytes(),1024)

    def test_invalid_proof_init_never_publishes_or_accepts(self):
        self.lib.reset(0)
        self.assertEqual(C.string_at(self.lib.response(),32),b"\xa5"*32)
        self.request(payload())
        self.assertEqual(self.lib.pending(),0);self.lib.init()
        self.assertEqual(self.lib.ackWrites(),0);self.assertEqual(self.lib.cached(),0)

    def test_bad_request_shapes_reject_before_payload_access(self):
        for change in ({"magic":0},{"version":2},{"bootNonce":BOOT+1},{"fileNonce":0},{"run":0},
                       {"payloadBytes":319},{"payloadBytes":321},{"payloadBytes":320+1025*256},
                       {"payloadBytes":393248}):
            with self.subTest(change=change):
                self.lib.reset(1);self.request(payload(),**change);self.settle()
                self.assertEqual(self.response()[3:6],(1,BAD_REQUEST,0))
                self.assertEqual(self.lib.cached(),0);self.assertIsNone(self.file(self.path()))

    def test_zero_sequence_is_no_request(self):
        self.request(payload(),sequence=0)
        self.assertEqual(self.lib.pending(),0);self.assertEqual(self.response()[3],0)

    def test_header_shape_and_identity_are_checked(self):
        for offset,value in ((0,0),(4,2),(8,32),(12,321),(16,0x474d534a),(20,1),(24,2),(36,1),(40,244),(60,1)):
            with self.subTest(offset=offset):
                self.lib.reset(1);data=payload();struct.pack_into(">I",data,offset,value)
                self.request(data);self.settle()
                self.assertEqual(self.response()[4],BAD_PAYLOAD)
                self.assertIsNone(self.file(self.path()))

    def test_partial_snapshot_status_is_diagnostic_not_a_count_contract(self):
        data=payload(2);struct.pack_into(">I",data,44,4);struct.pack_into(">I",data,56,0)
        self.request(data);self.settle();self.assertEqual(self.response()[4],OK)

    def test_actor_padding_and_checksum_are_verified_from_disk(self):
        for padding in (False,True):
            self.lib.reset(1);data=payload(1)
            if padding:data[320+252]=1
            self.request(data,checksum=fnv(data) if padding else fnv(data)^1);self.settle()
            self.assertEqual(self.response()[4],BAD_PAYLOAD)
            self.assertIsNone(self.file(self.path()));self.assertIsNone(self.file(self.path(suffix="part")))

    def test_readback_detects_payload_or_footer_corruption(self):
        for corruption in (1,2):
            self.lib.reset(1);self.lib.fault(8,corruption);self.request(payload());self.settle()
            self.assertEqual(self.response()[4],BAD_PAYLOAD)
            self.assertIsNone(self.file(self.path()))

    def test_source_mutation_before_write_cannot_change_validated_header(self):
        data=payload();self.request(data);self.lib.step(1)
        self.lib.mutate(20,0);self.lib.mutate(21,0);self.settle()
        self.assertEqual(self.response()[4],BAD_PAYLOAD);self.assertIsNone(self.file(self.path()))

    def test_source_mutation_of_unwritten_tail_fails_checksum(self):
        data=payload(100);self.request(data);self.until(2)
        self.lib.step(1);self.lib.mutate(20000,(data[20000]+1)&255);self.settle()
        self.assertEqual(self.response()[4],BAD_PAYLOAD);self.assertIsNone(self.file(self.path()))

    def test_short_write_sync_read_and_rename_errors_cleanup_before_ack(self):
        for kind,value in ((5,10),(4,1),(3,1),(2,1),(6,1),(7,1),(9,1)):
            self.lib.reset(1);self.request(payload());self.lib.fault(kind,value);self.settle()
            self.assertEqual(self.response()[4],IO)
            self.assertEqual(self.lib.openCount(),0)
            self.assertIsNone(self.file(self.path()));self.assertIsNone(self.file(self.path(suffix="part")))

    def test_close_failure_keeps_lease_and_init_is_idempotent(self):
        data=payload();request=self.request(data);self.until(5)
        self.lib.fault(0,1);self.lib.step(10);self.lib.init()
        self.assertEqual(self.response()[3],0);self.assertEqual(self.lib.openCount(),1)
        self.assertEqual(C.string_at(self.lib.request(),32),request);self.assertEqual(self.lib.pending(),1)
        self.lib.fault(0,0);self.settle()
        self.assertEqual(self.response()[3:5],(1,OK))

    def test_failed_close_during_cleanup_never_acknowledges_early(self):
        self.request(payload(),checksum=0);self.until(7)
        self.lib.fault(0,1);self.lib.step(20);self.lib.init()
        self.assertEqual(self.response()[3],0);self.assertEqual(self.lib.openCount(),1)
        self.lib.fault(0,0);self.settle();self.assertEqual(self.response()[4],BAD_PAYLOAD)

    def test_unlink_failure_keeps_pending_ownership_until_settled(self):
        self.request(payload(),checksum=0);self.lib.fault(1,1);self.until(11)
        self.lib.step(10);self.lib.init()
        self.assertEqual(self.response()[3],0);self.assertEqual(self.lib.owned(),1);self.assertEqual(self.lib.openCount(),0)
        self.lib.fault(1,0);self.settle();self.assertEqual(self.response()[3:5],(1,BAD_PAYLOAD))

    def test_existing_final_or_part_is_never_overwritten_or_deleted(self):
        for suffix in ("bin","part"):
            self.lib.reset(1);old=b"existing report"
            self.install(self.path(suffix=suffix),old);self.request(payload());self.settle()
            self.assertEqual(self.response()[4],EXISTS)
            self.assertEqual(self.file(self.path(suffix=suffix)),old)

    def test_final_collision_at_publication_preserves_existing_final(self):
        self.request(payload());self.until(10)
        self.install(self.path(),b"other committed report");self.settle()
        self.assertEqual(self.response()[4],EXISTS)
        self.assertEqual(self.file(self.path()),b"other committed report")
        self.assertIsNone(self.file(self.path(suffix="part")))

    def test_changed_request_is_not_acknowledged_for_old_source(self):
        original=self.request(payload());self.until(2)
        changed=bytearray(original);struct.pack_into("<I",changed,12,2);self.lib.submit(bytes(changed))
        self.lib.fault(0,1);self.lib.step(4);self.assertEqual(self.response()[3],0)
        self.lib.fault(0,0)
        for _ in range(8):
            self.lib.step(1)
            if self.response()[3]==1:break
        self.assertEqual(self.response()[3:6],(1,STALE,0))
        self.assertIsNone(self.file(self.path()))
        self.settle();self.assertEqual(self.response()[3:5],(2,OK))

    def test_proof_loss_drains_without_more_source_access(self):
        self.request(payload(100));self.until(2);reads=self.lib.cached()
        self.lib.setProof(BOOT,0);self.lib.init();self.settle()
        self.assertEqual(self.response()[3:6],(1,STALE,0))
        self.assertEqual(self.lib.cached(),reads);self.assertEqual(self.lib.openCount(),0)

    def test_new_epoch_does_not_reset_busy_owner(self):
        request=self.request(payload());self.until(2)
        self.lib.fault(0,1);self.lib.setProof(BOOT+1,1);self.lib.init();self.lib.step(4)
        self.assertEqual(self.response()[2:4],(BOOT,0));self.assertEqual(C.string_at(self.lib.request(),32),request)
        self.lib.fault(0,0);self.settle();self.assertEqual(self.response()[3:5],(1,STALE))
        self.lib.init();self.assertEqual(self.response()[2:4],(BOOT+1,0))

    def test_no_storage_and_launcher_volume(self):
        self.lib.available(0);self.request(payload());self.settle()
        self.assertEqual(self.response()[4],NO_STORAGE)
        self.lib.reset(1);self.lib.volume(1);self.request(payload());self.settle()
        self.assertEqual(self.response()[4],OK);self.assertIsNotNone(self.file(self.path(usb=True)))

if __name__=="__main__":
    unittest.main()
