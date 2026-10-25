"""Exercise the actual isolated UDP worker against a deferred, in-memory IOS ABI.

No sockets are opened. This checks ownership and framing, not IOS58 connectivity.
"""
import ctypes as C
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PLATFORM = r'''
typedef unsigned char u8;
typedef unsigned int u32;
typedef int s32;
typedef unsigned long long size_t;
#define NULL ((void*)0)
#define ALIGNED(n) __attribute__((aligned(n)))
struct ipcmessage { u32 command,result,words[6]; };
typedef struct { void *data; u32 len; } ioctlv;
void *memcpy(void*d,const void*s,size_t n){u8*a=d;const u8*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int c,size_t n){u8*a=d;while(n--)*a++=(u8)c;return d;}
int memcmp(const void*a,const void*b,size_t n){const u8*x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
static unsigned fCalls,fViolation,fAck;
static int fReject,fOpenFail,fTimerFail,fThreadFail,fContinueFail,fQueueFail,fCancelFail,fDestroyFail;
static int fOpens,fCloses,fTimers,fDestroys,fCancels;
static struct ipcmessage *fMessages[8];
static unsigned fWrite,fRead;
struct FakeRequest { unsigned active,command,in,out,vector,count; struct ipcmessage *message;
 void *buffers[4]; unsigned lengths[4]; u8 copies[4][288]; };
static struct FakeRequest fReq[2];
static void *fCachePointers[12];
static unsigned fCacheLengths[12],fCacheCount;
static u8 fCacheBacking[12][288];
static void checkPinned(void){unsigned n,i;for(n=0;n<2;++n)if(fReq[n].active)
 for(i=0;i<fReq[n].count;i++)if(memcmp(fReq[n].buffers[i],fReq[n].copies[i],fReq[n].lengths[i]))++fViolation;}
static void sync_after_write(void*p,u32 n){unsigned i;
 for(i=0;i<fCacheCount&&fCachePointers[i]!=p;++i){}
 if(i==12||n>288){++fViolation;return;}
 if(i==fCacheCount){fCachePointers[i]=p;++fCacheCount;}
 fCacheLengths[i]=n;memcpy(fCacheBacking[i],p,n);}
static void sync_before_read(void*p,u32 n){unsigned i;
 for(i=0;i<fCacheCount;++i)if(fCachePointers[i]==p&&fCacheLengths[i]==n){memcpy(p,fCacheBacking[i],n);return;}
 ++fViolation;}
static int mqueue_create(void*p,int n){(void)p;return fQueueFail?fQueueFail:(n==8?3:-1);}
static int MoonshineNetDestroyQueue(int q){(void)q;++fDestroys;return fDestroyFail;}
static int mqueue_send_now(int q,struct ipcmessage*m,int flags){(void)q;
 if(flags!=1)++fViolation;if(fWrite-fRead==8)return -8;fMessages[fWrite++&7]=m;return 0;}
static int mqueue_recv(int q,struct ipcmessage**m,int flags){(void)q;(void)flags;
 if(fRead==fWrite)return -1;*m=fMessages[fRead++&7];return 0;}
static int mqueue_ack(struct ipcmessage*m,int r){(void)m;(void)r;++fViolation;++fAck;return -4;}
static int do_thread_create(void*entry,u32*stack,u32 bytes,u32 priority){
 (void)entry;(void)stack;if(bytes!=8192||priority!=0x58)++fViolation;return fThreadFail?fThreadFail:4;}
static int thread_continue(int id){(void)id;return fContinueFail;}
static int thread_cancel(int id,int result){(void)id;(void)result;++fCancels;return fCancelFail;}
static int TimerCreate(int first,int repeat,int q,int message){(void)q;
 if(first!=10000||repeat!=10000||message!=2)++fViolation;++fTimers;return fTimerFail?fTimerFail:5;}
static void TimerDestroy(int id){(void)id;--fTimers;}
static int IOS_Open(const char*p,int mode){(void)p;(void)mode;++fOpens;return fOpenFail?fOpenFail:10+fOpens;}
static void IOS_Close(int fd){(void)fd;if(fReq[0].active||fReq[1].active)++fViolation;++fCloses;}
static int beginAsync(int command,unsigned in,unsigned out,unsigned vec,struct ipcmessage*m){
 struct FakeRequest*r=&fReq[command==12];checkPinned();if(r->active)++fViolation;++fCalls;
 if(fReject){int result=fReject;fReject=0;return result;}
 memset(r,0,sizeof(*r));r->active=1;r->command=command;r->in=in;r->out=out;r->vector=vec;r->message=m;return 0;}
static void remember(struct FakeRequest*r,void*p,unsigned bytes){unsigned i=r->count;if(!bytes)return;
 if(i>=4||bytes>288){++fViolation;return;}r->buffers[i]=p;r->lengths[i]=bytes;memcpy(r->copies[i],p,bytes);++r->count;}
static int IOS_IoctlAsync(int fd,int cmd,void*in,unsigned n,void*out,unsigned z,int q,struct ipcmessage*m){
 int r;(void)fd;(void)q;r=beginAsync(cmd,n,z,0,m);if(!r){remember(&fReq[0],in,n);remember(&fReq[0],out,z);}return r;}
static int IOS_IoctlvAsync(int fd,int cmd,unsigned in,unsigned out,ioctlv*v,int q,struct ipcmessage*m){
 unsigned i;int r;(void)fd;(void)q;r=beginAsync(cmd,in,out,1,m);
 if(!r){remember(&fReq[cmd==12],v,(in+out)*sizeof(*v));for(i=0;i<in+out;i++)remember(&fReq[cmd==12],v[i].data,v[i].len);}return r;}
'''

