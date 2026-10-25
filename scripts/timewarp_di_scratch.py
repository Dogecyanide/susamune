"""Host proof of the production DI limit/fence; task-local traces and receipts."""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import subprocess

from test_fatfs_contiguous_reads import compile_reader
from test_launcher_iso_cache import FIXTURE, EXPORTS
from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]
SIZES = (0x80000, 0x20000, 0x10000)
RELEASE = Path("C:/Users/Dogec/.codex/worktrees/4e33/susamune")
TRACES = {
    "pal-lifecycle": RELEASE / "build/v2.3.3-feedback5/final-lifecycle/profile-20261007-173306/Logs/dolphin.log",
    "pal-boot": RELEASE / "build/foxtrot-bianco5/pal/profile/Logs/dolphin.log",
}

SUPPORT = r'''
#define NULL 0
typedef unsigned short u16;
static u64 ioOffset[100000];static u32 ioLength[100000],ioCount;
static u32 chunks,patches,syncs,acks,badOrder,badData,phase;
static u32 requestedOffset,requestedLength,RealDiscCMD,FSTMode,Patch31A0Backup;
static u32 tailOwned;
static u32 DI_Thread=2,currentThread=1;
static int DI_Handle=24,ioctlFailure,fenceResult;
static bool DI_IRQ,delayedIRQ;
static u32 queuedBefore,queuedAfter,drainedBeforeLimit,drainedAfterLimit;
static u32 fenceAcks,fenceAckLimit,ioctlCalls,finishPolls,interruptCalls,queueFailures;
static void drainQueued();
static u32 thread_get_id(){return currentThread;}
static bool DiscCheckAsync(){++finishPolls;return queuedBefore==0;}
static void CheckOSReport(){}static void BTUpdateRegisters(){}
static void DIInterrupt(){++interruptCalls;if(!delayedIRQ)DI_IRQ=false;}
static void DIFinishAsync();
static int IOS_Ioctl(int,int,void*,int,void*,int);
bool DIReserveScratchTail(void);
static const char *GamePath="private";
static const u8 *di_src;static char *di_dest;static u32 di_length,di_offset;
alignas(32) static u8 destination[0x900000+64];
static void ioLog(u64 offset,u32 length){if(ioCount<100000){ioOffset[ioCount]=offset;ioLength[ioCount]=length;}++ioCount;}
static u64 filePosition;
static u32 failRead,shortRead;
static void f_lseek(FIL*,u64 p){filePosition=p;}
static void f_read(FIL*,void*dst,u32 n,UINT*actual){
 ++reads;bytesRead+=n;lastReadSize=n;lastReadOffset=filePosition;ioLog(filePosition,n);
 u8*out=(u8*)dst;
 bool cached=out>=CACHE_START&&out<=CACHE_START+CACHE_SIZE&&n<=(u32)(CACHE_START+CACHE_SIZE-out);
 bool scratchOk=out>=DI_READ_BUFFER&&out<=DI_READ_BUFFER+DI_READ_BUFFER_LENGTH&&n<=(u32)(DI_READ_BUFFER+DI_READ_BUFFER_LENGTH-out);
 if(!cached&&!scratchOk){++overruns;*actual=0;return;}
 if(failRead&&reads==failRead){*actual=0;return;}
 u32 amount=shortRead&&n>shortRead?shortRead:n;
 for(u32 i=0;i<amount;++i)out[i]=sample(filePosition+i);
 filePosition+=amount;*actual=amount;
}
static FIL GameFile;
static bool wiiVCInternal=false,ISO_IsCISO=false;
static u32 USBReadTimer;
#define HW_TIMER 90
#define CISO_HEADER_SIZE 0x8000u
#define CISO_BLOCK_SIZE 0x200000u
#define CISO_MAP_SIZE 1024u
static unsigned short ciso_block_map[CISO_MAP_SIZE];
static void WDVD_FST_LSeek(u64 p){f_lseek(&GameFile,p);}
static u32 WDVD_FST_Read(void*p,u32 n){u32 got;f_read(&GameFile,p,n,&got);return got;}
static u32 registers[100];
static u32 read32(__UINTPTR_TYPE__ address){return address<100?registers[address]:*(u32*)address;}
static void sync_before_read(const void*,u32){}
static u8 expected(u64 logical){
 if(ISO_IsCISO&&!RealDiscCMD){u32 block=(u32)(logical/CISO_BLOCK_SIZE);u32 part=(u32)(logical%CISO_BLOCK_SIZE);
  if(block>=CISO_MAP_SIZE||ciso_block_map[block]==0xffff)return 0;
  logical=CISO_HEADER_SIZE+(u64)ciso_block_map[block]*CISO_BLOCK_SIZE+part;}
 return sample(logical);
}
#define DIP_CMD_DVDR 0xd0
#define DIP_CMD_NORMAL 0xa8
#define DIP_STATUS 1
#define DIP_CMD_0 2
#define DIP_CMD_1 3
#define DIP_CMD_2 4
#define DIP_DMA_ADR 5
#define DIP_DMA_LEN 6
#define DIP_CONTROL 7
#define HW_GPIO_OUT 8
#define GPIO_SLOT_LED 1
#define ALIGN_BACKWARD(x,n) ((x)&~((u64)(n)-1))
#define ALIGN_FORWARD(x,n) (((x)+(n)-1)&~((n)-1))
alignas(32) static u8 realMemory[CACHE_SIZE+64];
static u8 *const DISC_FRONT_CACHE=realMemory+32;
static u8 *const DISC_DRIVE_BUFFER=realMemory+32+0x800;
static u8 *const DISC_TMP_CACHE=realMemory+32+CACHE_SIZE-0x800;
static const u32 DISC_DRIVE_BUFFER_LENGTH=CACHE_SIZE-0x1000;
static u64 DVD_OFFSET64=~0ull;
static u32 WaitForRead,WaitForWrite;static bool access_led=false;
static void udelay(u32){WaitForRead=WaitForWrite=0;drainQueued();}
static void set32(u32,u32){}static void clear32(u32,u32){}
static void write32(u32 reg,u32 value){
 registers[reg]=value;
 if(reg==DIP_CONTROL&&value==3){
  u32 n=registers[DIP_DMA_LEN];
  u64 offset=(u64)registers[DIP_CMD_1]<<(RealDiscCMD==DIP_CMD_DVDR?11:2);
  ++reads;bytesRead+=n;ioLog(offset,n);
  if(n>DISC_DRIVE_BUFFER_LENGTH){++overruns;registers[reg]=0;return;}
  for(u32 i=0;i<n;++i)DISC_DRIVE_BUFFER[i]=sample(offset+i);
  registers[reg]=0;
 }
}
static const u8 *ReadRealDisc(u32*,u32,bool);
static void DoPatches(void *p,u32 n,u32 offset){
 ++patches;if(phase||n!=requestedLength||offset!=requestedOffset)++badOrder;
 const u8*b=(u8*)p;for(u32 i=0;i<n;++i)if(b[i]!=expected(ISOShift64+offset+i)){++badData;break;}
 // A cross-boundary consumer sees the complete destination, then changes it.
 if(n>1){((u8*)p)[0]^=0x55;((u8*)p)[n-1]^=0xaa;}phase=1;
}
static void ReadSpeed_Setup(u32 offset,u32 n){if(phase!=1||offset!=requestedOffset||n!=requestedLength)++badOrder;}
struct ipcmessage{struct{u32 command;void*buffer_io;u32 length_io;void*buffer_in;u32 length_in;}ioctl;};
typedef ipcmessage Message;
static void mqueue_ack(Message*m,int result){
 if(m->ioctl.command==DI_IOCTL_RESERVE_SCRATCH_TAIL){++fenceAcks;fenceAckLimit=GetDIBufferLimit();fenceResult=result;return;}
 if(phase!=2)++badOrder;++acks;phase=3;
}
static void finalSync(void*,u32 n){if(n!=requestedLength||phase>1)++badOrder;++syncs;phase=2;}
'''

