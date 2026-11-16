"""Execute actual PPC preparation-client functions with cache/ready-state doubles."""
import ctypes as C
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PRE=r'''
#define TIMEWARP_LIVE_RACING 1
#include <cstring>
#include "susamune/ghost_trace_prepare.h"
#include "susamune/ghost_simulation.hxx"
#include "susamune/ghost_trace_observation.h"
static MsTracePrepareMailbox localPrepare;
static bool admitted=true,memoryReady=true,normalReady=true,worldBusy=false,online=false,paused=false,camera=false,tas=false,setup=true;
static unsigned speed,ticks=100,stores;static bool fastForward;
static bool actionsFastForwardActive(){return fastForward;}
struct TMarDirector {enum {STATE_NORMAL=4,STATE_PAUSE_MENU=5,STATE_STAGE_EXIT_2=12};unsigned _260=1,mCurState=4;};
static TMarDirector director;static unsigned gSetupThread;
namespace GhostMemory {bool admitted(){return ::admitted;}bool ready(){return memoryReady;}}
namespace RetailInput {const TMarDirector*stageDirector(){return &director;}}
namespace GhostWorldRuntime {bool busy(){return worldBusy;}}
namespace GhostTraceFlat {bool active(){return false;}}
namespace LevelWarp {bool readyForOnlineRace(){return normalReady&&(director.mCurState==4||director.mCurState==5||director.mCurState==11);}
bool readyForStorageMaintenance(unsigned char held){return normalReady&&(director.mCurState==held||director.mCurState==12)&&(held==4||held==5||held==11);}}
namespace PracticeSession {bool paused(){return ::paused;}bool freeCamera(){return camera;}bool recording(){return tas;}bool replaying(){return false;}}
namespace LiveRace {struct Status{bool active;};Status status(){return {online};}}
namespace GhostTraceHooks {unsigned capabilities(){return 0xb00;}}
enum {SETTING_GAMEPLAY_SPEED=1};static struct Settings{unsigned get(unsigned){return speed;}}gSettings;
static bool OSIsThreadTerminated(const void*){return setup;}
static unsigned OSGetTick(){return ++ticks;}
static void DCInvalidateRange(void*,unsigned){}
static void DCStoreRange(void*,unsigned){++stores;}
namespace GhostTrace {
static bool mandatory;bool fastContinuationUntracked(){return false;}bool continuationBackgroundPending(){return mandatory;}
namespace {
struct State {MsTraceResponse response;unsigned request,run,used[2],frame,prepareHello;unsigned char prepareKnown;unsigned error;bool ordinary;GhostSimulation::Snapshot settings;};
static State s;static bool bootReady=true;bool forkBlocksCapture(){return false;}
}
'''
POST=r'''
}
#define API extern "C" __declspec(dllexport)
API void reset(){GhostTrace::mandatory=false;localPrepare={};GhostTrace::s={};GhostTrace::s.response.nonce=1234;GhostTrace::s.ordinary=true;admitted=memoryReady=normalReady=setup=true;worldBusy=online=paused=camera=tas=false;speed=stores=0;fastForward=false;director._260=1;director.mCurState=4;}
API void stalePair(){localPrepare.request={MS_TRACE_PREPARE_MAGIC,MS_TRACE_PREPARE_VERSION,1234,101,MS_PREP_FILE,0x80000001,0xffffff,0};localPrepare.response={MS_TRACE_PREPARE_MAGIC,MS_TRACE_PREPARE_VERSION,1234,101,MS_PREP_READY,0,0x80000001,101};ticks=100;}
API void changeNonce(){GhostTrace::s.response.nonce=5678;}
API unsigned discard(){return GhostTrace::discardOperation();}
API void advertiseVersion(unsigned version){localPrepare.response={MS_TRACE_PREPARE_MAGIC,version,1234,0,MS_PREP_IDLE,0,0,0};}
API void statusFlag(unsigned flags){localPrepare.response.status|=flags;}
API void advertise(){localPrepare.response={MS_TRACE_PREPARE_MAGIC,MS_TRACE_PREPARE_VERSION,1234,0,MS_PREP_IDLE,0,0,0};}
API unsigned next(unsigned run){return GhostTrace::prepareNextRun(run);}
API void ack(unsigned phase,unsigned status,unsigned run){localPrepare.response={MS_TRACE_PREPARE_MAGIC,localPrepare.request.version,1234,localPrepare.request.sequence,phase,status,run,localPrepare.request.operation==MS_PREP_FILE?localPrepare.request.sequence:localPrepare.request.target};}
API unsigned request(unsigned field){return reinterpret_cast<unsigned*>(&localPrepare.request)[field];}
API unsigned permit(unsigned field){return reinterpret_cast<unsigned*>(&localPrepare.permit)[field];}
API void publish(int allow){GhostTrace::preparePermit(allow!=0);}
API void publishMetadata(unsigned held,unsigned reasons,unsigned frozen){GhostTrace::preparePermit(false,held,reasons,frozen!=0);}
API void metadataOwner(){GhostTrace::mandatory=true;localPrepare.response.phase=MS_PREP_LINKING;}
API void revoke(){GhostTrace::revokePreparation();}
API void unsafe(unsigned reason){switch(reason){case 0:normalReady=false;break;case 1:worldBusy=true;break;case 2:online=true;break;case 3:paused=true;break;case 4:camera=true;break;case 5:tas=true;break;case 6:setup=false;break;case 7:speed=50;break;case 8:GhostTrace::s.used[0]=0x40001;break;case 9:fastForward=true;break;case 10:director.mCurState=9;break;case 11:director._260=0;break;}}
API void state(unsigned value){director.mCurState=value;}
API void dropAram(){memoryReady=false;}
API unsigned stored(){return stores;}
API void ackOwner(unsigned phase,unsigned status,unsigned run,unsigned owner){localPrepare.response={MS_TRACE_PREPARE_MAGIC,localPrepare.request.version,1234,localPrepare.request.sequence,phase,status,run,owner};}
API void source(unsigned run){GhostTrace::s.run=run;}
API void pendingWriter(){GhostTrace::s.request=1;GhostTrace::s.response.ackRequest=0;}
'''


class PrepareClientTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='trace-prepare-client-');cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
  source=(ROOT/'src/ghost_trace.cpp').read_text(encoding='utf-8')
  first=source.index('namespace {\nvolatile MsTracePrepareMailbox &prepareBox')
  last=source.index('\nvoid reset(){',first)
  implementation=source[first:last].replace('volatile MsTracePrepareMailbox &prepareBox=*reinterpret_cast<volatile MsTracePrepareMailbox*>(MS_TRACE_PREPARE_PPC);','volatile MsTracePrepareMailbox &prepareBox=localPrepare;')
  (folder/'client.cpp').write_text(PRE+implementation+POST,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-O2','-std=c++11','-I',str(ROOT/'include'),str(folder/'client.cpp'),'-o',str(folder/'client.dll')],env=env,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(folder/'client.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  for name in ('next','request','permit','stored'):getattr(cls.lib,name).restype=C.c_uint
 def setUp(self):self.lib.reset()
 def hello(self):
  self.lib.advertise();self.assertEqual(self.lib.next(0),0);self.assertEqual(self.lib.request(4),1)
  self.lib.ack(0,0,0);self.assertEqual(self.lib.next(0),1)
 def test_required_metadata_progresses_under_menu_and_frame_advance_holds(self):
  for reason in (4,64):
   self.setUp();self.hello();self.lib.metadataOwner();self.lib.state(12)
   self.lib.publishMetadata(4,reason,1);self.assertEqual(self.lib.permit(4),2)
   self.lib.unsafe(3);self.lib.unsafe(7);self.lib.unsafe(5)
   self.lib.publishMetadata(4,reason,1);self.assertEqual(self.lib.permit(4),2)
  self.setUp();self.hello();self.lib.metadataOwner();self.lib.state(5);self.lib.unsafe(3)
  self.lib.publishMetadata(5,0,0);self.assertEqual(self.lib.permit(4),2)
 def test_unborrowed_exit_state_cannot_claim_a_ui_grant(self):
  self.hello();self.lib.metadataOwner();self.lib.state(12)
  self.lib.publishMetadata(4,4,0);self.assertEqual(self.lib.permit(4),0)
 def test_metadata_grant_does_not_authorize_optional_warming(self):
  self.hello();self.lib.metadataOwner();self.lib.ack(1,0,0x80000001);self.lib.state(12)
  self.lib.publishMetadata(4,4,1);self.assertEqual(self.lib.permit(4),0)
 def test_metadata_grant_denies_unsafe_owners_and_transitions(self):
  for unsafe in (0,1,2,4,6,8,10,11):
   self.setUp();self.hello();self.lib.metadataOwner();self.lib.state(12);self.lib.unsafe(unsafe)
   self.lib.publishMetadata(4,4,1);self.assertEqual(self.lib.permit(4),0,unsafe)
  for reason in (8,16,32,128,256,1024):
   self.setUp();self.hello();self.lib.metadataOwner();self.lib.state(12)
   self.lib.publishMetadata(4,reason,1);self.assertEqual(self.lib.permit(4),0,reason)
 def test_old_backend_does_not_receive_requests_or_wait_for_a_reply(self):
  for _ in range(20):self.assertEqual(self.lib.next(0x80000001),0)
  self.lib.publish(1);self.assertEqual(self.lib.stored(),0);self.assertEqual(self.lib.request(3),0)
 def test_matching_stale_pair_and_repeated_tick_cannot_enable_preparation(self):
  self.lib.stalePair();self.assertEqual(self.lib.next(0),0)
  self.assertEqual(self.lib.request(4),1);self.assertNotEqual(self.lib.request(3),101)
  for _ in range(10):self.assertEqual(self.lib.next(0x80000001),0)
  self.lib.publish(1);self.assertEqual(self.lib.permit(4),0)
  self.lib.ack(0,0,0);self.assertEqual(self.lib.next(0),1)
 def test_retirement_requires_fresh_version2_echo_and_version1_keeps_discard3(self):
  for version,operation in ((1,3),(2,6)):
   self.setUp();self.lib.advertiseVersion(version)
   self.assertEqual(self.lib.discard(),3)
   self.assertEqual(self.lib.next(0),0);self.assertEqual(self.lib.request(1),version)
   self.lib.ack(0,0,0);self.assertEqual(self.lib.next(0),1)
   self.assertEqual(self.lib.discard(),operation)
 def test_pending_retirement_is_not_an_error_and_can_admit_cleanup_with_ready_warm_slot(self):
  self.hello();run=0x80000001;self.lib.next(run);self.lib.ack(6,0,run);self.lib.statusFlag(0x100)
  self.assertEqual(self.lib.next(run),2)
  self.lib.publish(1);self.assertEqual(self.lib.permit(4),1)
 def test_unknown_status_flag_and_version1_retire_flag_fail_closed(self):
  for version,flag in ((1,0x100),(2,0x200)):
   self.setUp();self.lib.advertiseVersion(version);self.lib.next(0);self.lib.ack(0,0,0);self.lib.next(0)
   self.lib.statusFlag(flag);self.assertEqual(self.lib.next(0x80000001),0)
   self.assertEqual(self.lib.discard(),3)
 def test_nonce_change_invalidates_previous_support(self):
  self.hello();self.lib.changeNonce();self.assertEqual(self.lib.next(0x80000001),0)
 def test_fresh_hello_echo_is_required_before_reserving(self):
  self.lib.advertise();self.assertEqual(self.lib.next(0),0);seq=self.lib.request(3)
  for _ in range(10):self.assertEqual(self.lib.next(0x80000001),0)
  self.assertEqual(self.lib.request(3),seq)
  self.lib.ack(0,0,0);self.assertEqual(self.lib.next(0),1)
 def test_exact_request_identity_and_terminal_results(self):
  self.hello();run=0x80000001;self.assertEqual(self.lib.next(run),1)
  self.assertEqual((self.lib.request(2),self.lib.request(4),self.lib.request(5),self.lib.request(6)),(1234,2,run,0xffffff))
  self.lib.ack(6,0,run);self.assertEqual(self.lib.next(run),2)
  self.lib.ack(7,2,run);self.assertEqual(self.lib.next(run),3)
  self.lib.ack(9,0,run);self.assertEqual(self.lib.next(run),4)
 def test_next_prepare_does_not_replace_ready_slot_before_primary_start_ack(self):
  self.hello();run=0x80000001;self.lib.next(run);self.lib.ack(6,0,run)
  sequence=self.lib.request(3);self.lib.pendingWriter()
  self.assertEqual(self.lib.next(run+1),1)
  self.assertEqual(self.lib.request(3),sequence);self.assertEqual(self.lib.request(5),run)
 def test_abandoned_ready_reservation_is_canceled_exactly_then_new_file_is_requested(self):
  self.hello();run=0x80000002;self.lib.next(run);self.lib.ack(6,0,run)
  owner=self.lib.request(3);self.lib.source(run-1)
  self.assertEqual(self.lib.next(run+1),1)
  self.assertEqual((self.lib.request(4),self.lib.request(5),self.lib.request(7)),(3,run,owner))
  self.lib.ackOwner(8,0,run,owner)
  self.assertEqual(self.lib.next(run+1),1)
  self.assertEqual((self.lib.request(4),self.lib.request(5)),(2,run+1))
 def test_cleanup_busy_waits_for_background_progress_without_burning_new_identity(self):
  self.hello();run=0x80000002;self.lib.next(run)
  self.lib.ackOwner(8,5,run-1,50)
  sequence=self.lib.request(3)
  for _ in range(10):self.assertEqual(self.lib.next(run),1)
  self.assertEqual(self.lib.request(3),sequence)
  self.lib.ackOwner(8,0,run-1,50);self.assertEqual(self.lib.next(run),1)
  self.assertGreater(self.lib.request(3),sequence)
 def test_current_owned_run_is_never_canceled_as_an_abandoned_reservation(self):
  self.hello();run=0x80000002;self.lib.next(run);self.lib.ack(6,0,run);self.lib.source(run)
  sequence=self.lib.request(3);self.assertEqual(self.lib.next(run+1),1)
  self.assertEqual(self.lib.request(3),sequence)
 def test_permit_requires_normal_offline_ready_gameplay_and_headroom(self):
  for reason in range(12):
   self.setUp();self.hello();self.lib.next(0x80000001);self.lib.ack(1,0,0x80000001);self.lib.publish(1);self.assertEqual(self.lib.permit(4),1)
   self.lib.unsafe(reason);self.lib.publish(1);self.assertEqual(self.lib.permit(4),0,reason)
 def test_safe_save_and_retail_pause_windows_are_eligible_but_intros_and_exits_are_not(self):
  self.hello();self.lib.next(0x80000001);self.lib.ack(1,0,0x80000001)
  for state in (4,5,11):
   self.lib.state(state);self.lib.publish(1);self.assertEqual(self.lib.permit(4),1,state)
  for state in (0,1,2,3,9,12):
   self.lib.state(state);self.lib.publish(1);self.assertEqual(self.lib.permit(4),0,state)
 def test_cleanup_states_publish_only_safe_offline_grants(self):
  for phase in (7,8):
   self.setUp();self.hello();self.lib.next(0x80000001);self.lib.ack(phase,0,0x80000001)
   self.lib.publish(1);self.assertEqual(self.lib.permit(4),1)
   self.lib.unsafe(2);self.lib.publish(1);self.assertEqual(self.lib.permit(4),0)
 def test_revoke_is_published_even_after_stage_aram_readiness_drops(self):
  self.hello();self.lib.next(0x80000001);self.lib.ack(1,0,0x80000001);self.lib.publish(1);self.assertEqual(self.lib.permit(4),1)
  sequence=self.lib.permit(3);self.lib.dropAram();self.lib.revoke()
  self.assertEqual(self.lib.permit(4),0);self.assertGreater(self.lib.permit(3),sequence)


if __name__=='__main__':unittest.main()
