"""Replay-report source ownership and exact acknowledgements."""
import ctypes as C,os,re,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PREFIX=r"""
#include <cstring>
#define MOONSHINE_GHOST_TRACE 1
#define IS_EMULATOR 0
#include "susamune/ghost_replay_report.h"
alignas(32) static MsReplayReportMailbox mail;
alignas(32) static unsigned char testPayload[0x60000];
#undef MS_REPLAY_REPORT_MAILBOX_PPC
#undef MS_REPLAY_REPORT_DATA_PPC
#define MS_REPLAY_REPORT_MAILBOX_PPC ((__UINTPTR_TYPE__)&mail)
#define MS_REPLAY_REPORT_DATA_PPC ((__UINTPTR_TYPE__)testPayload)
static unsigned game=0x474d5350,flushes;
namespace GhostTrace {bool backendIdentity(unsigned &n){n=77;return true;}}
void DCInvalidateRange(void*,unsigned){}void DCStoreRange(void*,unsigned){++flushes;}
"""
SUFFIX=r"""
extern "C" {
__declspec(dllexport) void resetTest(){std::memset(&mail,0,sizeof(mail));std::memset(testPayload,0,sizeof(testPayload));GhostReplayReport::sequence=GhostReplayReport::boot=GhostReplayReport::lease=flushes=0;mail.response={MS_REPLAY_REPORT_MAGIC,1,77,0,0,0,{0,0}};unsigned h[16]={MS_REPLAY_REPORT_MAGIC,1,64,320,game,123,456,119,0,0,256,1,0,511,0,0};for(unsigned i=0;i<16;++i)MsReplayReportPut(testPayload+i*4,h[i]);}
__declspec(dllexport) int reserve(){return GhostReplayReport::reserve();}
__declspec(dllexport) int send(){return GhostReplayReport::submit(320,123,456);}
__declspec(dllexport) int pending(){return GhostReplayReport::pending();}
__declspec(dllexport) unsigned poll(){return GhostReplayReport::poll();}
__declspec(dllexport) void ack(unsigned sequence,unsigned nonce,unsigned status){mail.response.ack=sequence;mail.response.bootNonce=nonce;mail.response.status=status;}
__declspec(dllexport) unsigned value(unsigned key){return key==0?mail.request.sequence:key==1?mail.request.checksum:key==2?MsReplayReportHash(2166136261u,testPayload,320):flushes;}
__declspec(dllexport) void badHeader(){testPayload[63]=1;}
}
"""
class PublisherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='replay-publisher-');cls.addClassCleanup(cls.tmp.cleanup);d=Path(cls.tmp.name)
  source=re.sub(r'^#include .*$', '',(ROOT/'src/ghost_replay_report.cpp').read_text(),flags=re.M).replace('*reinterpret_cast<volatile const unsigned*>(0x80000000u)','game')
  (d/'fixture.cpp').write_text(PREFIX+source+SUFFIX)
  env=dict(os.environ);env['PATH']='C:/msys64/mingw64/bin;'+env.get('PATH','')
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-shared','-static','-O2','-I',str(ROOT/'include'),str(d/'fixture.cpp'),'-o',str(d/'fixture.dll')],capture_output=True,text=True,env=env)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
  cls.lib=C.CDLL(str(d/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)));cls.lib.value.restype=C.c_uint
 def setUp(self):self.lib.resetTest()
 def test_payload_stays_owned_until_exact_ack(self):
  self.assertTrue(self.lib.reserve());self.assertTrue(self.lib.send());self.assertTrue(self.lib.pending());self.assertFalse(self.lib.reserve())
  self.lib.ack(2,77,0);self.assertTrue(self.lib.pending());self.lib.ack(1,78,0);self.assertTrue(self.lib.pending())
  self.lib.ack(1,77,0);self.assertFalse(self.lib.pending());self.assertEqual(self.lib.poll(),1);self.assertEqual(self.lib.poll(),0)
 def test_header_and_checksum_are_checked_before_publication(self):
  self.lib.badHeader();self.assertFalse(self.lib.send());self.assertEqual(self.lib.value(0),0)
  self.lib.resetTest();self.assertTrue(self.lib.send());self.assertEqual(self.lib.value(1),self.lib.value(2))
 def test_settled_failure_releases_the_lease_and_reports_status(self):
  self.assertTrue(self.lib.send());self.lib.ack(1,77,4);self.assertFalse(self.lib.pending());self.assertEqual(self.lib.poll(),5);self.assertTrue(self.lib.reserve())
 def test_requests_have_increasing_identities(self):
  self.assertTrue(self.lib.send());self.lib.ack(1,77,0);self.assertEqual(self.lib.poll(),1);self.assertTrue(self.lib.send());self.assertEqual(self.lib.value(0),2)
if __name__=='__main__':unittest.main()
