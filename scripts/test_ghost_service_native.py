"""Check the production Wii adapter against deferred IOS completions, without sockets."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/ghost-service-native-tests'
CC = Path('C:/msys64/mingw64/bin/gcc.exe')

PLATFORM = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef unsigned char u8;
typedef unsigned int u32;
typedef int s32;
#define ALIGNED(n) __attribute__((aligned(n)))
#define HW_TIMER 0
struct ipcmessage { u32 command, result, words[6]; };
typedef struct { void *data; u32 len; } ioctlv;
u32 read32(unsigned);
void udelay(unsigned);
void sync_after_write(void *, unsigned);
int mqueue_create(void *, int);
int mqueue_recv(int, struct ipcmessage **, int);
int mqueue_send_now(int, struct ipcmessage *, int);
int GhostServiceDestroyQueue(int);
int do_thread_create(void *, u32 *, unsigned, unsigned);
int thread_continue(int);
int thread_cancel(int, int);
int IOS_Open(const char *, int);
int IOS_Close(int);
int IOS_Ioctl(int,int,void *,int,void *,int);
int IOS_IoctlAsync(int, unsigned, void *, unsigned, void *, unsigned, int, struct ipcmessage *);
int IOS_IoctlvAsync(int, unsigned, unsigned, unsigned, ioctlv *, int, struct ipcmessage *);
'''

ADAPTER = r'''
#define API __declspec(dllexport)
static unsigned char stage[0x30000] ALIGNED(32);
static unsigned char session[GHOST_SERVICE_SESSION_SIZE] ALIGNED(32);
static unsigned violations, calls, tick, command, inputBytes, outputBytes, vector;
static unsigned opened, closed, cancelCommand, malformedDns, unrelated;
static int socketResult, sendResult, recvResult, randomResult, rejectCommand;
static unsigned kdWait, ipWait, tlsCalls, reusedCalls, failReused, failFresh, partialResponse, randomCalls;
static int tlsFailure;
static struct ipcmessage *queued;
static struct ipcmessage *pending;
static unsigned char argsCopy[64], dataCopy[2048];
static unsigned copyBytes;

u32 read32(unsigned unused) { (void)unused; return tick; }
void udelay(unsigned micros) { tick += micros * 2; }
void sync_after_write(void *p, unsigned n) { (void)p; (void)n; }
int mqueue_create(void *p, int n) { (void)p; if (n != 8) ++violations; return 1; }
int GhostServiceDestroyQueue(int q) { (void)q; return 0; }
int do_thread_create(void *f, u32 *stack, unsigned bytes, unsigned priority) {
    (void)f; (void)stack; if (bytes != 8192 || priority != 0x48) ++violations; return 2;
}
int thread_continue(int id) { (void)id; return 0; }
int thread_cancel(int id, int code) { (void)id; (void)code; if (pending) ++violations; return 0; }
int mqueue_send_now(int q, struct ipcmessage *m, int flags) {
    (void)q; if ((m != WEB_JOB && m != WEB_CLOSE && m != WEB_RETIRE) || flags != 1) ++violations;
    queued=m;return 0;
}
int IOS_Open(const char *path, int mode) {
    if (mode || (strcmp(path, "/dev/net/kd/request") && strcmp(path, "/dev/net/ip/top"))) ++violations;
    return 10 + ++opened;
}
int IOS_Close(int fd) { (void)fd; if (pending) ++violations; ++closed; return 0; }
int IOS_Ioctl(int fd,int cmd,void *in,int n,void *out,int cap) {
 (void)fd;(void)out;if(pending || cmd!=3 || n!=4 || cap || word(in)!=7)++violations;return 0;
}
int GhostServiceRandom(void *data, u32 n) { ++randomCalls;memset(data, 0x73, n); return randomResult; }

static int submit(unsigned cmd, unsigned in, unsigned out, unsigned vec, struct ipcmessage *m) {
    if (pending) ++violations;
    ++calls; command = cmd; inputBytes = in; outputBytes = out; vector = vec;
    if ((int)cmd == rejectCommand) return -9;
    pending = m;
    memcpy(argsCopy, sWork->args, sizeof(argsCopy));
    copyBytes = vec && cmd == 13 ? sWork->vectors[0].len : 0;
    if (copyBytes > sizeof(dataCopy)) { ++violations; copyBytes = 0; }
    memcpy(dataCopy, sWork->data, copyBytes);
    return 0;
}
int IOS_IoctlAsync(int fd, unsigned cmd, void *in, unsigned n, void *out, unsigned cap,
                  int q, struct ipcmessage *m) {
    (void)fd; (void)q;
    if ((n && in != sWork->args) || (cap && out != sWork->reply)) ++violations;
    return submit(cmd, n, cap, 0, m);
}
int IOS_IoctlvAsync(int fd, unsigned cmd, unsigned in, unsigned out, ioctlv *v,
                   int q, struct ipcmessage *m) {
    (void)fd; (void)q;
    if (v != sWork->vectors) ++violations;
    return submit(cmd, in, out, 1, m);
}
int mqueue_recv(int q, struct ipcmessage **out, int flags) {
    static struct ipcmessage noise;
    int result = 0;
    (void)q; (void)flags;
    if (!pending) return -1;
    if (unrelated) { --unrelated; *out = &noise; return 0; }
    if (cancelCommand == command) {
        struct WebWork *original = sWork;
        GhostServiceCancel(); GhostServiceRelease();
        if (sWork != original || !sBusy || GhostServiceShutdown()) ++violations;
    }
    if (memcmp(argsCopy, sWork->args, sizeof(argsCopy)) || memcmp(dataCopy, sWork->data, copyBytes)) ++violations;
    if (!vector) switch (command) {
    case 6:
        if (inputBytes || outputBytes != 32) ++violations;
        put(sWork->reply, kdWait ? (--kdWait,-29) : 0); break;
    case 31: if (inputBytes || outputBytes) ++violations; break;
    case 16: if(inputBytes || outputBytes)++violations;result=ipWait?(--ipWait,0):(int)0xc0a80228u;break;
    case 17:
        if (inputBytes != sizeof(GHOST_SERVICE_HOST) || outputBytes != 0x460 ||
            strcmp((char *)sWork->args, GHOST_SERVICE_HOST)) ++violations;
        memset(sWork->reply, 0, sizeof(sWork->reply));
        put(sWork->reply, 0x20000010); put(sWork->reply + 12, 0x20000040);
        sWork->reply[9] = 2; sWork->reply[11] = 4;
        put(sWork->reply + 0x40, 0x20000050);
        memcpy(sWork->reply + 0x50, "\x01\x02\x03\x04", 4);
        if (malformedDns == 1) put(sWork->reply + 12, 0x20000460);
        if (malformedDns == 2) put(sWork->reply + 0x40, 0x20000460);
        if (malformedDns == 3) sWork->reply[9] = 1;
        if (malformedDns == 4) sWork->reply[11] = 16;
        break;
    case 15:
        if (inputBytes != 12 || word(sWork->args) != 2 || word(sWork->args + 4) != 1 || word(sWork->args + 8)) ++violations;
        result = socketResult; break;
    case 4:
        if (inputBytes != 16 || word(sWork->args) != 7 || word(sWork->args + 4) != 1 ||
            memcmp(sWork->args + 8, "\x08\x02\x01\xbb\x01\x02\x03\x04", 8)) ++violations;
        break;
    case 5:
        if (inputBytes != 12 || word(sWork->args) != 7 || word(sWork->args + 4) != 4 || word(sWork->args + 8) != 4) ++violations;
        break;
    case 3: if (inputBytes != 4 || word(sWork->args) != 7) ++violations; break;
    default: ++violations;
    } else if (command == 13) {
        if (inputBytes != 2 || outputBytes || sWork->vectors[1].len != 40 ||
            sWork->vectors[1].data != sWork->args || word(sWork->args) != 7 || word(sWork->args + 4)) ++violations;
        result = sendResult;
    } else if (command == 12) {
        if (inputBytes != 1 || outputBytes != 1 || sWork->vectors[0].len != 8 ||
            sWork->vectors[0].data != sWork->args || word(sWork->args) != 7 || word(sWork->args + 4) != 4) ++violations;
        result = recvResult;
        if (result > 0 && (unsigned)result <= sizeof(sWork->data)) memset(sWork->data, 'R', result);
    } else ++violations;
    *out = pending; pending = NULL; (*out)->result = result; return 0;
}

/* Crypto and parsing have separate production tests; this fixture isolates IOS ownership. */
void br_sha256_init(br_sha256_context *p) { (void)p; }
void br_sha224_update(br_sha224_context *p, const void *data, size_t n) { (void)p; (void)data; (void)n; }
void br_sha256_out(const br_sha256_context *p, void *out) { (void)p; memset(out, 0, 32); }
int GhostTlsGet(struct GhostTls *t, const struct GhostTlsIo *io, const char *path,
    void *out, unsigned cap, unsigned *used, unsigned now, const unsigned char entropy[32]) {
    (void)io; (void)path; (void)out; (void)cap; (void)now; (void)entropy;
    ++tlsCalls;if(t->active){++reusedCalls;if(failReused){--failReused;t->active=0;return -20;}}
    else if(failFresh){--failFresh;t->http.responseBytes=partialResponse;t->client.eng.err=tlsFailure?62:0;
        return tlsFailure?tlsFailure:-20;}
    t->active=1;*used=0;return 0;
}
unsigned br_ssl_engine_current_state(const br_ssl_engine_context *p){(void)p;return BR_SSL_SENDAPP;}
int GhostTlsRequest(struct GhostTls *t,const struct GhostTlsIo *io,const char *path,
 const struct GhostTlsRequest *req,void *out,unsigned cap,unsigned *used,unsigned now,const unsigned char entropy[32]) {
 (void)req;return GhostTlsGet(t,io,path,out,cap,used,now,entropy);
}
int GhostAccountRun(struct GhostAccount *a,struct GhostAccountWork *w,unsigned op,unsigned now,
 const void *ghost,unsigned bytes,GhostAccountHttp http){(void)a;(void)w;(void)op;(void)now;(void)ghost;(void)bytes;(void)http;return 0;}
void GhostAccountInfo(const struct GhostAccount *a,unsigned now,struct GhostServiceAccountInfo *out){(void)a;(void)now;memset(out,0,sizeof(*out));}
unsigned GhostHttpRetryDelay(const struct GhostHttp *h,unsigned now){(void)now;return h->retryAfter;}
int GhostServiceRouteSortSupported(struct GhostJson *j,const void *p,unsigned n){(void)j;(void)p;(void)n;return 1;}
int GhostServiceParsePage(struct GhostJson *j, const void *body, unsigned n, struct GhostServicePage *page) {
    (void)j; (void)body; (void)n; memset(page, 0, sizeof(*page)); page->magic = GHOST_SERVICE_PAGE_MAGIC; return 1;
}
int GhostServiceEntryValid(const struct GhostServiceEntry *entry) { return entry->bytes != 0; }

API void reset(void) {
    memset(stage, 0, sizeof(stage)); pending = NULL;
    memset(session,0,sizeof(session));sTls=NULL;sClosing=sCapabilities=sCapabilitiesKnown=sBackoffUntil=0;
    kdWait=ipWait=tlsCalls=reusedCalls=failReused=0;
    failFresh=partialResponse=randomCalls=0;tlsFailure=0;queued=NULL;
    sBusy = sDone = sInitialized = sCancel = 0; sThread = sQueue = sTop = sSocket = -1;
    sWrite = sRead = sBytes = 0; sWork = NULL;
    violations = calls = tick = opened = closed = cancelCommand = malformedDns = unrelated = 0;
    socketResult = 7; sendResult = recvResult = 2; randomResult = 0; rejectCommand = -1;
}
API int begin(const char *cursor, const char *region) {
    memset(stage, 0, sizeof(struct GhostServiceQuery));
    if (strlen(cursor) >= GHOST_SERVICE_CURSOR_SIZE) return 0;
    strcpy((char *)stage, cursor);
    return GhostServiceStart(stage, sizeof(stage), region, 1792900000u, NULL, session);
}
API void job(void) { performJob(); }
API int connectOnly(void) { return connectHost(); }
API const char *path(void) { return sWork->path; }
API int sendBytes(const void *p, unsigned n) { return sendIo(NULL, p, n); }
API int recvBytes(void *p, unsigned n) { return recvIo(NULL, p, n); }
API int publish(const void *p, unsigned n) { return sinkIo(NULL, p, n); }
API unsigned readBytes(void *p) { void *data; unsigned n = GhostServiceRead(&data); memcpy(p, data, n); GhostServiceReadAck(n); return n; }
API int result(void) { unsigned n; return GhostServicePoll(&n); }
API void release(void) { GhostServiceRelease(); }
API unsigned inspect(unsigned n) { return n == 0 ? violations : n == 1 ? calls : n == 2 ? sBusy : n == 3 ? closed : sWork != NULL; }
API unsigned metric(unsigned n){return n==0?tlsCalls:n==1?reusedCalls:n==2?tick:n==3?sStarted:randomCalls;}
API void idleClose(void){closeConnection(queued==WEB_RETIRE);sClosing=0;queued=NULL;}
API void forget(void){GhostServiceForget();memset(session,0xa5,sizeof(session));}
API void reclaim(void){memset(session,0,sizeof(session));}
API int shutdown(void){return GhostServiceShutdown();}
API unsigned traceValue(unsigned index,unsigned field){
 const struct GhostServiceTrace *t=GhostServiceTrace(index);if(!t)return 0xffffffffu;
 return field==0?t->sentBytes:field==1?t->receivedBytes:field==2?t->lastIo:(unsigned)t->result;
}
API void fault(unsigned n, int v) {
    switch (n) {
    case 0: malformedDns = v; break; case 1: sendResult = v; break; case 2: recvResult = v; break;
    case 3: cancelCommand = v; break; case 4: unrelated = v; break; case 5: randomResult = v; break;
    case 6: sTime = v; break; case 7: rejectCommand = v; break; case 8: tick = v; break;
    case 9: kdWait=v;break;case 10:ipWait=v;break;case 11:failReused=v;break;
    case 12:failFresh=v;break;case 13:partialResponse=v;break;case 14:tlsFailure=v;break;
    }
}
'''


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'GhostServiceTestPlatform.h').write_text(PLATFORM)
        (OUT / 'test.c').write_text('#define GHOST_SERVICE_HOST_TEST\n#include "GhostServiceNative.c"\n' + ADAPTER)
        env = {**os.environ, 'PATH': str(CC.parent) + os.pathsep + os.environ.get('PATH', '')}
        command = [str(CC), '-shared', '-Os', '-std=gnu99', '-static-libgcc', '-I' + str(OUT),
                   '-iquote' + str(ROOT / 'launcher/kernel'), '-I' + str(ROOT / 'include'),
                   '-I' + str(ROOT / 'launcher/third_party/bearssl/inc'), str(OUT / 'test.c'), '-o', str(OUT / 'native.dll')]
        r = subprocess.run(command, env=env, capture_output=True, text=True)
        if r.returncode: raise RuntimeError(r.stderr)
        cls.lib = C.CDLL(str(OUT / 'native.dll'))
        cls.lib.path.restype = C.c_char_p
        cls.lib.traceValue.restype = C.c_uint
        cls.lib.begin.argtypes = [C.c_char_p, C.c_char_p]
        cls.lib.sendBytes.argtypes = cls.lib.publish.argtypes = [C.c_void_p, C.c_uint]
        cls.lib.recvBytes.argtypes = [C.c_void_p, C.c_uint]
        cls.lib.readBytes.argtypes = [C.c_void_p]

    def setUp(self): self.lib.reset()
    def tearDown(self): self.assertEqual(self.lib.inspect(0), 0, 'IOS ABI or buffer ownership violation')
    def begin(self, cursor=b''):
        self.assertEqual(self.lib.begin(cursor, b'jp'), 1)
        self.assertEqual(self.lib.inspect(1), 0, 'Start must not perform IOS work on the caller')

    def test_cursor_and_connection_abi(self):
        self.begin(b'a&b=/+')
        self.assertTrue(self.lib.path().endswith(b'&cursor=a%26b%3D%2F%2B'))
        self.lib.fault(4, 2)
        self.assertEqual(self.lib.connectOnly(), 0)
        self.assertEqual(self.lib.inspect(1), 7)

    def test_bad_dns_offsets_and_types(self):
        for kind in range(1, 5):
            self.lib.reset(); self.begin(); self.lib.fault(0, kind)
            self.assertEqual(self.lib.connectOnly(), -29)

    def test_short_send_would_block_eof_and_receive_bounds(self):
        self.begin(); self.assertEqual(self.lib.connectOnly(), 0)
        out = C.create_string_buffer(8)
        self.assertEqual(self.lib.sendBytes(b'abcdef', 6), 2)
        self.lib.fault(1, -6); self.assertEqual(self.lib.sendBytes(b'abcdef', 6), 0)
        self.assertEqual(self.lib.recvBytes(out, 8), 2); self.assertEqual(out.raw[:2], b'RR')
        self.lib.fault(2, -6); self.assertEqual(self.lib.recvBytes(out, 8), 0)
        for n in (0, 9):
            self.lib.fault(2, n); self.assertEqual(self.lib.recvBytes(out, 8), -20)
        self.assertEqual(self.lib.sendBytes(b'x', 2049), -20)
        self.assertEqual(self.lib.recvBytes(out, 2049), -20)

    def test_cancellation_cannot_release_inflight_ios_memory(self):
        self.begin(); self.lib.fault(3, 6); self.lib.job()
        self.assertEqual(self.lib.result(), -26)
        self.assertEqual(self.lib.inspect(2), 1)
        self.lib.release(); self.assertEqual(self.lib.inspect(2), 0)
        self.assertEqual(self.lib.inspect(4), 0)

    def test_failure_closes_open_resources(self):
        self.begin(); self.lib.fault(7, 4); self.lib.job()
        self.assertEqual(self.lib.result(), -20)
        self.assertEqual(self.lib.inspect(3), 1)
        self.lib.release();self.assertEqual(self.lib.shutdown(),0)
        self.lib.idleClose();self.assertEqual(self.lib.shutdown(),1)
        self.assertEqual(self.lib.inspect(3),2)

    def test_clock_entropy_and_deadline_fail_closed(self):
        for fault, value, expected in [(5, -1, -23), (6, 0, -22)]:
            self.lib.reset(); self.begin(); self.lib.fault(fault, value); self.lib.job()
            self.assertEqual(self.lib.result(), expected)

    def test_startup_retries_get_their_own_time_budget(self):
        self.begin();self.lib.fault(9,3);self.lib.fault(10,4)
        self.assertEqual(self.lib.connectOnly(),0)
        self.assertEqual(self.lib.inspect(1),14)
        self.assertGreater(self.lib.metric(3),0)
        self.lib.fault(8,self.lib.metric(3)+121*1898437)
        self.assertEqual(self.lib.publish(b'a',1),0)

    def test_fresh_handshake_retries_once_with_new_entropy(self):
        self.begin();self.lib.fault(12,1);self.lib.job()
        self.assertEqual(self.lib.result(),1)
        self.assertEqual(self.lib.metric(0),3)
        self.assertEqual(self.lib.metric(4),2)
        self.assertEqual(self.lib.inspect(1),12)

    def test_two_dropped_handshakes_stop(self):
        self.begin();self.lib.fault(12,5);self.lib.job()
        self.assertEqual(self.lib.result(),-20)
        self.assertEqual(self.lib.metric(0),2)
        self.assertEqual(self.lib.traceValue(0,3),C.c_uint(-20).value)
        self.assertEqual(self.lib.traceValue(1,3),C.c_uint(-20).value)
        self.assertEqual(self.lib.traceValue(2,3),0xffffffff)

    def test_partial_response_and_certificate_failure_are_not_retried(self):
        for fault,value,result in [(13,1,-20),(14,-21,-21)]:
            self.lib.reset();self.begin();self.lib.fault(12,5);self.lib.fault(fault,value)
            self.lib.job();self.assertEqual(self.lib.result(),result)
            self.assertEqual(self.lib.metric(0),1)

    def test_local_cache_reclaim_then_reopen_keeps_network_startup(self):
        self.begin();self.lib.job();self.lib.release();self.lib.forget()
        self.assertEqual(self.lib.begin(b'',b'jp'),0)
        self.lib.idleClose();self.lib.reclaim()
        self.assertEqual(self.lib.begin(b'',b'jp'),1)
        self.lib.job();self.assertEqual(self.lib.result(),1)
        self.assertEqual(self.lib.inspect(1),12)
        self.assertEqual(self.lib.inspect(3),1)
        self.lib.release();self.assertEqual(self.lib.shutdown(),0)
        self.lib.idleClose();self.assertEqual(self.lib.shutdown(),1)
        self.assertEqual(self.lib.inspect(3),2)

    def test_startup_timeout_is_distinct(self):
        self.begin();self.lib.fault(10,2000);self.lib.job()
        self.assertEqual(self.lib.result(),-28)

    def test_pages_reuse_tls_after_transfer_workspace_is_overwritten(self):
        self.begin();self.lib.job();self.assertEqual(self.lib.result(),1)
        calls=self.lib.inspect(1);self.assertEqual(self.lib.metric(0),2)
        self.lib.release()
        self.assertEqual(self.lib.begin(b'next',b'jp'),1)
        self.lib.job();self.assertEqual(self.lib.result(),1)
        self.assertEqual(self.lib.inspect(1),calls)
        self.assertEqual(self.lib.metric(1),2)

    def test_stale_connection_reconnects_once(self):
        self.begin();self.lib.job();self.lib.release()
        self.assertEqual(self.lib.begin(b'next',b'jp'),1)
        self.lib.fault(11,1);self.lib.job()
        self.assertEqual(self.lib.result(),1)
        self.assertEqual(self.lib.inspect(1),12)

    def test_ring_wrap_preserves_stream(self):
        self.begin(); output = C.create_string_buffer(16384)
        for i in range(9):
            data = bytes([i]) * 10000
            self.assertEqual(self.lib.publish(data, len(data)), 1)
            got = bytearray()
            while len(got) < len(data):
                n = self.lib.readBytes(output); self.assertGreater(n, 0); got.extend(output.raw[:n])
            self.assertEqual(got, data)


if __name__ == '__main__': unittest.main()
