"""Mailbox ownership, torn publication and reset epochs with the actual ARM bridge.

The worker is an in-memory stub; no sockets or emulator are started.
"""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#define TIMEWARP_LIVE_RACING 1
#define __GLOBAL_H__
#define __STRING_H__
#include "susamune/live_transport.h"
#include "susamune/susamune_cfg.h"
#include "MoonshineNet.h"
typedef __SIZE_TYPE__ size_t;
void *memset(void *p,int c,size_t n){unsigned char *d=p;while(n--)*d++=(unsigned char)c;return p;}
void *memcpy(void *p,const void *q,size_t n){unsigned char*d=p;const unsigned char*s=q;while(n--)*d++=*s++;return p;}
static int equal(const void *p,const void *q,unsigned n){const unsigned char*a=p,*b=q;while(n--)if(*a++!=*b++)return 0;return 1;}
static unsigned actor,violation,mutate,reads,poseIssued;
static void sync_after_write(void*,unsigned);
static void sync_before_read(void*,unsigned);
#include "MoonshineNetBridge.c"
void MoonshineNetLogSample(const struct MoonshineNetStatus *s,unsigned t,unsigned r,unsigned p){(void)s;(void)t;(void)r;(void)p;}
void MoonshineNetLogPacket(int o,const TWLiveEndpoint *e,const void *d,unsigned b){(void)o;(void)e;(void)d;(void)b;}
void MoonshineNetLogEvent(const char *n,unsigned e,unsigned s,int r){(void)n;(void)e;(void)s;(void)r;}

static struct MoonshineNetStatus fakeStatus;
static struct MoonshineNetPacket fakeRx;
static unsigned starts,sends,poses,stops,hasRx,isRetired,lastPort,lastByte;
int MoonshineNetInit(void){return 1;}
int MoonshineNetStart(const struct MoonshineNetConfig*c){++starts;memset(&fakeStatus,0,sizeof(fakeStatus));fakeStatus.epoch=c->epoch;
 fakeStatus.state=MOONSHINE_NET_READY;lastPort=(c->localPort[0]<<8)|c->localPort[1];isRetired=0;
 fakeStatus.local.ip[0]=192;fakeStatus.local.ip[1]=168;fakeStatus.local.ip[2]=1;fakeStatus.local.ip[3]=4;
 fakeStatus.local.port[0]=c->localPort[0];fakeStatus.local.port[1]=c->localPort[1];return 1;}
int MoonshineNetPoll(struct MoonshineNetStatus*s){*s=fakeStatus;return 1;}
int MoonshineNetSendTo(unsigned e,const struct MoonshineNetEndpoint*p,const void*d,unsigned n){
 if(e!=fakeStatus.epoch||!n||p->reserved[0]||p->reserved[1])++violation;
 ++sends;lastPort=(p->port[0]<<8)|p->port[1];lastByte=*(const unsigned char*)d;return 1;}
int MoonshineNetPublishPose(unsigned e,const struct MoonshineNetEndpoint*p,const void*d,unsigned n){
 if(e!=fakeStatus.epoch||!n||!p->port[0])++violation;++poses;lastByte=*(const unsigned char*)d;return 1;}
int MoonshineNetReceive(unsigned e,struct MoonshineNetPacket*p){if(!hasRx)return 0;
 if(e!=fakeStatus.epoch)++violation;*p=fakeRx;hasRx=0;return 1;}
void MoonshineNetRequestStop(unsigned e){if(e!=fakeStatus.epoch)++violation;++stops;}
int MoonshineNetRetired(unsigned e){if(e!=fakeStatus.epoch)++violation;return isRetired;}
static void sync_after_write(void *p,unsigned n){
 size_t a=(size_t)p,b=(size_t)&sMailbox;unsigned o;
 if(a<b||a+n>b+sizeof(sMailbox)){++violation;return;}o=(unsigned)(a-b);
 if((o|n)&31)++violation;
 if(actor==1&&!((o+n<=64)||(o>=96&&o+n<=1248)||(o>=2400&&o+n<=2688)))++violation;
 if(actor==2&&!((o>=64&&o+n<=96)||(o>=1248&&o+n<=2400)||(o>=2688&&o+n<=2720)))++violation;
}
static void sync_before_read(void*p,unsigned n){
 (void)n;
 if(mutate&&p==&sMailbox.pose&&++reads==2){TWLivePose next;unsigned saved=actor;
  mutate=0;actor=1;memset(&next,0,sizeof(next));next.epoch=sStatus.epoch;
  next.bytes=1;next.endpoint.ip[0]=127;next.endpoint.ip[3]=1;next.endpoint.port=4567;next.data[0]=0x77;
  TWLivePublish(&sMailbox.pose,&next,sizeof(next),&poseIssued,&sIo);actor=saved;}
}
static unsigned commandIssued,indicesIssued;
static void request(unsigned epoch,unsigned sequence,unsigned operation){TWLiveCommand c;
 memset(&c,0,sizeof(c));c.epoch=epoch;c.sequence=sequence;c.operation=operation;c.localPort=23456;
 actor=1;TWLivePublish(&sMailbox.command,&c,sizeof(c),&commandIssued,&sIo);actor=2;}
