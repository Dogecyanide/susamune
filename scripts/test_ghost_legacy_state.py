"""Old savestate ghost metadata is checked but never supplies writable banks."""
import ctypes as C
import os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r"""
#include "src/ghost_legacy_state.cpp"
#define API extern "C" __declspec(dllexport)
API void make(void*out,unsigned version){
 using namespace GhostLegacyState;
 Ghost::SavestateData data={};SavedPrefix old={};old.magic=kSavedPrefixMagic;old.capturedQf=1200;
 old.track.count=123;old.track.segmentCount=2;old.track.inputCount=60;old.track.formatVersion=version;
 old.track.startQf=0;old.track.endQf=1180;old.track.resultQf=0xffffffffu;old.track.runFlags=8;
 old.track.area=3;old.track.episode=2;old.track.parentEpisode=2;old.track.routeParentArea=255;
 old.track.valid=1;old.clock={10,1200,20,1,{0,0,0}};old.serial=10;old.lastSampleQf=1180;old.phase=2;old.flags=1;
 __builtin_memcpy(&data,&old,sizeof(old));
 if(version>=8){data.words[126]=272;data.words[127]=SUSAMUNE_GHOST_CAMERA_MAGIC;}
 if(version>=10){data.words[124]=128;data.words[125]=SUSAMUNE_GHOST_CONTEXT_MAGIC;}
 __builtin_memcpy(out,&data,sizeof(data));
}
API int spans(void*raw,unsigned*out){
 StateCodec::WriteSpan destinations[Ghost::kSavestateSpanCount];
 if(!GhostLegacyState::restoreSpans(*static_cast<Ghost::SavestateData*>(raw),destinations))return 0;
 for(unsigned i=0;i<5;++i){out[i]=destinations[i].size;if(destinations[i].size&&!StateCodec::isDiscardSpan(destinations[i]))return -1;}
 return 1;
}
API unsigned stride(unsigned version){return SusamuneGhostInputStride(version);}
API void corrupt(void*raw,unsigned field){
 using namespace GhostLegacyState;auto*p=static_cast<Ghost::SavestateData*>(raw);auto&s=*reinterpret_cast<SavedPrefix*>(raw);
 switch(field){case 0:s.track.samples=0x91780000;break;case 1:s.track.count=~0u;break;case 2:s.track.segmentCount=65;break;
 case 3:s.track.inputCount=~0u;break;case 4:s.clock.ready=2;break;case 5:s.clock.omittedQf=1201;break;case 6:p->words[127]^=1;break;
 case 7:s.track.completed=1;break;case 8:s.track.routeFlags=0x80;break;case 9:s.track.formatVersion=99;break;}
}
"""
class LegacyStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='msgt-legacy-state-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  (d/'fixture.cpp').write_text(FIXTURE,encoding='utf-8');env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
  result=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-shared','-static','-std=c++17','-O2','-I',str(ROOT),'-I',str(ROOT/'include'),'-I',str(ROOT/'include/JSystem'),str(d/'fixture.cpp'),'-o',str(d/'fixture.dll')],env=env,capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  cls.lib=C.CDLL(str(d/'fixture.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.make.argtypes=[C.c_void_p,C.c_uint];cls.lib.spans.argtypes=[C.c_void_p,C.POINTER(C.c_uint)];cls.lib.corrupt.argtypes=[C.c_void_p,C.c_uint]
 def test_each_legacy_format_yields_only_bounded_discard_spans(self):
  for version in range(4,11):
   raw=C.create_string_buffer(512);out=(C.c_uint*5)();self.lib.make(raw,version);self.assertEqual(self.lib.spans(raw,out),1)
   self.assertEqual(list(out),[123*16,64,60*self.lib.stride(version),272 if version>=8 else 0,128 if version>=10 else 0])
 def test_invalid_pointers_counts_clock_and_camera_are_refused(self):
  for field in range(10):
   raw=C.create_string_buffer(512);out=(C.c_uint*5)();self.lib.make(raw,9);self.lib.corrupt(raw,field);self.assertEqual(self.lib.spans(raw,out),0,field)
 def test_empty_metadata_restores_no_sidecar_bytes(self):
  raw=C.create_string_buffer(512);out=(C.c_uint*5)();self.assertEqual(self.lib.spans(raw,out),1);self.assertEqual(list(out),[0]*5)
  raw[511]=b'\1';self.assertEqual(self.lib.spans(raw,out),0)
if __name__=='__main__':unittest.main()
