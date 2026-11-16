"""Recorded scene admission for full-world Watch, independent of IL selection."""
import ctypes as C
import os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r"""
#include "susamune/ghost_replay_start.hxx"
#include <cstring>
#define API extern "C" __declspec(dllexport)
API unsigned destination(unsigned current,unsigned previous,unsigned variant,unsigned scenarios,unsigned corrupt) {
    GhostTraceDecode::StageStart s={};
    s.scene=current;s.current={static_cast<unsigned char>(current>>8),static_cast<unsigned char>(current),0};
    s.next=s.current;s.previous={static_cast<unsigned char>(previous>>8),static_cast<unsigned char>(previous),0};
    unsigned char image[896]={};image[0xdc]=variant>>24;image[0xdd]=variant>>16;image[0xde]=variant>>8;image[0xdf]=variant;
    if(corrupt==1)s.current.flags=1;
    if(corrupt==2)s.previous.flags=1;
    if(corrupt==3)s.next.flags=1;
    if(corrupt==4)++s.next.episode;
    if(corrupt==5)++s.scene;
    if(corrupt==6)image[0xf4]=1;
    LevelWarp::Dest from={0xff,0xff,0xff},to=from;
    if(!GhostReplayStart::destination(s,image,scenarios,from,to))return 0;
    return 0x80000000u|(unsigned(to.area)<<16)|(unsigned(to.episode)<<8)|to.gameInt3;
}
API unsigned source(unsigned previous) {
    GhostTraceDecode::StageStart s={};s.scene=0x700;s.current=s.next={7,0,0};
    s.previous={static_cast<unsigned char>(previous>>8),static_cast<unsigned char>(previous),0};
    unsigned char image[896]={};LevelWarp::Dest from={},to={};
    return GhostReplayStart::destination(s,image,8,from,to)?(unsigned(from.area)<<8)|from.episode:~0u;
}
"""
class ReplayStartTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-watch-start-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  (d/'fixture.cpp').write_text(FIXTURE,encoding='utf-8')
  env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-I',str(ROOT/'include'),'-I',str(ROOT/'include/JSystem'),str(d/'fixture.cpp'),str(ROOT/'src/ghost_trace_initial_flags.cpp'),str(ROOT/'src/ghost_replay_start.cpp'),'-o',str(d/'fixture.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.destination.argtypes=[C.c_uint]*5;cls.lib.destination.restype=cls.lib.source.restype=C.c_uint
 def test_recorded_hotel_variant_not_menu_choice(self):
  for variant in range(8):self.assertEqual(self.lib.destination(0x700,0x609,variant,8,0),0x80070000|variant)
 def test_recorded_previous_scene_keeps_entry_point(self):
  for previous in (0,0x109,0x500,0xd00,0x1600):self.assertEqual(self.lib.source(previous),previous)
 def test_self_source_captures_still_use_identical_destination(self):
  self.assertEqual(self.lib.destination(0xd00,0xd00,0,8,0),0x800d0000)
 def test_bad_scenes_or_flag_snapshot_never_produce_a_destination(self):
  for corrupt in range(1,7):self.assertEqual(self.lib.destination(0x700,0x600,3,8,corrupt),0)
  for current,previous in ((0x3d00,0x700),(0x700,0x3d00),(0x70a,0x700),(0x700,0x70a)):
   self.assertEqual(self.lib.destination(current,previous,0,8,0),0)
 def test_parent_episode_must_exist(self):
  for variant,scenarios in ((8,8),(0xffffffff,8),(0,0),(0,257)):
   self.assertEqual(self.lib.destination(0x700,0x600,variant,scenarios,0),0)
if __name__=='__main__':unittest.main()
