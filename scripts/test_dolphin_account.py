"""Native account journal + cooperative protocol, with real CARD jobs and local HTTP replies."""
from pathlib import Path
import ctypes as C
import json,subprocess,unittest
import test_dolphin_files,test_ghost_service
from test_ghost_account import Info,PAIR,CODE,UUID
from test_dolphin_ghost_library import Response
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test-dolphin-account'
HTTP=C.CFUNCTYPE(C.c_int,C.c_char_p,C.c_char_p,C.c_char_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.POINTER(C.c_uint),C.POINTER(C.c_uint))
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  test_dolphin_files.Tests.setUpClass();test_ghost_service.build();OUT.mkdir(parents=True,exist_ok=True)
  source=(ROOT/'native/dolphin_https/account.cpp').read_text()
  source=source.replace('#include "../../../launcher/kernel/GhostServiceAccount.h"','#include "GhostServiceAccount.h"')
  source=source.replace('Work &s=*reinterpret_cast<Work *>(DOLPHIN_ACCOUNT_WORK_BASE);','Work s;')
  source=source.replace('reinterpret_cast<void *>(SUSAMUNE_DOLPHIN_GHOST_FILE_TRANSFER_PPC_BASE)','transfer')
  source=source.replace('reinterpret_cast<GhostJson *>(DOLPHIN_WEB_JSON_BASE)','&parser')
  source=source.replace('moonshine_https_api.sha256','httpsApi->sha256')
  base=(ROOT/'build/test-dolphin-files/fixture.cpp').read_text()
  shim=r"""
#include "susamune/dolphin_storage_api.hxx"
extern "C" {
#include "GhostServiceAccount.h"
}
extern "C" void MoonshineNativeInit(){}
static unsigned char transfer[65536];
static GhostJson parser;
static unsigned tick=1000,networkCalls;
static int fileError,ghostError,networkHold;
static SusamuneGhostStorageResponse ghostResponse;
static unsigned ghostBytes;
static std::vector<unsigned char> ghostData;
static bool ghostPending,httpPending;
static int httpResult;
static DolphinHttpsInfo httpInfo;
typedef int (*Http)(const char *,const char *,const char *,const void *,unsigned,void *,unsigned,unsigned *,unsigned *);
static Http callback;
static bool httpBegin(const char *path,const DolphinHttpsRequest *r,void *out,unsigned cap){
 if(httpPending)return false;httpPending=true;++networkCalls;httpInfo={};
 httpResult=callback(path,r->method,r->headers,r->body,r->bytes,out,cap,&httpInfo.used,&httpInfo.httpStatus);return true;
}
static void httpUpdate(){}
static int httpTake(DolphinHttpsInfo *out){if(networkHold || !httpPending)return 1;*out=httpInfo;httpPending=false;return httpResult;}
static bool ghostBegin(const SusamuneGhostStorageRequest &r){
 if(ghostPending)return false;ghostPending=true;ghostResponse={};ghostResponse.status=ghostError;
 ghostResponse.payloadSize=ghostData.size();memcpy(transfer,ghostData.data(),ghostData.size());return true;
}
static void ghostUpdate(){}
static bool ghostTake(SusamuneGhostStorageResponse *out){if(!ghostPending)return false;*out=ghostResponse;ghostPending=false;return true;}
static unsigned seconds(){return tick;}
static const DolphinStorageHost host={DolphinFiles::read,DolphinFiles::write,DolphinFiles::create,DolphinFiles::remove,DolphinFiles::take,
 httpBegin,httpUpdate,httpTake,ghostBegin,ghostUpdate,ghostTake,seconds};
namespace NativeStorage { bool libraryBegin(const SusamuneGhostStorageRequest &,const DolphinStorageHost *,unsigned){return false;} }
namespace DolphinGhostLibrary { void update(){} bool take(SusamuneGhostStorageResponse *){return false;} }
"""+source+r"""
extern "C" {
__declspec(dllexport) void accountReset(){reset();initialized=false;networkCalls=0;networkHold=ghostError=0;tick=1000;httpPending=ghostPending=false;}
__declspec(dllexport) void restartAccount(){initialized=false;DolphinFiles::initialized=false;DolphinFiles::init();httpPending=ghostPending=false;networkHold=0;}
__declspec(dllexport) void setHttp(Http h){callback=h;}
__declspec(dllexport) void setTime(unsigned n){tick=n;}
__declspec(dllexport) void holdNetwork(int n){networkHold=n;}
__declspec(dllexport) unsigned calls(){return networkCalls;}
__declspec(dllexport) unsigned journal(unsigned which){return which==0?s.generation:which==1?s.bank:s.phase;}
__declspec(dllexport) void corruptBank(unsigned bank){for(auto &f:files)if(f.used && !strcmp(f.entry.mFilename,kFile))f.data[bank*8192+32]^=1;}
__declspec(dllexport) void restoreOldBank(unsigned bank){for(auto &f:files)if(f.used && !strcmp(f.entry.mFilename,kFile))memcpy(f.data.data()+bank*8192,f.data.data()+(1-bank)*8192,256);}
__declspec(dllexport) void ghost(const void *p,unsigned n,int error){ghostData.assign((const unsigned char*)p,(const unsigned char*)p+n);ghostError=error;}
__declspec(dllexport) int accountBegin(unsigned op,const char *description){
 SusamuneGhostStorageRequest r={};r.requestMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;r.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;r.requestSeq=1;
 r.command=op==4?SUSAMUNE_GHOST_CMD_WEB_UPLOAD:SUSAMUNE_GHOST_CMD_WEB_ACCOUNT;r.profile=op==4?0:SUSAMUNE_GHOST_IMPORTED_PROFILE;r.slot=op==4?7:op;
 if(op==4){r.expectedGeneration=9;r.payloadSize=sizeof(GhostServiceUpload);memset(transfer,0,r.payloadSize);if(description)strncpy((char*)transfer,description,r.payloadSize);}
 return moonshine_storage_api.begin(r,&host);
}
__declspec(dllexport) int accountStep(SusamuneGhostStorageResponse *out){moonshine_storage_api.update();DolphinFiles::perform(sector);return moonshine_storage_api.take(out);}
__declspec(dllexport) void info(GhostServiceAccountInfo *out){memcpy(out,transfer,sizeof(*out));}
}
"""
  (OUT/'fixture.cpp').write_text(base+'\n'+shim)
  objs=[ROOT/'build/ghost-service-tests'/n for n in ('GhostServiceAccount.o','GhostServiceJson.o','sha2small.o','enc32be.o','dec32be.o')]
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-shared','-static-libgcc','-static-libstdc++','-DTIMEWARP_LIVE_RACING=1','-I'+str(ROOT/'include'),'-iquote'+str(ROOT/'launcher/kernel'),'-I'+str(ROOT/'launcher/third_party/bearssl/inc'),str(OUT/'fixture.cpp'),*map(str,objs),'-o',str(OUT/'account.dll')],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr[-6000:])
  cls.lib=C.CDLL(str(OUT/'account.dll'));cls.lib.setApi.argtypes=[C.c_void_p];cls.lib.setApi(C.byref(test_dolphin_files.Tests.api))
  cls.lib.accountBegin.argtypes=[C.c_uint,C.c_char_p];cls.lib.ghost.argtypes=[C.c_void_p,C.c_uint,C.c_int];cls.lib.setHttp.argtypes=[HTTP]
 def setUp(self):
  self.lib.accountReset();self.responses=[];self.requests=[];self.failure=None;self.current=Info()
  @HTTP
  def http(path,method,headers,body,n,out,cap,used,status):
   self.requests.append((path.decode(),method.decode(),headers.decode(),C.string_at(body,n)))
   if self.failure is not None:return self.failure
   if not self.responses:return -24
   code,value=self.responses.pop(0);raw=json.dumps(value).encode();self.assertLessEqual(len(raw),cap)
   C.memmove(out,raw,len(raw));used[0]=len(raw);status[0]=code;return 0
  self.http=http;self.lib.setHttp(http)
 def run_op(self,op,description=b''):
  self.assertTrue(self.lib.accountBegin(op,description));out=Response()
  for _ in range(200):
   if self.lib.accountStep(C.byref(out)):
    if not out.status and op!=4:self.lib.info(C.byref(self.current))
    return out.status
  self.fail('native account did not finish')
 def link(self):
  self.responses=[(200,CODE),(200,PAIR)];self.assertEqual(self.run_op(1),0)
  self.lib.setTime(1005);self.assertEqual(self.run_op(2),0);self.assertEqual(self.current.linked,1)
  self.requests.clear()
 def ghost(self,error=0):self.lib.ghost(b'canonical ghost unchanged',25,error)
 def test_link_persists_across_restart_and_uses_dolphin_name(self):
  self.link();self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,1);self.assertEqual(self.current.user,b'runner')
  self.assertEqual(self.requests,[])
 def test_link_poll_interval_and_slow_down(self):
  self.responses=[(200,CODE),(400,{'error':{'code':'slow_down'},'interval':15})]
  self.assertEqual(self.run_op(1),0);self.assertEqual(json.loads(self.requests[0][3])['client_name'],'Moonshine Dolphin')
  self.assertEqual(self.run_op(2),0);self.assertEqual(len(self.requests),1)
  self.lib.setTime(1005);self.assertEqual(self.run_op(2),0);self.assertEqual(self.current.retry,15)
 def test_upload_and_rotated_token_persist(self):
  self.link();self.ghost();pair={**PAIR,'refresh_token':'dgr_'+'s'*43}
  self.responses=[(200,pair),(201,{'upload':{'upload_id':UUID}}),(200,{}),(201,{})]
  self.assertEqual(self.run_op(4,b'my description'),0);self.assertEqual([r[1] for r in self.requests],['POST','POST','PUT','POST'])
  self.assertEqual(self.requests[2][3],b'canonical ghost unchanged');self.assertEqual(json.loads(self.requests[1][3])['description'],'my description')
  self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,1)
 def test_failed_refresh_not_replayed_after_restart(self):
  self.link();self.ghost();self.failure=-20;self.assertEqual(self.run_op(4),-20)
  self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,0)
  self.assertEqual(self.run_op(4),-33);self.assertEqual(len(self.requests),1)
 def test_stop_during_refresh_leaves_durable_tombstone(self):
  self.link();self.ghost();self.lib.holdNetwork(1);self.responses=[(200,PAIR)]
  self.assertTrue(self.lib.accountBegin(4,b''));r=Response()
  for _ in range(40):self.lib.accountStep(C.byref(r))
  self.assertEqual(len(self.requests),1);self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,0)
 def test_bad_or_stale_ghost_does_not_rotate(self):
  self.link();self.ghost(-8);self.assertEqual(self.run_op(4),-8);self.assertEqual(self.requests,[])
  self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,1)
 def test_invalid_description_does_not_rotate(self):
  self.link();self.ghost();self.assertEqual(self.run_op(4,b'bad\ntext'),-35);self.assertEqual(self.requests,[])
 def test_write_failure_prevents_network_rotation(self):
  self.link();self.ghost();self.lib.setFault(2);self.assertNotEqual(self.run_op(4),0);self.assertEqual(self.requests,[])
 def test_damaged_newest_bank_cannot_restore_previous_token(self):
  self.link();self.ghost();self.failure=-20;self.assertEqual(self.run_op(4),-20)
  self.lib.corruptBank(self.lib.journal(1));self.lib.restartAccount();self.assertNotEqual(self.run_op(0),0)
  self.assertEqual(self.run_op(3),0);self.assertEqual(self.current.linked,0)
 def test_equal_generation_banks_are_rejected(self):
  self.link();self.ghost();self.failure=-20;self.run_op(4);self.lib.restoreOldBank(self.lib.journal(1))
  self.lib.restartAccount();self.assertNotEqual(self.run_op(0),0)
 def test_failure_after_refresh_keeps_new_token(self):
  self.link();self.ghost();self.responses=[(200,PAIR),(500,{})];self.assertEqual(self.run_op(4),-31)
  self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,1)
 def test_unlink_survives_network_failure(self):
  self.link();self.failure=-20;self.assertEqual(self.run_op(3),0);self.lib.restartAccount();self.assertEqual(self.run_op(0),0);self.assertEqual(self.current.linked,0)
if __name__=='__main__':unittest.main()