ADAPTER = r'''
#define API __declspec(dllexport)
static unsigned lane(void){return sOp?0:1;}
API void reset(void){
 sTxWrite=sTxRead=sRxWrite=sRxRead=sRequestEpoch=sStopEpoch=sStatusSequence=0;
 memset(&sConfig,0,sizeof(sConfig));memset(&sStatus,0,sizeof(sStatus));memset(&sPublished,0,sizeof(sPublished));
 memset(sTxPoses,0,sizeof(sTxPoses));memset(sRxPoses,0,sizeof(sRxPoses));
 sTxPoseCursor=sRxPoseCursor=sRxPreferPose=0;
 sTicks=sDue=sSubmitted=sRetries=sTxBudget=sRxBudget=sPreferPose=sRxPending=sRxSubmitted=0;
 sQueue=sTimer=sKd=sTop=sSocket=sThread=-1;sInitialized=sFailed=sOp=sNext=sShuttingDown=0;
 fCalls=fViolation=fAck=fWrite=fRead=fCacheCount=0;memset(fReq,0,sizeof(fReq));
 fReject=fOpenFail=fTimerFail=fThreadFail=fContinueFail=fQueueFail=fCancelFail=fDestroyFail=0;
 fOpens=fCloses=fTimers=fDestroys=fCancels=0;
}
API int init(void){return MoonshineNetInit();}
API int shutdown(void){return MoonshineNetShutdown();}
API int start(unsigned epoch,unsigned port){struct MoonshineNetConfig c;
 memset(&c,0,sizeof(c));c.epoch=epoch;c.localPort[0]=port>>8;c.localPort[1]=port;return MoonshineNetStart(&c);}
API void stop(unsigned epoch){MoonshineNetRequestStop(epoch);}
API int retired(unsigned epoch){return MoonshineNetRetired(epoch);}
API unsigned poll(unsigned field){struct MoonshineNetStatus s;if(!MoonshineNetPoll(&s))return ~0u;
 return field<10?((unsigned*)&s)[field]:field==10?get32(s.local.ip):(s.local.port[0]<<8)|s.local.port[1];}
API void wakes(void){struct ipcmessage*m;unsigned count=0;
 while(fRead!=fWrite&&count++<8){m=fMessages[fRead++&7];event(m);checkPinned();}}
API void ticks(unsigned n){while(n--){event(NET_TIMER);checkPinned();}}
API void finishLane(unsigned n,int result,const u8*payload,unsigned bytes,const u8*sender){
 struct FakeRequest*r=&fReq[n];struct ipcmessage*m=r->message;
 if(!r->active){++fViolation;return;}checkPinned();r->active=0;
 if(!n){
  if(sOp==OP_SOCKET&&result>=0&&get32(sArgs+8)!=0)result=-68;
  if(sOp==OP_KD)put32(sReply,bytes);
  if(sOp==OP_NAME){sReply[0]=8;sReply[1]=2;sReply[2]=bytes>>8;sReply[3]=bytes;}
 }else{if(bytes>sizeof(sRxData)){++fViolation;return;}
  if(payload)memcpy(sRxData,payload,bytes);if(sender)memcpy(sRxAddress,sender,8);}
 m->command=8;m->result=result;event(m);checkPinned();
}
API void finish(int result,const u8*p,unsigned n,const u8*sender){finishLane(lane(),result,p,n,sender);}
API unsigned inspect(unsigned which){struct FakeRequest*r=&fReq[lane()];checkPinned();switch(which){
 case 0:return sOp?sOp:sRxPending?OP_RECV:OP_NONE;case 1:return fCalls;case 2:return fViolation;case 3:return r->command;
 case 4:return r->in;case 5:return r->out;case 6:return r->vector;case 7:return fReq[0].active||fReq[1].active;
 case 8:return sSocket;case 9:return fOpens;case 10:return fCloses;case 11:return fAck;
 case 12:return fTimers;case 13:return fDestroys;case 14:return fCancels;
 case 15:return sTxWrite-sTxRead;case 16:return sRxWrite-sRxRead;case 17:return sRxPending;case 18:return sOp;default:return ~0u;}}
API const void*args(void){return lane()?sRxArgs:sArgs;}
API const void*data(void){return lane()?sRxData:sData;}
API unsigned vectorLen(unsigned i){return i<3?(lane()?sRxVectors[i].len:sVectors[i].len):0;}
API void fault(unsigned which,int value){switch(which){case 0:fReject=value;break;
 case 1:fOpenFail=value;break;case 2:fTimerFail=value;break;case 3:fThreadFail=value;break;
 case 4:fContinueFail=value;break;case 5:fQueueFail=value;break;
 case 6:fCancelFail=value;break;case 7:fDestroyFail=value;break;}}
API int send(unsigned epoch,const u8*endpoint,const void*p,unsigned n,unsigned pose){
 struct MoonshineNetEndpoint e;memcpy(&e,endpoint,sizeof(e));
 return pose?MoonshineNetPublishPose(epoch,&e,p,n):MoonshineNetSendTo(epoch,&e,p,n);}
API int receive(unsigned epoch,void*p){return MoonshineNetReceive(epoch,p);}
'''


class MoonshineNetWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled host compiler required')
        output = ROOT / 'build/timewarp-network-spike-1'
        output.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='host-', dir=output)
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        (path / 'MoonshineNetTestPlatform.h').write_text(PLATFORM)
        (path / 'test.c').write_text('#define MOONSHINE_NET_HOST_TEST\n#include "MoonshineNet.c"\n' + ADAPTER)
        result = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared', '-O2',
            '-fno-builtin', '-nostdlib', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(path), '-I', str(ROOT / 'include'), '-I', str(ROOT / 'launcher/kernel'), str(path / 'test.c'),
            '-o', str(path / 'test.dll')], text=True, capture_output=True,
            env={**os.environ, 'TEMP': str(path), 'TMP': str(path)})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.poll.restype = cls.lib.inspect.restype = C.c_uint
        cls.lib.args.restype = cls.lib.data.restype = C.c_void_p
        cls.lib.finish.argtypes = [C.c_int, C.c_char_p, C.c_uint, C.c_char_p]
        cls.lib.finishLane.argtypes = [C.c_uint, C.c_int, C.c_char_p, C.c_uint, C.c_char_p]
        cls.lib.send.argtypes = [C.c_uint, C.c_char_p, C.c_char_p, C.c_uint, C.c_uint]
        cls.lib.receive.argtypes = [C.c_uint, C.c_void_p]

    def setUp(self):
        self.lib.reset()

    def tearDown(self):
        self.assertEqual(self.lib.inspect(2), 0, 'IOS-owned memory changed before its completion')

    def finish(self, result=0, payload=None, count=0, sender=None):
        self.lib.finish(result, payload, count, sender)

    def start(self, epoch=17, port=36471):
        self.assertEqual(self.lib.init(), 1)
        calls = self.lib.inspect(1)
        self.assertEqual(self.lib.start(epoch, port), 1)
        self.assertEqual(self.lib.inspect(1), calls)  # Start only publishes work.
        self.lib.wakes()
        self.assertEqual(self.lib.inspect(0), 1)

    def ready(self, epoch=17):
        self.start(epoch)
        self.finish(count=C.c_uint(-15).value)  # Already started is allowed.
        self.assertEqual(self.lib.inspect(0), 2)
        self.finish()
        self.assertEqual(self.lib.inspect(0), 3)
        self.finish(C.c_int(0xc0a80109).value)
        self.assertEqual(C.string_at(self.lib.args(), 12), bytes.fromhex('000000020000000200000000'))
        self.finish(19)
        self.assertEqual(C.string_at(self.lib.args(), 12), bytes.fromhex('000000130000000400000004'))
        self.finish()
        for option in (0x1002, 0x1001):
            expected = b''.join(x.to_bytes(4, 'big') for x in (19, 0xffff, option, 4, 4096))
            self.assertEqual(C.string_at(self.lib.args(), 20), expected)
            self.finish()
        self.assertEqual(C.string_at(self.lib.args(), 16), bytes.fromhex('000000130000000108028e7700000000'))
        self.finish()
        self.assertEqual(self.lib.inspect(0), 9)
        self.finish(count=36471)
        self.assertEqual(self.lib.poll(2), 2)
        self.assertEqual(self.lib.poll(10), 0xc0a80109)
        self.assertEqual(self.lib.poll(11), 36471)

    @staticmethod
    def endpoint(port=1234):
        return bytes((192, 168, 1, 20)) + port.to_bytes(2, 'big') + b'\0\0'

    def send(self, data, *, pose=0, epoch=17):
        return self.lib.send(epoch, self.endpoint(), data, len(data), pose)

    @staticmethod
    def movement(sequence):
        import struct
        return struct.pack('>IHBBHHIIII4B', 0x4d535231, 7, 3, 0, 48, 0,
                           sequence, 1, 2, 0, 0, 1, 1, 0) + bytes(48)

    def test_stalled_consumer_gets_latest_of_each_peer_and_preserves_controls(self):
        self.ready()
        sender = bytes.fromhex('080204d2c0a80114')
        for n in range(4):
            self.lib.ticks(1)
            self.lib.finishLane(1, 1, bytes([n]), 1, sender)
        for sequence in range(1, 101):
            for peer in range(3):
                self.lib.ticks(1)
                address = b'\x08\x02' + (1234 + peer).to_bytes(2, 'big') + bytes((192, 168, 1, 20))
                pose = self.movement(sequence)
                self.lib.finishLane(1, len(pose), pose, len(pose), address)
        packet = C.create_string_buffer(272)
        controls, latest = [], {}
        while self.lib.receive(17, packet):
            size = int.from_bytes(packet.raw[12:16], 'little')
            if size == 1:
                controls.append(packet.raw[16])
            else:
                latest[int.from_bytes(packet.raw[4:6], 'big')] = int.from_bytes(packet.raw[28:32], 'big')
        self.assertEqual(controls, list(range(4)))
        self.assertEqual(latest, {1234: 100, 1235: 100, 1236: 100})
        self.assertEqual(self.lib.poll(7), 0)
        self.assertEqual(self.lib.inspect(2), 0)

    def test_three_transmit_recipients_each_keep_their_newest_pose(self):
        self.ready()
        for sequence in range(1, 41):
            for peer in range(3):
                pose = self.movement(sequence)
                self.assertEqual(self.lib.send(17, self.endpoint(1234 + peer), pose, len(pose), 1), 1)
        sent = {}
        for _ in range(3):
            self.lib.ticks(1)
            self.assertEqual(self.lib.inspect(18), 10)
            port = int.from_bytes(C.string_at(self.lib.args(), 20)[14:16], 'big')
            sent[port] = int.from_bytes(C.string_at(self.lib.data(), 80)[12:16], 'big')
            self.lib.finishLane(0, 80, None, 0, None)
        self.assertEqual(sent, {1234: 40, 1235: 40, 1236: 40})
        self.assertEqual(self.lib.inspect(2), 0)

    def test_same_bound_socket_udp_abi_and_latest_pose(self):
        self.ready()
        self.assertEqual((self.lib.inspect(3), self.lib.inspect(4), self.lib.inspect(5)), (12, 1, 2))
        self.assertEqual(self.lib.vectorLen(1), 257)
        self.assertEqual(C.string_at(self.lib.args(), 8), bytes.fromhex('0000001300000004'))
        self.assertEqual(self.send(b'control'), 1)
        self.assertEqual(self.send(b'old-pose', pose=1), 1)
        self.assertEqual(self.send(b'new-pose', pose=1), 1)
        self.finish(-6)
        self.assertEqual((self.lib.inspect(3), self.lib.inspect(4), self.lib.inspect(5)), (13, 2, 0))
        self.assertEqual(C.string_at(self.lib.data(), 7), b'control')
        self.assertEqual(C.string_at(self.lib.args(), 20), bytes.fromhex('000000130000000000000001080204d2c0a80114'))
        self.finish(7)
        self.lib.ticks(1)
        self.assertEqual(self.lib.inspect(17), 1)
        self.lib.finishLane(1, -6, None, 0, None)
        self.assertEqual(C.string_at(self.lib.data(), 8), b'new-pose')
        self.finish(8)
        self.assertEqual(self.lib.poll(5), 2)
        self.assertEqual(self.lib.inspect(9), 2)  # Driver opens, never another UDP socket.

    def test_udp_send_flags_zero_preserves_nonblocking_and_queue_progress(self):
        self.ready()  # Verifies F_SETFL still installs nonblocking flag 4.
        self.assertEqual(self.send(b'blocked'), 1)
        self.assertEqual(self.send(b'next'), 1)
        self.finish(-6)  # Empty nonblocking receive permits the first send.
        self.assertEqual(self.lib.inspect(0), 10)
        self.assertEqual(C.string_at(self.lib.args(), 12), bytes.fromhex('000000130000000000000001'))
        self.finish(-6)  # IOS would-block must release the request buffers.
        self.assertEqual(self.lib.poll(2), 2)
        self.assertEqual(self.lib.poll(8), 1)
        self.assertEqual(C.c_int(self.lib.poll(3)).value, -6)
        self.assertEqual(self.lib.inspect(15), 1)
        self.lib.ticks(1)
        self.assertEqual(self.lib.inspect(17), 1)
        self.lib.finishLane(1, -6, None, 0, None)
        self.assertEqual(self.lib.inspect(0), 10)
        self.assertEqual(C.string_at(self.lib.data(), 4), b'next')
        self.assertEqual(C.string_at(self.lib.args(), 12), bytes.fromhex('000000130000000000000001'))
        self.finish(4)
        self.assertEqual(self.lib.poll(5), 1)
        self.assertEqual(self.lib.inspect(15), 0)

    def test_bounded_queues_payloads_and_untrusted_receive(self):
        self.ready()
        self.assertEqual(self.send(b'x' * 257), 0)
        self.assertEqual(self.send(b'wrong', epoch=18), 0)
        for _ in range(4):
            self.assertEqual(self.send(b'x' * 256), 1)
        self.assertEqual(self.send(b'full'), 0)
        self.assertEqual(self.lib.inspect(15), 4)
        sender = bytes.fromhex('080204d2c0a80114')
        self.finish(257, b'x' * 257, 257, sender)
        self.assertEqual(self.lib.poll(7), 1)
        self.finish(256)  # Queued TX gets its one attempt this tick.
        for n in range(4):
            self.lib.ticks(1)
            self.lib.finishLane(1, 4, bytes((n,)) * 4, 4, sender)
            if self.lib.inspect(0) == 10:
                self.finish(256)
        self.assertEqual(self.lib.inspect(16), 4)
        self.assertEqual(self.lib.poll(7), 1)
        packet = C.create_string_buffer(272)
        for n in range(4):
            self.assertEqual(self.lib.receive(17, packet), 1)
            self.assertEqual(packet.raw[:8], self.endpoint())
            self.assertEqual(int.from_bytes(packet.raw[8:12], 'little'), 17)
            self.assertEqual(packet.raw[16:20], bytes((n,)) * 4)
        self.assertEqual(self.lib.receive(17, packet), 0)

    def test_full_control_ring_does_not_block_socket_draining(self):
        self.ready()
        self.finish(-6)
        self.lib.ticks(1)
        sender = bytes.fromhex('080204d2c0a80114')
        packet = C.create_string_buffer(272)
        for n in range(4):
            self.lib.finishLane(1, 4, bytes((n,)) * 4, 4, sender)
        self.assertEqual(self.lib.inspect(0), 11)
        self.lib.ticks(20)
        self.assertEqual(self.lib.inspect(0), 11)
        self.assertEqual(self.send(b'heartbeat'), 1)
        self.lib.wakes()
        self.assertEqual(self.lib.inspect(0), 10)
        self.finish(9)
        received = []
        for n in range(4, 8):
            self.assertEqual(self.lib.receive(17, packet), 1)
            received.append(packet.raw[16])
            self.lib.wakes()
            self.assertEqual(self.lib.inspect(0), 11)
            self.lib.finishLane(1, 4, bytes((n,)) * 4, 4, sender)
        while self.lib.receive(17, packet):
            received.append(packet.raw[16])
        self.assertEqual(received, list(range(8)))
        self.assertEqual(self.lib.poll(7), 0)

    def test_receive_bursts_drain_without_waiting_a_tick_per_datagram(self):
        self.ready()
        self.finish(-6)
        self.lib.ticks(1)
        sender = bytes.fromhex('080204d2c0a80114')
        packet = C.create_string_buffer(272)
        for n in range(8):
            self.assertEqual(self.lib.inspect(0), 11)
            if n == 2:
                self.assertEqual(self.send(b'ctrl'), 1)
                self.lib.wakes()
            self.lib.finishLane(1, 4, bytes((n,)) * 4, 4, sender)
            self.assertEqual(self.lib.receive(17, packet), 1)
            self.assertEqual(packet.raw[16:20], bytes((n,)) * 4)
            if n == 2:
                self.assertEqual(self.lib.inspect(0), 10)
                self.assertEqual(C.string_at(self.lib.data(), 4), b'ctrl')
                self.finish(4)
        self.assertEqual(self.lib.inspect(0), 0)
        before = self.lib.inspect(1)
        self.lib.wakes()
        self.assertEqual(self.lib.inspect(1), before)
        self.lib.ticks(1)
        self.assertEqual(self.lib.inspect(0), 11)
        self.finish(-6)
        self.assertEqual(self.lib.inspect(0), 0)

    def test_send_and_receive_complete_independently_and_stop_waits_for_both(self):
        for first in (0, 1):
            with self.subTest(first_completion=first):
                self.lib.reset()
                self.ready()
                self.assertEqual(self.send(b'hello'), 1)
                self.lib.wakes()
                self.assertEqual((self.lib.inspect(18), self.lib.inspect(17)), (10, 1))
                self.lib.stop(17)
                self.lib.wakes()
                self.lib.finishLane(first, -6, None, 0, None)
                self.assertEqual(self.lib.retired(17), 0)
                self.assertNotEqual(self.lib.inspect(18), 12)
                self.lib.finishLane(1 - first, -6, None, 0, None)
                self.assertEqual(self.lib.inspect(18), 12)
                self.finish()
                self.assertEqual(self.lib.retired(17), 1)

    def test_four_player_load_with_ten_ms_ios_completions(self):
        from collections import deque
        self.ready()
        queued = deque()
        submitted = [None, 0]
        delivered = [0, 0, 0]
        packet = C.create_string_buffer(272)
        max_age = 0
        for ms in range(6000):
            if ms % 33 == 0:
                for peer in range(3):
                    queued.append((ms, peer))
            if ms % 17 == 0:
                self.assertEqual(self.send(b'bundle'), 1)
                self.lib.wakes()
            if ms % 10 == 0:
                self.lib.ticks(1)
            for lane in (0, 1):
                pending = self.lib.inspect(18 if lane == 0 else 17)
                if pending and submitted[lane] is None:
                    submitted[lane] = ms
                if pending and ms - submitted[lane] >= 10:
                    if lane == 0:
                        self.lib.finishLane(0, 6, None, 0, None)
                    elif queued:
                        stamp, peer = queued.popleft()
                        max_age = max(max_age, ms - stamp)
                        sender = bytes((8, 2, 4, 210, 192, 168, 1, 20 + peer))
                        self.lib.finishLane(1, 4, bytes((peer,)) * 4, 4, sender)
                    else:
                        self.lib.finishLane(1, -6, None, 0, None)
                    submitted[lane] = ms if self.lib.inspect(18 if lane == 0 else 17) else None
            while self.lib.receive(17, packet):
                delivered[packet.raw[16]] += 1
            self.lib.wakes()
        self.assertLess(max_age, 80)
        self.assertLessEqual(len(queued), 3)
        self.assertTrue(all(n >= 179 for n in delivered), delivered)
        self.assertGreaterEqual(self.lib.poll(5), 350)
        self.assertEqual(self.lib.poll(7), 0)

    def test_network_completions_preempt_main_but_not_disc_streaming(self):
        import re
        source = (ROOT / 'launcher/kernel/MoonshineNet.c').read_text()
        main = (ROOT / 'launcher/kernel/main.c').read_text()
        priority = int(re.search(r'#define NET_WORKER_PRIORITY (0x[0-9A-Fa-f]+)', source)[1], 16)
        main_priority = int(re.search(r'thread_set_priority\(\s*0,\s*(0x[0-9A-Fa-f]+)', main)[1], 16)
        self.assertGreater(priority, main_priority)
        self.assertLess(priority, 0x78)

    def test_timeout_keeps_ios_buffers_until_late_completion_and_close(self):
        self.ready()
        self.assertEqual(self.send(b'waiting'), 1)
        before = self.lib.inspect(1)
        self.lib.stop(17)
        self.lib.wakes()
        self.lib.ticks(1200)
        self.assertEqual(self.lib.inspect(1), before)
        self.assertEqual(self.lib.poll(2), 3)
        self.assertEqual(self.lib.retired(17), 0)
        self.assertEqual(self.lib.start(18, 36471), 0)
        self.assertEqual(self.send(b'late'), 0)
        self.finish(-6)
        self.assertEqual(self.lib.inspect(0), 12)
        self.assertEqual(self.lib.retired(17), 0)
        self.finish(-6)  # A failed close also retains the socket.
        self.lib.ticks(9)
        self.assertEqual(self.lib.inspect(0), 0)
        self.lib.ticks(1)
        self.assertEqual(self.lib.inspect(0), 12)
        self.finish()
        self.assertEqual(self.lib.retired(17), 1)
        self.assertEqual(self.lib.poll(2), 4)
        self.assertEqual(self.lib.inspect(10), 2)
        self.assertEqual(self.lib.inspect(12), 0)
        self.assertEqual(self.lib.start(18, 36471), 1)
        self.lib.stop(17)  # Stale stop cannot cancel the new session.
        self.lib.wakes()
        self.assertEqual(self.lib.poll(2), 1)
        self.assertEqual(self.lib.inspect(0), 1)

    def test_stop_accounts_for_socket_creation_and_early_cancellation(self):
        self.start()
        self.lib.stop(17)
        self.lib.wakes()
        self.finish()
        self.assertEqual(self.lib.retired(17), 1)
        self.assertEqual(self.lib.inspect(9), 1)
        self.assertEqual(self.lib.start(18, 36471), 1)
        self.lib.wakes()
        self.finish()
        self.finish()
        self.finish(0x0a000001)
        self.assertEqual(self.lib.inspect(0), 4)
        self.lib.stop(18)
        self.lib.wakes()
        self.finish(22)
        self.assertEqual(self.lib.inspect(8), 22)
        self.assertEqual(self.lib.inspect(0), 12)
        self.finish()
        self.assertEqual(self.lib.retired(18), 1)
        self.assertEqual(self.lib.start(19, 36471), 1)
        opens = self.lib.inspect(9)
        self.lib.stop(19)
        self.lib.wakes()
        self.assertEqual(self.lib.retired(19), 1)
        self.assertEqual(self.lib.inspect(9), opens)

    def test_startup_failures_and_timer_retries_are_terminal_or_bounded(self):
        self.start()
        self.finish(count=C.c_uint(-29).value)
        calls = self.lib.inspect(1)
        self.lib.ticks(9)
        self.assertEqual(self.lib.inspect(1), calls)
        self.lib.ticks(1)
        self.assertEqual(self.lib.inspect(0), 1)
        self.finish()
        self.finish()
        self.finish(4)  # Invalid host id cannot masquerade as ready.
        self.assertEqual(self.lib.retired(17), 1)
        self.assertEqual(self.lib.poll(2), 4)
        self.assertEqual(self.lib.start(18, 36471), 1)
        self.lib.fault(0, -22)
        self.lib.wakes()
        self.assertEqual(self.lib.inspect(7), 0)
        self.lib.ticks(10)
        self.assertEqual(self.lib.retired(18), 1)

    def test_init_failure_does_not_release_or_wait_on_an_unstarted_worker(self):
        self.lib.fault(4, -1)
        self.assertEqual(self.lib.init(), 0)
        self.assertEqual(self.lib.inspect(13), 1)
        self.assertEqual(self.lib.inspect(14), 1)
        self.assertEqual(self.lib.start(17, 36471), 0)
        self.lib.fault(4, 0)
        self.assertEqual(self.lib.init(), 1)
        self.assertEqual(self.lib.init(), 1)

    def test_failure_origin_survives_cleanup_and_retry(self):
        self.start()
        self.finish()
        self.finish()
        self.finish(0x0a000001)
        self.finish(19)
        self.assertEqual(self.lib.inspect(0), 5)
        self.finish(-8)  # Socket-layer NONBLOCK completion, not IPC submission.
        self.assertEqual(C.c_int(self.lib.poll(3)).value, -237008)
        self.assertEqual(self.lib.inspect(0), 12)
        self.finish(-22)
        self.assertEqual(C.c_int(self.lib.poll(3)).value, -237008)
        self.lib.ticks(10)
        self.finish()
        self.assertEqual(self.lib.retired(17), 1)
        self.assertEqual(self.lib.start(18, 36471), 1)
        self.lib.fault(0, -8)  # IPC submission failed before KD owned the request.
        self.lib.wakes()
        self.assertEqual(C.c_int(self.lib.poll(3)).value, -217008)
        self.lib.ticks(10)
        self.assertEqual(self.lib.retired(18), 1)

    def test_socket_rejection_retires_without_a_descriptor_and_allows_retry(self):
        self.start()
        self.finish()
        self.finish()
        self.finish(0x0a000001)
        self.finish(-68)  # Prototype 2 hardware report: unsupported protocol.
        self.assertEqual(C.c_int(self.lib.poll(3)).value, -236068)
        self.assertEqual(self.lib.inspect(8), 0xffffffff)
        self.assertEqual(self.lib.retired(17), 1)
        self.ready(epoch=18)
        self.assertEqual(C.c_int(self.lib.poll(3)).value, 0)

    def test_kernel_shutdown_keeps_pending_worker_and_retries_teardown_failures(self):
        self.ready()
        self.assertEqual(self.lib.shutdown(), 0)
        self.assertEqual(self.lib.inspect(13), 0)
        self.assertEqual(self.lib.inspect(14), 0)
        self.lib.wakes()
        self.lib.ticks(10)
        self.assertEqual(self.lib.shutdown(), 0)
        self.finish(-6)
        self.assertEqual(self.lib.inspect(0), 12)
        self.assertEqual(self.lib.shutdown(), 0)
        self.finish()
        self.lib.fault(6, -6)
        self.assertEqual(self.lib.shutdown(), 0)
        self.assertEqual(self.lib.inspect(13), 0)
        self.assertEqual(self.lib.init(), 0)
        self.assertEqual(self.lib.start(18, 36471), 0)
        self.lib.fault(6, 0)
        self.lib.fault(7, -8)
        self.assertEqual(self.lib.shutdown(), 0)
        cancelled = self.lib.inspect(14)
        self.lib.fault(7, 0)
        self.assertEqual(self.lib.shutdown(), 1)
        self.assertEqual(self.lib.shutdown(), 1)
        self.assertEqual(self.lib.inspect(14), cancelled)
        self.assertEqual(self.lib.inspect(11), 0)  # Callback is already a reply.
        self.assertEqual(self.lib.init(), 1)
        self.assertEqual(self.lib.poll(0), 0)
        self.assertEqual(self.lib.start(17, 36471), 1)
        self.lib.wakes()
        self.assertEqual(self.lib.inspect(0), 1)


if __name__ == '__main__':
    unittest.main()
