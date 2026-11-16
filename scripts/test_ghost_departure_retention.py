"""Explicit partial Save and abandoned departures have different ownership intent."""
from pathlib import Path
import ctypes as C,os,subprocess,tempfile,unittest
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class DepartureRetentionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='departure-retention-');cls.addClassCleanup(cls.tmp.cleanup);d=Path(cls.tmp.name)
  src=(ROOT/'src/ghost.cpp').read_text();body=function(src,'prepareStreamDeparture')
  code=r"""
struct Track{bool valid,completed;unsigned count;}sRecord;
enum{CLOCK_ACTIVE,CLOCK_FINISHED,CLOCK_WAIT_STAGE};static int sClockPhase,finished,cancelled;static bool capturing;
namespace GhostRecording{bool capturing(){return ::capturing;}void cancelActive(){++cancelled;}}
void finishStreamRecord(const Track&){++finished;}
"""+body+r"""
extern "C" __declspec(dllexport) unsigned run(unsigned flags,unsigned clock,unsigned count,bool keep){
 sRecord={bool(flags&1),bool(flags&2),count};capturing=flags&4;sClockPhase=clock;finished=cancelled=0;
 prepareStreamDeparture(keep);return finished|(cancelled<<8);
}
"""
  (d/'test.cpp').write_text(code);env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2',str(d/'test.cpp'),'-o',str(d/'test.dll')],check=True,env=env)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.lib.run.argtypes=[C.c_uint,C.c_uint,C.c_uint,C.c_bool];cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_reset_discards_unfinished_attempt(self):self.assertEqual(self.lib.run(5,0,100,False),256)
 def test_explicit_save_preserves_partial_capture(self):self.assertEqual(self.lib.run(5,0,100,True),1)
 def test_completed_capture_is_retained_on_departure(self):self.assertEqual(self.lib.run(7,1,100,False),1)
 def test_previous_completed_metadata_is_not_used_for_new_intro(self):self.assertEqual(self.lib.run(7,2,100,False),256)
 def test_no_capture_and_empty_capture_do_not_finalize_stale_data(self):
  self.assertEqual(self.lib.run(3,1,100,False),0)
  self.assertEqual(self.lib.run(4,0,0,False),256)
if __name__=='__main__':unittest.main()
