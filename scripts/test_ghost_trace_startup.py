"""Exercise production startup/cancellation control before the stage owns ARAM."""
from pathlib import Path
import os,re,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
def function(source,name):
 start=re.search(r'(?:void|bool) '+name+r'\([^;{}]*\)\s*\{',source).start();brace=source.index('{',start);depth=1;end=brace+1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
class TraceStartupTests(unittest.TestCase):
 def test_boot_waits_for_memory_and_only_cancels_a_live_attempt(self):
  source=(ROOT/'src/ghost_trace.cpp').read_text(encoding='utf-8')
  stage=source[source.index('struct StageStart {'):source.index('\nstatic_assert(sizeof(TFlagManager)')]
  state=source[source.index('struct State {'):source.index('\nstruct Actor {')]
  prefix='''#include <cstring>
#include <cstdio>
#include "susamune/ghost_trace.h"
struct TMarioGamePad {unsigned char bytes[240];};struct TMarioControllerWork {unsigned char bytes[36];};
struct ContactSample {unsigned role,pointer,valid,reserved;unsigned char triangle[0x48];};struct CameraSample {unsigned pointer,mode,child,valid;unsigned char interpolation[0x48];};
namespace GhostSimulation {struct Snapshot {unsigned char bytes[64];};}
namespace GhostTraceHooks {bool active=false,allowed=true;bool setActive(bool value){active=value;return allowed;}}
namespace GhostMemory {bool granted=true,owned=false;bool admitted(){return granted;}bool ready(){return granted&&owned;}}
struct Menu {void toast(const char*){}};Menu *gMenu=nullptr;
typedef int s32;
struct Timer {unsigned serial=1;bool ready=true;unsigned attemptSerial(){return serial;}bool currentQf(s32*q){*q=0;return ready;}} gQFTTimer;
namespace GhostStageContext {struct Sample {unsigned generation;};unsigned serial=4;bool valid=true;unsigned generation(){return valid?serial:0;}bool sample(Sample*p){p->generation=serial;return valid;}}
void flushRandom(){} void flushOrdinaryFinish(){}
void checkpointPoll(){} unsigned checkpointBoundary(){return ~0u;}
bool issueCheckpointFence(){return false;} bool sourcePinned(){return false;} bool forkBlocksCapture(){return false;}
namespace GhostWorldRuntime {bool hooksActive(){return false;}}
void DCInvalidateRange(void*,unsigned){} void DCStoreRange(void*,unsigned){}
'''+stage+'\n'+state+'''
State s{};bool bootReady;volatile MsTraceMailbox mailbox{};
unsigned char buffers[2][MS_TRACE_BUFFER_BYTES];unsigned char *buffer(unsigned n){return buffers[n];}
'''
  functions='\n'.join(function(source,n) for n in ('poll','command','seal','stop','beginAttempt','sameAttempt','service','reset','init','recording','stageArmed'))
  stage_setup=function(source,'stageSetup');stage_setup=stage_setup[:stage_setup.index('    StageStart &sample=')]+ '}\n'
  frame=function(source,'frame');frame=frame[:frame.index('    const unsigned before=OSGetTick();')]+ '}\n'
  frame=frame.replace('void frame(unsigned *worldScratch,unsigned worldSlots)', 'void frame(unsigned *worldScratch=nullptr,unsigned worldSlots=0)')
  functions+=stage_setup
  main='''
#define CHECK(c) do {if(!(c)){std::fprintf(stderr,"Failed line %d: %s\\n",__LINE__,#c);return 1;}}while(0)
int main(){
 mailbox.response.magic=MS_TRACE_MAGIC;mailbox.response.version=MS_TRACE_VERSION-1;mailbox.response.nonce=42;
 init();CHECK(!bootReady);frame();CHECK(mailbox.request.sequence==0);
 mailbox.response.version=MS_TRACE_VERSION;
 init();CHECK(bootReady);for(unsigned i=0;i<300;++i)frame();
 CHECK(mailbox.request.sequence==0);CHECK(s.ending==0);CHECK(s.error==0);
 GhostMemory::owned=true;frame();CHECK(mailbox.request.sequence==0);
 s.run=7;s.next=1;s.response.nonce=42;command(MS_TRACE_START);
 mailbox.response.ackRequest=1;mailbox.response.phase=MS_TRACE_RECORDING;
 frame();CHECK(s.attempt==gQFTTimer.serial);CHECK(mailbox.request.operation==MS_TRACE_START);
 GhostMemory::owned=false;frame();CHECK(mailbox.request.operation==MS_TRACE_DISCARD);CHECK(mailbox.request.run==7);
 unsigned sequence=mailbox.request.sequence;for(unsigned i=0;i<300;++i)frame();CHECK(mailbox.request.sequence==sequence);
 mailbox.response.ackRequest=sequence;mailbox.response.phase=MS_TRACE_DISCARDED;frame();
 CHECK(s.used[0]+s.used[1]==0);GhostMemory::owned=true;frame();CHECK(mailbox.request.sequence==sequence);
 mailbox.request.run=9;mailbox.response.phase=MS_TRACE_RECORDING;init();
 CHECK(mailbox.request.operation==MS_TRACE_DISCARD&&mailbox.request.run==9);
 // Starting during an intro adopts exactly one timer start in that stage.
 mailbox.response.ackRequest=s.request;s.ending=0;s.frame=1;s.command=MS_TRACE_START;s.run=9;s.response.phase=MS_TRACE_RECORDING;
 mailbox.response.phase=MS_TRACE_RECORDING;gQFTTimer.ready=false;beginAttempt();
 CHECK(s.introStage==4);++gQFTTimer.serial;gQFTTimer.ready=true;frame();
 CHECK(s.command==MS_TRACE_START&&s.introStage==0&&s.attempt==gQFTTimer.serial);
 ++gQFTTimer.serial;frame();CHECK(s.command==MS_TRACE_DISCARD);
 // A restart during the intro has a new stage generation and must still discard.
 mailbox.response.ackRequest=s.request;s.ending=0;s.command=MS_TRACE_START;gQFTTimer.ready=false;beginAttempt();
 ++GhostStageContext::serial;++gQFTTimer.serial;frame();CHECK(s.command==MS_TRACE_DISCARD);
 // Armed capture must stay inactive through the departing stage.
 s.ending=0;s.command=MS_TRACE_START;s.response.phase=MS_TRACE_RECORDING;
 s.waitingStage=true;s.scene=0x1d00;s.request=17;mailbox.response.ackRequest=17;
 mailbox.response.phase=MS_TRACE_RECORDING;s.frame=0;GhostTraceHooks::active=false;
 CHECK(!recording());CHECK(stageArmed());
 stageSetup(2,4,8);CHECK(s.waitingStage&&!GhostTraceHooks::active);
 stageSetup(0x1d,0,9);CHECK(!s.waitingStage&&recording()&&GhostTraceHooks::active);
 CHECK(s.introStage==9&&s.attempt==gQFTTimer.serial);
 // No resource capture may be advertised if storage was not ready in time.
 s.waitingStage=true;s.ending=0;s.error=0;s.request=18;GhostTraceHooks::active=false;
 stageSetup(0x1d,0,10);CHECK(s.ending==MS_TRACE_KEEP&&s.error==MS_TRACE_PROTOCOL);
 CHECK(!recording()&&!GhostTraceHooks::active);
 std::puts("Boot, intro, reset and armed pre-resource capture ownership passed.");
}
'''
  with tempfile.TemporaryDirectory(prefix='trace-startup-') as temp:
   folder=Path(temp);env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
   for legacy in (False,True):
    code=prefix+functions+frame+main
    if legacy:
     code=code.replace('!GhostMemory::ready()&&s.run&&s.command==MS_TRACE_START','!GhostMemory::ready()').replace('s.ending==MS_TRACE_DISCARD&&s.run&&s.command!=MS_TRACE_DISCARD','s.ending==MS_TRACE_DISCARD&&s.command!=MS_TRACE_DISCARD')
    cpp=folder/'test.cpp';exe=folder/'test.exe';cpp.write_text(code,encoding='utf-8')
    compile_result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-I',str(ROOT/'include'),str(cpp),'-o',str(exe)],env=env,capture_output=True,text=True)
    self.assertEqual(compile_result.returncode,0,compile_result.stderr)
    result=subprocess.run([str(exe)],env=env,capture_output=True,text=True)
    if legacy:self.assertNotEqual(result.returncode,0,'Must reproduce r5 startup fault')
    else:self.assertEqual(result.returncode,0,result.stdout+result.stderr);print(result.stdout,end='')
if __name__=='__main__':unittest.main()