TAIL = r'''
API void setSize(u32 n){DI_READ_BUFFER_LENGTH=n;}
API void configure(u32 mode,u32 cardBytes,u32 ciso){
 reset(cardBytes,mode==1);FSTMode=mode==2;RealDiscCMD=mode==3?DIP_CMD_DVDR:(mode==4?DIP_CMD_NORMAL:0);
 tailOwned=0;
 DI_Handle=24;currentThread=1;DI_IRQ=delayedIRQ=false;ioctlFailure=0;
 queuedBefore=queuedAfter=drainedBeforeLimit=drainedAfterLimit=0;
 fenceAcks=fenceAckLimit=ioctlCalls=finishPolls=interruptCalls=queueFailures=0;fenceResult=0;
 ISO_IsCISO=ciso!=0;for(u32 i=0;i<CISO_MAP_SIZE;++i)ciso_block_map[i]=(i%3==1)?0xffff:(unsigned short)(i-i/3);
 ioCount=chunks=patches=syncs=acks=badOrder=badData=phase=0;failRead=shortRead=0;filePosition=0;
 DVD_OFFSET64=~0ull;memset(realMemory,0xC7,sizeof(realMemory));
}
API void faults(u32 fail,u32 shortBytes){failRead=fail;shortRead=shortBytes;}
API u32 request(u32 offset,u32 length,u32 command){
 if(length>0x900000)return 0;
 requestedOffset=offset;requestedLength=length;phase=0;
 memset(destination,0xD8,length+64);
 Message message={{command,destination+32,length,(void*)(__UINTPTR_TYPE__)offset}};
 runDi(&message);
 if(phase!=3)return 0;
 for(u32 i=0;i<32;++i)if(destination[i]!=0xD8||destination[32+length+i]!=0xD8)return 0;
 for(u32 i=0;i<length;++i){u8 v=expected(ISOShift64+offset+i);if(!command&&length>1){if(!i)v^=0x55;if(i==length-1)v^=0xaa;}if(destination[32+i]!=v)return 0;}
 return 1;
}
API u32 allGuards(){if(!guards())return 0;for(u32 i=0;i<32;++i)if(realMemory[i]!=0xC7||realMemory[32+CACHE_SIZE+i]!=0xC7)return 0;return 1;}
static u8 tailByte(u32 i){return i<0x10020?0xB6:(u8)(sample(i)^0xD3);}
API void setupRuntimeCache(){ISOSetupCache();}
API u32 publishRuntime(){return DIReserveScratchTail();}
API void claimTail(){for(u32 i=0x10000;i<0x80000;++i)DI_READ_BUFFER[i]=tailByte(i);tailOwned=1;}
API u32 tailIntact(){if(!tailOwned)return 0;for(u32 i=0x10000;i<0x80000;++i)if(DI_READ_BUFFER[i]!=tailByte(i))return 0;return 1;}
API void reopenCache(){CacheInited=0;LastOffset64=~0ull;}
API u32 currentLimit(){return GetDIBufferLimit();}
API void staleWideWrite(){for(u32 i=0;i<0x20000;++i)DI_READ_BUFFER[i]=sample(i);}
API u32 stat(u32 n){switch(n){case 0:return chunks;case 1:return patches;case 2:return syncs;case 3:return acks;case 4:return badOrder;case 5:return badData;case 6:return ioCount;}return 0;}
API u64 ioAt(u32 i){return ioOffset[i];}API u32 ioSize(u32 i){return ioLength[i];}
'''


