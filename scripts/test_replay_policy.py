"""Playback eligibility is independent of the source run's TAS classification."""
from pathlib import Path
import ctypes as C,os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class ReplayPolicyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='replay-policy-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  (d/'test.cpp').write_text('#include "susamune/replay_policy.h"\nstatic ReplayPolicy::State s;\nextern "C" {\n__declspec(dllexport) void begin(unsigned tas){ReplayPolicy::begin(s,tas);}\n__declspec(dllexport) void stop(){ReplayPolicy::stop(s);}\n__declspec(dllexport) void stage(unsigned active){ReplayPolicy::stageEntry(s,active);}\n__declspec(dllexport) unsigned playing(){return ReplayPolicy::playing(s);}\n__declspec(dllexport) unsigned blocked(){return ReplayPolicy::blocksResults(s);}\n__declspec(dllexport) unsigned tas(){return ReplayPolicy::sourceTas(s);}\n__declspec(dllexport) unsigned tick(){return ReplayPolicy::advance(s);}\n__declspec(dllexport) void paint(){ReplayPolicy::paint(s);}\n__declspec(dllexport) void nearWrap(){s.frame=s.painted=0xfffffffeu;}\n}\n')
  env=dict(os.environ);env['PATH']='C:/msys64/mingw64/bin;'+env.get('PATH','');r=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-O2','-I',str(ROOT/'include'),str(d/'test.cpp'),'-o',str(d/'test.dll')],env=env,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def setUp(self):self.lib.stage(0)
 def test_clean_replay_blocks_awards_without_tas_label(self):
  self.lib.begin(0);self.assertEqual(self.lib.blocked(),1);self.assertEqual(self.lib.tas(),0)
 def test_tas_replay_is_marked_and_blocks_awards(self):
  self.lib.begin(1);self.assertEqual(self.lib.blocked(),1);self.assertEqual(self.lib.tas(),1)
 def test_stop_retains_derived_attempt_until_fresh_entry(self):
  self.lib.begin(0);self.lib.stop();self.assertTrue(self.lib.blocked());self.assertTrue(self.lib.tick());self.lib.stage(0);self.assertFalse(self.lib.blocked())
 def test_stopping_hides_replay_marker_but_keeps_result_protection(self):
  self.lib.begin(0);self.assertTrue(self.lib.playing());self.lib.stop()
  self.assertFalse(self.lib.playing());self.assertTrue(self.lib.blocked());self.assertFalse(self.lib.tas())
 def test_replay_transition_keeps_marker_and_eligibility(self):
  self.lib.begin(1);self.lib.stage(1);self.assertTrue(self.lib.blocked());self.assertTrue(self.lib.tas())
 def test_new_clean_replay_does_not_inherit_previous_source_tas(self):
  self.lib.begin(1);self.lib.stop();self.lib.begin(0);self.assertFalse(self.lib.tas());self.assertTrue(self.lib.blocked())
 def test_missing_marker_fails_closed_after_grace(self):
  self.lib.begin(0);self.assertTrue(self.lib.tick());self.assertTrue(self.lib.tick());self.assertFalse(self.lib.tick());self.assertTrue(self.lib.blocked())
 def test_drawn_marker_keeps_playback_live(self):
  self.lib.begin(0)
  for _ in range(100):self.assertTrue(self.lib.tick());self.lib.paint()
 def test_draw_counter_wrap_preserves_health(self):
  self.lib.begin(0);self.lib.nearWrap()
  for _ in range(4):self.assertTrue(self.lib.tick());self.lib.paint()
if __name__=='__main__':unittest.main()
