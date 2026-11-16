"""Exercise the real opaque Ghost wrappers with the real native crane cache API."""
import ctypes as C
from pathlib import Path
import re,unittest
from unittest.mock import patch
import test_ghost_savestate_prefix as prefix
import test_rng_trace_crane as crane
from test_ghost_tas_clock import function

ROOT=Path(__file__).resolve().parents[1]
BRIDGE=r'''
const u32 kSavedRngWord=124-RNG_CONTROL_SAVESTATE_DATA_WORDS;
using CacheOut=unsigned(*)(u32*,unsigned);using CacheIn=unsigned(*)(const u32*,unsigned);
static CacheOut cacheCapture;static CacheIn cacheValid,cacheRestore;static void(*cacheLegacy)();static unsigned(*cacheRequired)();
bool rngControlCaptureSavestate(u32*p,unsigned n){return cacheCapture&&cacheCapture(p,n);}
bool rngControlValidateSavestate(const u32*p,unsigned n){return cacheValid&&cacheValid(p,n);}
bool rngControlRestoreSavestate(const u32*p,unsigned n){return cacheRestore&&cacheRestore(p,n);}
void rngControlRestoreLegacySavestate(){if(cacheLegacy)cacheLegacy();}
bool rngControlSavestateRequired(){return cacheRequired&&cacheRequired();}
'''
APIS=r'''
API void cacheBind(void*a,void*b,void*c,void*d,void*e){using namespace Ghost;cacheCapture=(CacheOut)a;cacheValid=(CacheIn)b;cacheRestore=(CacheIn)c;cacheLegacy=(void(*)())d;cacheRequired=(unsigned(*)())e;}
API void* stateWords(unsigned slot){return Ghost::states[slot].words;}
API int rngStatus(unsigned slot){return Ghost::savestateRngStatus(Ghost::states[slot]);}
API int rngRestore(unsigned slot){return Ghost::restoreSavestateRng(Ghost::states[slot]);}
API void format10(){Ghost::sRecord.formatVersion=SUSAMUNE_GHOST_FILE_VERSION_V10;}
API unsigned tailWord(){return Ghost::kSavedRngWord;}
'''
NATIVE_API=r'''
API unsigned controlActor(unsigned actor,unsigned vertical){seenRetail=0;if(vertical)susamuneCraneUpDownControl((void*)(__UINTPTR_TYPE__)actor);else susamuneCraneRotYControl((void*)(__UINTPTR_TYPE__)actor);unsigned bits;__builtin_memcpy(&bits,&seenRetail,4);return bits;}
'''
RAM_ENV=r'''
namespace GhostTrace {struct CheckpointSnapshot {unsigned magic;};}
namespace GhostRecording {static unsigned fastCalls;int prepareFastCheckpointLoad(const GhostTrace::CheckpointSnapshot&,unsigned,unsigned){++fastCalls;return 1;}}
struct SavestateHeader {unsigned magic,version,game_version,heap_addr,area_id,episode_id;};
struct StoredState {SavestateHeader header;unsigned generation,metadataTag,parentEpisode;Ghost::SavestateData ghost;GhostTrace::CheckpointSnapshot trace;};
struct SavestateManager {enum{kSlotCount=3};};
struct Card {int getLastStatus(){return 0;}};static Card*gpCardManager;
struct App {void*mCurrentHeap;struct{unsigned mAreaID,mEpisodeID;}mCurrentScene;}gpApplication;
static StoredState sSlots[3];const unsigned kSnapshotMagic=0x53555341,kSnapshotVersion=19,SUSAMUNE_GAME_VERSION=3;const int CARD_ERROR_BUSY=-1;
bool validStore(){return true;}bool inLoadTransition(){return false;}unsigned parentEpisode(){return 2;}
unsigned metadataTag(const StoredState&s){return s.metadataTag;}
'''
RAM_API=r'''
API int ramReady(unsigned slot){StoredState&s=sSlots[slot];s.ghost=Ghost::states[slot];s.generation=11;s.metadataTag=123;s.parentEpisode=2;s.header={kSnapshotMagic,kSnapshotVersion,SUSAMUNE_GAME_VERSION,0x81000000,3,2};gpApplication.mCurrentHeap=(void*)(__UINTPTR_TYPE__)0x81000000;gpApplication.mCurrentScene={3,2};GhostRecording::fastCalls=0;return prepareRamCheckpointLoad(slot,11);}
API unsigned fastPrepareCalls(){return GhostRecording::fastCalls;}
'''

class GhostRngTailTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  ghost=(ROOT/'src/ghost.cpp').read_text();state=(ROOT/'src/savestate.cpp').read_text();old_function=prefix.function;old_run=prefix.subprocess.run
  def extracted(text,signature):
   result=old_function(text,signature)
   if signature=='bool decodeSavedPrefix(':
    result=re.search(r'enum \{ RNG_CONTROL_SAVESTATE_MAGIC.*?\};',(ROOT/'include/susamune/rng_control.hxx').read_text(),re.S).group(0)+'\n'+BRIDGE+function(ghost,'bool savedRngValid(')+'\n'+result
   if signature=='void restoreSavestate(':
    result=function(ghost,'int savestateRngStatus(')+'\n'+function(ghost,'bool restoreSavestateRng(')+'\n'+result
   return result
  def compile_fixture(args,*a,**kw):
   for arg in args if isinstance(args,list) else []:
    p=Path(arg)
    if p.suffix=='.cpp' and p.exists() and p.name=='prefix.cpp':
     text=p.read_text().replace('u32 prefixSize(const void*){return 0;}','u32 prefixSize(const void*){return 32;}')
     p.write_text(text+APIS+RAM_ENV+function(state,'int prepareRamCheckpointLoad(')+'\n'+RAM_API)
    elif p.suffix=='.cpp' and p.exists() and re.fullmatch(r'crane[012]\.cpp',p.name):p.write_text(p.read_text()+NATIVE_API)
   return old_run(args,*a,**kw)
  cls.native_type=type('NativeCacheFixture',(unittest.TestCase,),{})
  with patch.object(prefix,'function',extracted),patch.object(prefix.subprocess,'run',compile_fixture):
   crane.CraneTraceTests.setUpClass.__func__(cls.native_type);cls.addClassCleanup(cls.native_type.doClassCleanups)
   prefix.GhostSavestatePrefixTests.setUpClass.__func__(cls)
  cls.native=crane.CraneTraceTests('runTest');cls.native.libs=cls.native_type.libs
  cls.lib.cacheBind.argtypes=[C.c_void_p]*5;cls.lib.stateWords.argtypes=[C.c_uint];cls.lib.stateWords.restype=C.POINTER(C.c_uint)
  for name in ('rngStatus','rngRestore','ramReady'):getattr(cls.lib,name).argtypes=[C.c_uint];getattr(cls.lib,name).restype=C.c_int
  cls.lib.fastPrepareCalls.restype=C.c_uint
  for lib in cls.native.libs:lib.controlActor.argtypes=[C.c_uint,C.c_uint];lib.controlActor.restype=C.c_uint
  n=cls.native.libs[0];cls.lib.cacheBind(*(C.cast(getattr(n,name),C.c_void_p) for name in ('saveCache','validCache','restoreCache','legacyLoad','cacheRequired')))
 def setUp(self):crane.CraneTraceTests.setUp(self.native);self.lib.reset();self.n=self.native.libs[0]
 def words(self,slot=0):return self.lib.stateWords(slot)
 def save(self,slot=0,empty=True):
  if empty:self.lib.mode(3)
  self.assertEqual(self.lib.capture(slot),1);return tuple(self.words(slot)[:128])
 def clear_tail(self,slot=0):
  for i in range(106,124):self.words(slot)[i]=0
 def test_zero_prefix_captures_only_bounded_rng_tail_and_no_legacy_spans(self):
  self.native.actor(0,2,saved=True,speed=0x3d4ccccd);out=self.save()
  self.assertEqual(self.lib.tailWord(),106);self.assertEqual(out[:106],(0,)*106);self.assertEqual(out[106:108],(0x43524e47,1));self.assertEqual(out[124:],(0,)*4)
  self.assertEqual(self.lib.destinations(0),1);self.assertEqual([self.lib.destinationSize(i) for i in range(5)],[0]*5);self.assertEqual(self.lib.rngStatus(0),1)
 def test_sgpf_and_camera_context_metadata_are_preserved_by_five_span_capture(self):
  self.native.actor(0,1,saved=True);self.lib.format10();self.lib.frame(10,1,0)
  self.assertEqual(self.lib.captureCore(1),1);core=tuple(self.words(1)[:128]);out=self.save(empty=False)
  self.assertEqual(out[0],0x53475046);self.assertEqual(out[:106],core[:106]);self.assertEqual(out[124:],core[124:]);self.assertGreaterEqual(out[124],32);self.assertGreaterEqual(out[126],32)
  self.assertEqual(self.lib.destinations(0),1);self.assertGreaterEqual(self.lib.destinationSize(3),32);self.assertGreaterEqual(self.lib.destinationSize(4),32)
 def test_malformed_tail_is_refused_before_any_restore_span_or_cache_mutation(self):
  self.native.actor(0,0,saved=True);original=self.save();before=self.n.stateHash()
  for at,value in ((106,0x12345678),(107,2),(108,0x81000001),(123,0)):
   for i,v in enumerate(original):self.words()[i]=v
   self.words()[at]=value
   self.assertEqual(self.lib.destinations(0),0);self.assertEqual(self.lib.rngStatus(0),-1);self.assertEqual([self.lib.destinationSize(i) for i in range(5)],[0]*5);self.assertEqual(self.n.stateHash(),before)
  for i,v in enumerate(original):self.words()[i]=v
  self.words()[106]=0;self.assertEqual(self.lib.destinations(0),0)
 def test_preflight_is_structural_and_cache_restore_happens_after_heap_restore(self):
  a=0x3d4ccccd;b=0x3ecccccd;p=self.native.actor(0,2,saved=True,speed=a);self.native.put(p+0x144,a);native=C.string_at(p,0x14c);self.save()
  self.n.reset();self.native.actor(0,2,saved=True,speed=b);self.n.owner(2,p,0x7111,1,b);self.native.put(p+0x144,b);before=self.n.stateHash()
  self.assertEqual(self.lib.rngStatus(0),1);self.assertEqual(self.n.stateHash(),before)
  C.memmove(p,native,len(native));self.assertEqual(self.lib.rngRestore(0),1);self.assertEqual(self.n.row(2,1),a);self.assertEqual(self.n.row(2,2),0x11234)
  self.n.choice(0);self.assertEqual(self.n.controlActor(p,0),a)
 def test_legacy_ricco_ram_uses_practice_fallback_without_guessing_or_stale_controls(self):
  p=self.native.actor(0,2,saved=True,speed=0x3ecccccd);self.save();self.clear_tail();native=C.string_at(p,0x14c)
  self.assertEqual(self.lib.rngStatus(0),0);self.assertEqual(self.lib.ramReady(0),0);self.assertEqual(self.lib.fastPrepareCalls(),0)
  self.assertEqual(self.lib.rngRestore(0),0);self.assertEqual(self.native.rows(0),((0,0,0xffff),)*5);self.assertEqual(C.string_at(p,0x14c),native)
  speed=C.c_uint.from_address(p+0x144).value;self.n.choice(0);self.assertEqual(self.n.controlActor(p,0),speed)
 def test_legacy_sgpf_and_nonricco_zero_remain_decodable(self):
  self.lib.format10();self.lib.frame(10,1,0);self.save(empty=False);self.clear_tail();self.assertEqual(self.lib.destinations(0),1);self.assertEqual(self.lib.rngStatus(0),0)
  self.n.ready(1,1,1,1);self.assertEqual(self.lib.rngStatus(0),1);self.assertEqual(self.lib.ramReady(0),1);self.assertEqual(self.lib.fastPrepareCalls(),1)
 def test_post_restore_bad_owner_clears_all_rows_and_refuses_continuation_cache(self):
  for i in range(5):self.native.actor(0,i,saved=i<3)
  self.save();C.c_ushort.from_address(crane.BASE+0x4000+8).value=0x09ce
  self.assertEqual(self.lib.rngStatus(0),1);self.assertEqual(self.lib.rngRestore(0),0);self.assertEqual(self.native.rows(0),((0,0,0xffff),)*5)

if __name__=='__main__':unittest.main()
