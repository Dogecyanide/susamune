"""Keep JP1.0 available while retaining the explicit JP1.1 refusal."""
from pathlib import Path
import ctypes as C,subprocess,tempfile,unittest
from test_iling_attempt_lifecycle import function
ROOT=Path(__file__).resolve().parents[1]
class RevisionWarningTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='ms-revision-');cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  body=function((ROOT/'launcher/loader/source/SusamuneMod.c').read_text(),'SusamuneDiscRevisionWarning')
  (d/'test.c').write_text('#define MOONSHINE_MEMORY_MONITOR_ONLY 0\n#define NULL 0\ntypedef unsigned int u32;typedef unsigned char u8;\n__declspec(dllexport) '+body.strip())
  cmd=[str(ROOT/'toolchain/clang.exe'),'--target=x86_64-pc-windows-msvc','-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry',str(d/'test.c'),'-o',str(d/'test.dll')]
  r=subprocess.run(cmd,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(d/'test.dll'));cls.lib.SusamuneDiscRevisionWarning.argtypes=[C.c_uint,C.c_ubyte];cls.lib.SusamuneDiscRevisionWarning.restype=C.c_char_p
  cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_supported_regions_are_available(self):
  for game in (0x474d534a,0x474d5345,0x474d5350):self.assertIsNone(self.lib.SusamuneDiscRevisionWarning(game,0))
 def test_jp_revision_11_retains_clear_warning(self):self.assertIn(b'JP Version 1.1',self.lib.SusamuneDiscRevisionWarning(0x474d534a,1))
if __name__=='__main__':unittest.main()