FENCE_TAIL = r'''
static void drainQueued(){
 if(!queuedBefore)return;
 queuedBefore=0;drainedBeforeLimit=GetDIBufferLimit();currentThread=DI_Thread;
 if(!request(0x400000,0x20021,0))++queueFailures;
 currentThread=1;
}
static int IOS_Ioctl(int,int command,void*in,int inSize,void*out,int outSize){
 ++ioctlCalls;if(ioctlFailure)return ioctlFailure;
 Message message={{(u32)command,out,(u32)outSize,in,(u32)inSize}};
 currentThread=DI_Thread;
 bool handled=DIHandleScratchReservation(&message);
 currentThread=1;
 return handled?fenceResult:-4;
}
API void queueAroundFence(){queuedBefore=queuedAfter=1;}
API u32 drainAfterFence(){
 if(!queuedAfter)return 0;
 queuedAfter=0;drainedAfterLimit=GetDIBufferLimit();currentThread=DI_Thread;
 u32 ok=request(0x500000,0x20021,0);currentThread=1;return ok;
}
API void fenceFault(u32 kind){
 if(kind==1)DI_Handle=-1;
 if(kind==2)currentThread=DI_Thread;
 if(kind==3)ioctlFailure=-4;
 if(kind==4){DI_IRQ=true;delayedIRQ=true;}
 if(kind==5){DI_IRQ=true;delayedIRQ=false;}
}
API int malformedFence(u32 field){
 Message message={{DI_IOCTL_RESERVE_SCRATCH_TAIL,0,0,0,0}};
 if(field==0)message.ioctl.buffer_in=(void*)1;
 if(field==1)message.ioctl.length_in=1;
 if(field==2)message.ioctl.buffer_io=(void*)1;
 if(field==3)message.ioctl.length_io=1;
 DIHandleScratchReservation(&message);return fenceResult;
}
API u32 fenceStat(u32 key){switch(key){
 case 0:return drainedBeforeLimit;case 1:return drainedAfterLimit;case 2:return fenceAcks;
 case 3:return fenceAckLimit;case 4:return ioctlCalls;case 5:return finishPolls;
 case 6:return interruptCalls;case 7:return DI_IRQ;case 8:return queueFailures;}return 0;}
'''