static void indices(unsigned epoch,unsigned write,unsigned read){TWLiveIndices c;
 memset(&c,0,sizeof(c));c.epoch=epoch;c.txWrite=write;c.rxRead=read;
 actor=1;TWLivePublish(&sMailbox.indices,&c,sizeof(c),&indicesIssued,&sIo);actor=2;}
static void packet(unsigned slot,unsigned epoch,unsigned value){TWLivePacket p;memset(&p,0,sizeof(p));
 p.epoch=epoch;p.bytes=1;p.endpoint.ip[0]=10;p.endpoint.ip[3]=1;p.endpoint.port=4567;p.data[0]=value;
 actor=1;TWLiveCopyOut(&sMailbox.tx[slot],&p,sizeof(p));Flush(&sMailbox.tx[slot],sizeof(p));actor=2;}
static void service(void){unsigned char ppc[1536];unsigned concurrentPose=mutate;
 memcpy(ppc,&sMailbox.command,64);memcpy(ppc+64,sMailbox.tx,1152);memcpy(ppc+1216,&sMailbox.pose,288);
 actor=2;MoonshineNetBridgeService();
 if(!equal(ppc,&sMailbox.command,64)||!equal(ppc+64,sMailbox.tx,1152))++violation;
 /* A deliberate concurrent PPC pose write is allowed by the torn-read check. */
 if(!concurrentPose&&!equal(ppc+1216,&sMailbox.pose,288))++violation;
}
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
__declspec(dllexport) int run(void){unsigned i,issued=0,networkGeneration;TWLivePose p,copy;
 CHECK(sizeof(sMailbox)==2720&&sizeof(struct SusamuneCfg)==5152);
 CHECK(TWLiveDescriptorValid(TW_LIVE_MAGIC,1,TW_LIVE_DATA_END-sizeof(sMailbox),sizeof(sMailbox),1,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,1,TW_LIVE_DATA_END-sizeof(sMailbox)+32,sizeof(sMailbox),1,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,1,0xffffffe0u,sizeof(sMailbox),1,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,1,TW_LIVE_DATA_BEGIN+1,sizeof(sMailbox),1,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,2,TW_LIVE_DATA_BEGIN,sizeof(sMailbox),1,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,1,TW_LIVE_DATA_BEGIN,4096,1,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,1,TW_LIVE_DATA_BEGIN,sizeof(sMailbox),3,0));
 CHECK(!TWLiveDescriptorValid(TW_LIVE_MAGIC,1,TW_LIVE_DATA_BEGIN,sizeof(sMailbox),1,1));
 CHECK(TWLiveCountValid(1,0xfffffffeu)&&!TWLiveCountValid(2,0xfffffffdu));
 CHECK(!TWLiveCountValid(0,1));
 memset(&p,0,sizeof(p));p.epoch=1;p.bytes=1;p.endpoint.ip[0]=127;p.endpoint.ip[3]=1;p.endpoint.port=4567;
 actor=1;CHECK(TWLivePublish(&sMailbox.pose,&p,sizeof(p),&poseIssued,&sIo));
 actor=2;CHECK(TWLiveRead(&copy,&sMailbox.pose,sizeof(copy),&sIo));
 sMailbox.pose.generation=0;
 CHECK(!TWLiveRead(&copy,&sMailbox.pose,sizeof(copy),&sIo));
 CHECK(TWLiveResume(&issued,&sMailbox.pose,&sIo)&&issued==1);
 actor=1;CHECK(TWLivePublish(&sMailbox.pose,&p,sizeof(p),&issued,&sIo)&&issued==2);poseIssued=issued;
 issued=0xffffffffu;CHECK(!TWLivePublish(&sMailbox.pose,&p,sizeof(p),&issued,&sIo));
 actor=2;sInitialized=1;sStatus.epoch=1;sStatus.state=TW_LIVE_IDLE;Publish();
 indices(1,0,0);request(1,1,TW_LIVE_BEGIN);service();
 CHECK(starts==1&&lastPort==23456&&sStatus.state==TW_LIVE_READY);
 CHECK(sMailbox.networkInfo.epoch==1&&sMailbox.networkInfo.endpoint.port==23456&&sMailbox.networkInfo.endpoint.ip[3]==4);
 CHECK(sMailbox.networkInfo.reserved[0]==0&&sMailbox.networkInfo.reserved[1]==0x01000000u&&sMailbox.networkInfo.reserved[2]==0);
 networkGeneration=sMailbox.networkInfo.generation;
 for(i=0;i<5;i++)service();CHECK(sMailbox.networkInfo.generation==networkGeneration);
 fakeStatus.sent=3;fakeStatus.received=2;fakeStatus.dropped=4;fakeStatus.sendErrors=5;fakeStatus.receiveErrors=6;fakeStatus.lastError=-28;
 service();CHECK(sMailbox.networkInfo.generation==networkGeneration+1);
 CHECK(sMailbox.networkInfo.reserved[0]==0x00030002u&&sMailbox.networkInfo.reserved[1]==0x01040506u&&
  (int)sMailbox.networkInfo.reserved[2]==-28);
 networkGeneration=sMailbox.networkInfo.generation;
 service();CHECK(sMailbox.networkInfo.generation==networkGeneration);
 fakeStatus.sent=fakeStatus.received=fakeStatus.dropped=fakeStatus.sendErrors=fakeStatus.receiveErrors=0xffffffffu;
 service();CHECK(sMailbox.networkInfo.reserved[0]==0xffffffffu&&sMailbox.networkInfo.reserved[1]==0x01ffffffu);
 poses=0;sPoseSeen=poseIssued;
 for(i=0;i<4;i++)packet(i,1,0x40+i);indices(1,4,0);
 for(i=0;i<4;i++)service();service();
 CHECK(sends==4&&lastByte==0x43&&lastPort==4567&&sStatus.txRead==4);
 /* Ring counters also work across unsigned wrap, without accepting a fifth slot. */
 sStatus.txRead=0xfffffffeu;for(i=0;i<3;i++)packet((0xfffffffeu+i)&3,1,0x50+i);
 indices(1,1,0);for(i=0;i<3;i++)service();CHECK(sends==7&&sStatus.txRead==1);
 memset(&fakeRx,0,sizeof(fakeRx));fakeRx.epoch=1;fakeRx.bytes=1;
 fakeRx.endpoint.ip[0]=127;fakeRx.endpoint.ip[3]=1;fakeRx.endpoint.port[0]=0x12;fakeRx.endpoint.port[1]=0x34;
 for(i=0;i<4;i++){hasRx=1;service();}hasRx=1;service();
 CHECK(sStatus.rxWrite==4&&hasRx&&sMailbox.rx[0].endpoint.port==0x1234);
 indices(1,1,4);service();CHECK(sStatus.rxWrite==5&&!hasRx);
 actor=1;CHECK(TWLivePublish(&sMailbox.pose,&p,sizeof(p),&poseIssued,&sIo));
 mutate=1;reads=0;service();CHECK(poses==0&&!mutate);service();CHECK(poses==1&&lastByte==0x77);
 CHECK(!MoonshineNetBridgeRetire()&&sStatus.epoch==2&&sStatus.state==TW_LIVE_RETIRING&&stops==1);
 CHECK(!sMailbox.networkInfo.generation);
 CHECK(!MoonshineNetBridgeRetire()&&sStatus.epoch==2&&stops==1);
 indices(2,0,0);request(2,2,TW_LIVE_BEGIN);service();CHECK(starts==1);
 isRetired=1;service();CHECK(sStatus.state==TW_LIVE_IDLE);service();CHECK(starts==2&&sStatus.epoch==2);
 CHECK(sMailbox.networkInfo.epoch==2&&sMailbox.networkInfo.reserved[0]==0&&sMailbox.networkInfo.reserved[1]==0x01000000u&&sMailbox.networkInfo.reserved[2]==0);
 packet(0,1,0xee);indices(2,1,0);service();
 CHECK(sends==7&&sStatus.state==TW_LIVE_RETIRING&&sStatus.epoch==3&&sStatus.error==BRIDGE_PROTOCOL_ERROR);
 isRetired=1;service();indices(3,0,0);request(3,3,TW_LIVE_BEGIN);service();
 indices(3,5,0);service();CHECK(sStatus.state==TW_LIVE_RETIRING&&sStatus.epoch==4&&sends==7);
 CHECK(!violation);return 0;
}
'''


class LiveTransportTest(unittest.TestCase):
    def test_ownership_sequences_descriptor_and_retirement(self):
        with tempfile.TemporaryDirectory(prefix='live-transport-') as folder:
            folder = Path(folder)
            source, dll = folder / 'bridge.c', folder / 'bridge.dll'
            source.write_text(HARNESS)
            # Only platform headers are replaced; the actual bridge is included unchanged.
            result = subprocess.run([str(ROOT / 'toolchain/clang.exe'), '--target=x86_64-pc-windows-msvc',
                '-shared', '-O2', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry',
                '-Wno-pointer-to-int-cast', '-I', str(folder), '-I', str(ROOT / 'include'),
                '-I', str(ROOT / 'launcher/kernel'), str(source), '-o', str(dll)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            library = C.CDLL(str(dll))
            try:
                self.assertEqual(library.run(), 0, 'native harness assertion line')
            finally:
                C.windll.kernel32.FreeLibrary(C.c_void_p(library._handle))


if __name__ == '__main__':
    unittest.main()