def compile_di(folder):
    source = FIXTURE.replace("static const u32 DI_READ_BUFFER_LENGTH=0x80000;", "static volatile u32 DIReadBufferLimit=0x80000;")
    source = source.replace("static u32 GetDIBufferLimit(){return DI_READ_BUFFER_LENGTH;}",
                            function_source(ROOT / "launcher/kernel/DI.c", "u32 GetDIBufferLimit("))
    source = source.replace("static void f_lseek(FIL*,u32){}", "")
    source = source.replace("static void f_read(FIL*,void*dst,u32 n,UINT*read){++cardReads;memset(dst,0x78,n);*read=n;}", "")
    start = source.index("static void ISOReadDirect(")
    di = (ROOT / "launcher/kernel/DI.c").read_text()
    memory_map = (ROOT / "include/susamune/mem2_map.h").read_text()
    source = source[:start] + re.search(r"#define DI_IOCTL_RESERVE_SCRATCH_TAIL .*", di)[0] + "\n"
    for name in ("NIN_MEM2_DI_SCRATCH_RUNTIME_SIZE", "NIN_MEM2_DI_SCRATCH_SIZE"):
        source += re.search(r"#define " + name + r" .*", memory_map)[0] + "\n"
    source += SUPPORT
    source += function_source(ROOT / "launcher/kernel/ISO.c", "static inline void ISOReadDirect(")
    for path, name in (("GCNCard.c", "static void GCNCard_InitCtx("), ("GCNCard.c", "int GCNCard_Load("),
                       ("ISO.c", "void ISOSetupCache()"), ("ISO.c", "const u8 *ISORead(")):
        part = function_source(ROOT / "launcher/kernel" / path, name)
        if name.startswith("const u8"):
            part = part.replace("const u8 *ISORead(", "const u8 *productionISORead(", 1)
        source += part
    source += "const u8 *ISORead(u32*n,u32 o){++chunks;return productionISORead(n,o);}\n"
    fst = function_source(ROOT / "launcher/kernel/FST.c", "const u8* FSTRead(")
    clip = re.search(r"const u32 limit = GetDIBufferLimit\(\);\s*if \(\*Length > limit\)\s*\*Length = limit;", fst)[0]
    rounded = re.search(r"f_read\( &\(FC\[i\]\.File\), DI_READ_BUFFER, .*?;", fst)[0]
    rounded = rounded.replace("&(FC[i].File)", "&GameFile")
    source += "const u8* FSTRead(const char*,u32*Length,u32 Offset){++chunks;u32 read;" + clip + "f_lseek(&GameFile,Offset);" + rounded + "return DI_READ_BUFFER;}\n"
    real = function_source(ROOT / "launcher/kernel/RealDI.c", "const u8 *ReadRealDisc(")
    real = real.replace("{", "{++chunks;", 1)
    source += real
    body = di[di.index("\t\t\t\tdi_src = 0;"):]
    body = body[:body.index("\n\t\t\t\tbreak;")]
    body = body.replace("sync_after_write( di_dest, di_length );", "finalSync(di_dest, di_length);")
    source += "void runDi(Message*di_msg){" + body + "}\n"
    source += EXPORTS + TAIL
    for name in ("static bool DIHandleScratchReservation(", "bool DIReserveScratchTail(", "void DIFinishAsync("):
        source += function_source(ROOT / "launcher/kernel/DI.c", name)
    entry = function_source(ROOT / "launcher/kernel/DI.c", "u32 DIReadThread(")
    source += entry[:entry.index("\twhile(1)")] + "return DI_Thread;}\n"
    source += "API u32 startDiThread(u32 id){DI_Thread=0;currentThread=id;return DIReadThread(NULL);}\n"
    source += "API void selectThread(u32 id){currentThread=id;}\n"
    source += FENCE_TAIL
    source = source.replace("DI_READ_BUFFER_LENGTH", "DIReadBufferLimit")
    path = folder / "di.cpp"
    path.write_text(source)
    library = path.with_suffix(".dll")
    command = [str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc", "-shared", "-O2",
               "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", str(path), "-o", str(library)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    lib = C.CDLL(str(library))
    lib.ioAt.restype = C.c_uint64
    return lib, command


def traces():
    result = {}
    for name, path in TRACES.items():
        text = path.read_text(errors="replace")
        rows = []
        if name == "pal-boot":
            for offset, destination, length in re.findall(r"DVDRead: offset: ([0-9a-fA-F]+)\s+memOffset: ([0-9a-fA-F]+)\s+length: (\d+)", text):
                rows.append((int(offset, 16), int(length)))
        else:
            for offset, source, dma in re.findall(r"Read: DVDOffset=([0-9a-fA-F]+), DMABuffer = [0-9a-fA-F]+, SrcLength = ([0-9a-fA-F]+), DMALength = ([0-9a-fA-F]+)", text):
                rows.append((int(offset, 16), min(int(source, 16), int(dma, 16))))
        if not rows:
            raise RuntimeError("Empty retained trace: " + name)
        result[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "requests": rows, "request_count": len(rows), "requested_bytes": sum(n for _, n in rows)}
    return result


def fat_counts(lib, requests, mapped=True, fragmented=False):
    extents = [(60000, 2)] if not fragmented else [(1024, 2), (2048, 100000), (4096, 300000), (52832, 500000)]
    flat = [v for row in extents for v in row]
    lib.configure(512, 64, int(mapped), (C.c_uint * len(flat))(*flat), len(extents), 60000 * 32768)
    buffer = C.create_string_buffer(0x900000 + 64)
    pointer = C.addressof(buffer) + 32
    for offset, length in requests:
        if not length:
            continue
        C.memset(C.addressof(buffer), 0xA7, 32)
        C.memset(pointer + length, 0xA7, 32)
        if lib.seek(offset):
            raise RuntimeError("FatFS seek refused")
        actual = C.c_uint()
        if lib.take(pointer, length, C.byref(actual)) or actual.value != length:
            raise RuntimeError("FatFS read refused/short")
        if C.string_at(pointer - 32, 32) != b"\xa7" * 32 or C.string_at(pointer + length, 32) != b"\xa7" * 32:
            raise RuntimeError("FatFS DMA canary changed")
    if lib.stat(3):
        raise RuntimeError("FatFS crossed a fragmented extent")
    return {"device_reads": lib.stat(0), "maximum_device_read": lib.stat(2), "bad_extent_reads": lib.stat(3)}


def execute(lib, size, mode, requests, ciso=0, card=0):
    lib.setSize(size)
    lib.configure(mode, card, ciso)
    return run_requests(lib, requests)


def run_requests(lib, requests, owned_tail=False):
    before = [lib.stat(i) for i in range(7)]
    for offset, length in requests:
        if not lib.request(offset, length, 0) or not lib.allGuards():
            raise RuntimeError(f"DI output/guard failure: {offset=:x} {length=:x}")
    if lib.stat(4) or lib.stat(5) or lib.get(11):
        raise RuntimeError("Full-destination patch/order/buffer contract failed")
    if owned_tail and not lib.tailIntact():
        raise RuntimeError("DI overwrote the owned runtime tail")
    count = lib.stat(6)
    if count >= 100000:
        raise RuntimeError("I/O evidence log full")
    calls = [(lib.ioAt(i), lib.ioSize(i)) for i in range(before[6], count)]
    return {"chunks": lib.stat(0) - before[0], "backend_read_calls": len(calls), "backend_bytes": sum(n for _, n in calls),
            "patch_calls": lib.stat(1) - before[1], "sync_calls": lib.stat(2) - before[2], "ack_calls": lib.stat(3) - before[3],
            "exact_output": True, "canaries": True, "full_destination_patch_before_sync_ack": True}, calls


class ProposedHandoff:
    """Capability gating is modeled; the narrowing calls the production fence."""
    def __init__(self, lib):
        self.lib, self.phase, self.epoch = lib, "boot", 1
        self.parked, self.worker_busy, self.active_read, self.queued_reads = True, False, False, 0
        self.published, self.owner = 0, 0

    def publish(self, exact_game=True, exact_layout=True, injected=True):
        if (self.phase != "boot" or not self.parked or self.worker_busy or self.active_read or
                self.queued_reads or not exact_game or not exact_layout or not injected):
            return False
        if not self.lib.publishRuntime():
            return False
        self.phase, self.published = "runtime", self.epoch
        return True

    def claim(self, epoch):
        if self.phase != "runtime" or epoch != self.published or self.owner:
            return False
        self.lib.claimTail()
        self.owner = epoch
        return True

def phase_experiment(lib, fat, fixtures):
    boot = fixtures["pal-boot"]["requests"]
    runtime = fixtures["pal-lifecycle"]["requests"]
    results = []
    for mode, label in ((1, "iso-cache-3MiB"), (0, "iso-cache-disabled"),
                        (2, "fst-cached-file"), (3, "real-disc-dvdr")):
        control = None
        for small in (False, True):
            lib.setSize(0x80000)
            lib.configure(0 if mode == 1 else mode, 0, 0)
            model = ProposedHandoff(lib)
            rejections = []
            if small:
                for field, value in (("parked", False), ("active_read", True),
                                     ("queued_reads", len(boot)), ("worker_busy", True)):
                    previous = getattr(model, field)
                    setattr(model, field, value)
                    assert not model.publish() and lib.currentLimit() == 0x80000
                    rejections.append(field)
                    setattr(model, field, previous)
                for option in ("exact_game", "exact_layout", "injected"):
                    assert not model.publish(**{option: False}) and lib.currentLimit() == 0x80000
                    rejections.append(option)
            boot_result, boot_calls = run_requests(lib, boot)
            if mode == 1:
                lib.setupRuntimeCache()
            if small:
                assert model.publish() and model.claim(model.epoch)
                model.parked = False
            runtime_result, runtime_calls = run_requests(lib, runtime, owned_tail=small)
            row = {"mode": label, "boot_scratch_bytes": 0x80000,
                   "runtime_scratch_bytes": 0x10000 if small else 0x80000,
                   "boot": boot_result, "runtime": runtime_result}
            if mode != 3:
                for name, calls in (("boot", boot_calls), ("runtime", runtime_calls)):
                    row[name]["fat_contiguous"] = fat_counts(fat, calls, mapped=mode != 2)
                row["combined_fat_contiguous"] = fat_counts(fat, boot_calls + runtime_calls, mapped=mode != 2)
                row["combined_fat_fragmented"] = fat_counts(fat, boot_calls + runtime_calls, mapped=mode != 2, fragmented=True)
            if not small:
                control = row, boot_calls, runtime_calls
                continue
            assert boot_calls == control[1] and boot_result == control[0]["boot"]
            row["baseline_512_512"] = control[0]
            row["boot_traffic_byte_for_byte_identical"] = True
            row["runtime_backend_traffic_identical"] = runtime_calls == control[2]
            row["owned_tail_bytes"] = 0x70000
            row["entire_owned_tail_unchanged_after_runtime"] = bool(lib.tailIntact())
            boundary, _ = run_requests(lib, ((0x800000, 65505), (0x90001F, 65536),
                (0xA001FF, 65537), (0x1400000 - 17, 0x300021)), owned_tail=True)
            row["owned_tail_boundary_checks"] = dict(boundary, cases=4, entire_tail_unchanged=True)
            row["modeled_handoff_rejections"] = rejections
            fence_calls = lib.fenceStat(4)
            assert lib.publishRuntime() and lib.fenceStat(4) == fence_calls
            lib.reopenCache()
            reload_result, reload_calls = run_requests(lib, boot, owned_tail=True)
            assert lib.currentLimit() == 0x10000 and lib.tailIntact()
            if mode != 3:
                reload_result["fat_contiguous"] = fat_counts(fat, reload_calls, mapped=mode != 2)
            row["same_kernel_reinjection_at_64KiB"] = dict(reload_result,
                entire_tail_unchanged=True, repeated_reservation_has_no_new_ioctl=True)
            results.append(row)

    ciso_results = []
    for mode in (0, 1):
        lib.setSize(0x80000)
        lib.configure(0, 0, 1)
        if mode:
            lib.setupRuntimeCache()
        model = ProposedHandoff(lib)
        assert model.publish() and model.claim(model.epoch)
        row, _ = run_requests(lib, ((0x200000 - 17, 0x400031),
            (0x600000 - 31, 0x300001), (0x900001, 65505)), owned_tail=True)
        ciso_results.append(dict(row, cached=bool(mode), cases=3, entire_tail_unchanged=True))

    lib.setSize(0x80000)
    lib.configure(0, 0, 0)
    model = ProposedHandoff(lib)
    assert model.publish() and model.claim(model.epoch)
    # This emulates a backend DMA whose wide length was chosen before publication.
    lib.staleWideWrite()
    assert not lib.tailIntact()
    return {"scope": "Extracted production readers/getter/reservation handler/API execute natively with controlled storage and syscall scheduling. Capability/game/layout gates remain a proposed executable specification; no production capability integration or ARM/PPC cache-coherency proof. The limit never widens during the emulated kernel session; reopened-cache DOL replay remains64KiB.",
            "results": results, "owned_tail_ciso_boundaries": ciso_results,
            "negative_control_stale_wide_write_corrupts_owned_tail": True,
            "real_reinjection_policy": "Current DOL detection and PatchGame run after executable reads. The production API narrows once and never widens: later executable reads stay64KiB, even after ISO cache reopen. A fresh kernel image initializes512KiB again."}


def fence_experiment(lib):
    failures = []
    for kind, label in ((1, "closed_handle"), (2, "called_from_DI_thread"),
                        (3, "ioctl_error"), (4, "delayed_guest_IRQ")):
        lib.setSize(0x80000)
        lib.configure(0, 0, 0)
        lib.fenceFault(kind)
        assert not lib.publishRuntime() and lib.currentLimit() == 0x80000
        if kind == 4:
            assert lib.fenceStat(7) and not lib.fenceStat(4)
            lib.fenceFault(5)
            assert lib.publishRuntime() and not lib.fenceStat(7)
        failures.append(label)
    for field in range(4):
        lib.setSize(0x80000)
        lib.configure(0, 0, 0)
        assert lib.malformedFence(field) == -4 and lib.currentLimit() == 0x80000
    lib.setSize(0x80000)
    lib.configure(0, 0, 0)
    lib.queueAroundFence()
    assert lib.publishRuntime() and lib.fenceStat(0) == 0x80000
    assert lib.fenceStat(2) == 1 and lib.fenceStat(3) == 0x10000 and lib.stat(0) == 1
    lib.claimTail()
    assert lib.drainAfterFence() and lib.fenceStat(1) == 0x10000
    assert lib.stat(0) == 4 and lib.stat(1) == 2 and lib.stat(2) == 2 and lib.stat(3) == 2
    assert not lib.fenceStat(8) and not lib.stat(4) and not lib.stat(5)
    assert lib.tailIntact() and lib.allGuards()
    return {"scope": "Actual production getter, DIHandleScratchReservation, DIReserveScratchTail, DIFinishAsync and DI copy loop. Controlled synchronous-ioctl/thread/IRQ doubles; not a native ARM thread-scheduler or hardware test.",
            "refused_without_narrowing": failures, "malformed_messages_refused": 4,
            "delayed_IRQ_preserved_then_retry_succeeded": True,
            "queued_wide_before_fence": {"scratch_bytes": lib.fenceStat(0), "chunks": 1},
            "limit_visible_before_fence_ack": lib.fenceStat(3),
            "queued_read_after_fence": {"scratch_bytes": lib.fenceStat(1), "chunks": 3},
            "full_patch_sync_ack_per_request": True, "owned_tail_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/timewarp-di-scratch")
    args = parser.parse_args()
    folder = args.out.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()):
        parser.error("Private output must stay inside task build")
    folder.mkdir(parents=True, exist_ok=True)
    timer_before = hashlib.sha256((ROOT / "src/qft_timer.cpp").read_bytes()).hexdigest()
    receipt = {"scope": "Host execution of extracted production ISO cache/direct/CISO reader, RealDI reader, DI copy/patch loop; hardware and patch callbacks are controlled doubles. FST checks execute its actual common cap and cached-file rounded read against one synthetic file: pathname lookup/open cost and real per-file alignment are excluded. Physical FAT counts execute full production ff.c on synthetic mapped extents, not Wii throughput or hardware DMA/cache coherency.",
               "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                           ("launcher/kernel/DI.c", "launcher/kernel/DI.h", "launcher/kernel/ISO.c", "launcher/kernel/FST.c",
                            "launcher/kernel/RealDI.c", "launcher/kernel/Patch.c", "launcher/fatfs/ff.c",
                            "include/susamune/mem2_map.h")}, "trace_results": [], "boundary_results": [], "fault_characterization": []}
    lib = fat = None
    try:
        lib, command = compile_di(folder)
        receipt["compile_command"] = command
        fat = compile_reader(folder)
        fixtures = traces()
        receipt["traces"] = {name: {k: v for k, v in row.items() if k != "requests"} for name, row in fixtures.items()}
        for name, fixture in fixtures.items():
            for mode, label in ((0, "iso-cache-disabled"), (1, "iso-cache-3MiB"), (2, "fst-cached-file"), (3, "real-disc-dvdr")):
                for size in SIZES:
                    result, calls = execute(lib, size, mode, fixture["requests"])
                    result.update(trace=name, mode=label, scratch_bytes=size)
                    if mode != 3:
                        result["fat_contiguous"] = fat_counts(fat, calls, mapped=mode != 2)
                        result["fat_fragmented"] = fat_counts(fat, calls, mapped=mode != 2, fragmented=True)
                    receipt["trace_results"].append(result)
                    print(json.dumps(result), flush=True)
        cases = [(0x400000 + offset, length) for offset in (0, 31, 511, 2047) for length in
                 (0, 1, 31, 32, 33, 65505, 65535, 65536, 65537, 131071, 131072, 131073, 524287, 524288, 524289, 0x300001, 0x700021)]
        cases += [(0x200000 - 17, 0x400031), (0x900020, 4096), (0x90F020, 4096), (0x910000, 32)]
        for mode, label, ciso in ((0, "iso", 0), (0, "ciso-sparse", 1), (1, "iso-cache", 0), (1, "ciso-cache", 1), (2, "fst-cached", 0), (3, "real-dvdr", 0), (4, "real-normal", 0)):
            for size in SIZES:
                selected = [case for case in cases if not case[0] & 3] if mode == 4 else cases
                row, _ = execute(lib, size, mode, selected, ciso)
                row.update(mode=label, scratch_bytes=size, cases=len(selected))
                receipt["boundary_results"].append(row)
        for size in SIZES:
            for mode, label in ((0, "iso"), (2, "fst-cached")):
                for fail, short in ((1, 0), (0, 17)):
                    lib.setSize(size)
                    lib.configure(mode, 0, 0)
                    lib.faults(fail, short)
                    correct = bool(lib.request(0x400000, 65537, 0))
                    if correct or not lib.allGuards() or lib.stat(4):
                        raise RuntimeError("Unexpected short-read/error characterization")
                    receipt["fault_characterization"].append({"scratch_bytes": size, "mode": label,
                        "injected": "first read error" if fail else "short reads of17bytes",
                        "exact_output": correct, "canaries": True, "patch_calls": lib.stat(1),
                        "ack_calls": lib.stat(3), "preexisting_limitation": "The current caller patches/acks despite incomplete backend data; this is also present at512KiB."})
        receipt["production_fence"] = fence_experiment(lib)
        receipt["phase_variant"] = phase_experiment(lib, fat, fixtures)
        patch = (ROOT / "launcher/kernel/Patch.c").read_text()
        table = patch[patch.index("static const DspMatch DspMatches[]"):]
        table = table[:table.index("};")]
        dsp_lengths = [int(value, 16) for value in re.findall(r"\{\s*(0x[0-9a-fA-F]+),", table)]
        if max(dsp_lengths) > min(SIZES):
            raise RuntimeError("DSP scratch exceeds smallest candidate")
        receipt["other_consumers"] = {"dsp_match_lengths": dsp_lengths, "maximum_dsp_bytes": max(dsp_lengths),
            "minimum_candidate_headroom_after_dsp_bytes": min(SIZES) - max(dsp_lengths),
            "usb_keepalive": "DI ioctl2 performs one synchronous device-sector read before returning; FatFS maximum sector size4096 fits every candidate.",
            "low_mem_backup": "DI's physical destination<=0x31A0 backup is not addressable in this host fixture. Its maximum scratch index0x31A0+4 remains below64KiB; production code unchanged."}
        receipt["complete"] = True
    finally:
        receipt["sources_changed_during_run"] = [path for path, value in receipt["sources"].items()
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != value]
        receipt["production_sources_unchanged"] = not receipt["sources_changed_during_run"]
        receipt["timer_source_unchanged"] = hashlib.sha256((ROOT / "src/qft_timer.cpp").read_bytes()).hexdigest() == timer_before
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        for loaded in (lib, fat):
            if loaded:
                C.windll.kernel32.FreeLibrary(C.c_void_p(loaded._handle))


if __name__ == "__main__":
    main()
