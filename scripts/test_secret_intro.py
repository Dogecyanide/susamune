"""Run the optional skip against the audited native additional-movie decision."""
import ctypes as C
from pathlib import Path
import ast,re,subprocess,tempfile,unittest
import patches
ROOT=Path(__file__).resolve().parents[1]
# Retail decision with only local header field spellings adapted.
RETAIL_DECISION='bool TApplication::checkAdditionalMovie()\n{\n\tbool result = false;\n\n\tconst TGameSequence& currArea = gpApplication.mCurrentScene;\n\n\tu8 uVar1 = SMS_getShineIDofExStage(currArea.mAreaID);\n\tif (uVar1 != 0xFF) {\n\t\tif (!TFlagManager::getInstance()->getShineFlag(uVar1)) {\n\t\t\tif (!TFlagManager::getInstance()->getBool(0x3000D)) {\n\t\t\t\tmCutSceneID = 5;\n\t\t\t\tTFlagManager::getInstance()->setBool(true, 0x3000D);\n\t\t\t\tresult = true;\n\t\t\t}\n\t\t}\n\t} else {\n\t\tswitch (currArea.mAreaID) {\n\t\tcase 0:\n\t\t\tif (currArea.mEpisodeID == 0) {\n\t\t\t\tif (!TFlagManager::getInstance()->getBool(0x30009)) {\n\t\t\t\t\tmCutSceneID = 1;\n\t\t\t\t\tTFlagManager::getInstance()->setBool(true, 0x30009);\n\t\t\t\t\tresult = true;\n\t\t\t\t}\n\t\t\t}\n\t\t\tbreak;\n\n\t\tcase 1:\n\t\t\tif (currArea.mEpisodeID == 0) {\n\t\t\t\tif (!TFlagManager::getInstance()->getBool(0x3000B)) {\n\t\t\t\t\tmCutSceneID = 3;\n\t\t\t\t\tTFlagManager::getInstance()->setBool(true, 0x3000B);\n\t\t\t\t\tresult = true;\n\t\t\t\t}\n\t\t\t} else if (currArea.mEpisodeID == 1) {\n\t\t\t\tif (!TFlagManager::getInstance()->getBool(0x3000C)) {\n\t\t\t\t\tmCutSceneID = 4;\n\t\t\t\t\tTFlagManager::getInstance()->setBool(true, 0x3000C);\n\t\t\t\t\tresult = true;\n\t\t\t\t}\n\t\t\t}\n\t\t\tbreak;\n\n\t\tcase 8:\n\t\t\tif (currArea.mEpisodeID == 2) {\n\t\t\t\tif (!TFlagManager::getInstance()->getBool(0x3000D)) {\n\t\t\t\t\tmCutSceneID = 5;\n\t\t\t\t\tTFlagManager::getInstance()->setBool(true, 0x3000D);\n\t\t\t\t\tresult = true;\n\t\t\t\t}\n\t\t\t}\n\t\t\tbreak;\n\t\t}\n\t}\n\n\treturn result;\n}\n'
SECRET_TABLE=[255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 55, 20, 255, 255, 255, 255, 255, 255, 255, 43, 35, 64, 255, 255, 255, 5, 2, 13, 255, 31, 41, 255]

FIXTURE=r"""
#include "susamune/settings.hxx"
extern "C" void*memset(void*d,int v,__SIZE_TYPE__ n){volatile u8*p=(volatile u8*)d;while(n--)*p++=(u8)v;return d;}
Settings settings;Settings &gSettings=settings;
void Settings::set(SettingId id,u8 value){mValues[id]=value;}
struct TGameSequence{u8 mAreaID,mEpisodeID;};
struct TApplication{TGameSequence mCurrentScene;u32 mCutSceneID;bool checkAdditionalMovie();}gpApplication;
struct TFlagManager{bool shines[256],seen[5];unsigned writes;
static TFlagManager*getInstance();bool getShineFlag(unsigned i){return shines[i];}
bool getBool(unsigned id){return seen[id-0x30009];}
void setBool(bool v,unsigned id){seen[id-0x30009]=v;++writes;}}flags;
TFlagManager*TFlagManager::getInstance(){return &flags;}
u8 SMS_getShineIDofExStage(u8 a){static const u8 table[32]={TABLE};return a>0x14&&a<0x35?table[a-0x15]:255;}
#define SUSAMUNE_MEM1_ADDR(j,u,p) (&SMS_getShineIDofExStage)
"""
BRIDGE=r"""
#define API extern "C" __declspec(dllexport)
API void reset(unsigned skip,unsigned area,unsigned ep,unsigned complete,unsigned seen){
gpApplication.mCurrentScene={(u8)area,(u8)ep};gpApplication.mCutSceneID=0x12345678;flags={};
unsigned shine=SMS_getShineIDofExStage(area);if(shine!=255)flags.shines[shine]=complete;
flags.seen[4]=seen;settings.set(SETTING_FMV_SKIPS,skip);}
API unsigned decide(unsigned hooked){return hooked?susamuneSecretIntroMovie(&gpApplication):gpApplication.checkAdditionalMovie();}
API void values(unsigned*out){out[0]=gpApplication.mCutSceneID;out[1]=0;for(unsigned i=0;i<5;++i)if(flags.seen[i])out[1]|=1<<i;
out[2]=flags.writes;out[3]=0;for(unsigned i=0;i<256;++i)if(flags.shines[i])out[3]+=i+1;
unsigned shine=SMS_getShineIDofExStage(gpApplication.mCurrentScene.mAreaID);out[4]=shine==255||flags.getShineFlag(shine);out[5]=settings.get(SETTING_FMV_SKIPS);}
API unsigned ordinal(){return SETTING_FMV_SKIPS;}
"""
class SecretIntroTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-secret-intro-');cls.addClassCleanup(cls.temp.cleanup)
  source=re.sub(r'^#include .*?$','',(ROOT/'src/secret_intro.cpp').read_text(),flags=re.M)
  code=FIXTURE.replace('TABLE',','.join(map(str,SECRET_TABLE)))+RETAIL_DECISION+source+BRIDGE;cls.libs=[]
  for trace in (0,1):
   p=Path(cls.temp.name)/f'fixture{trace}.cpp';p.write_text(code)
   r=subprocess.run([str(ROOT/'toolchain/clang++.exe'),'--target=x86_64-pc-windows-msvc','-shared','-nostdlib','-O2','-fuse-ld=lld','-Wl,/noentry',f'-DMOONSHINE_GHOST_TRACE={trace}','-I',str(ROOT/'include'),str(p),'-o',str(p.with_suffix('.dll'))],capture_output=True,text=True)
   if r.returncode:raise RuntimeError(r.stdout+r.stderr)
   lib=C.CDLL(str(p.with_suffix('.dll')));cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
   lib.reset.argtypes=[C.c_uint]*5;lib.values.argtypes=[C.POINTER(C.c_uint)];cls.libs.append(lib)
 def values(self,lib):
  data=(C.c_uint*6)();lib.values(data);return tuple(data)
 def run_case(self,lib,skip=0,area=0x28,ep=0,complete=0,seen=0,hook=1):
  lib.reset(skip,area,ep,complete,seen);result=lib.decide(hook);return (result,)+self.values(lib)
 def test_off_matches_retail_all_scenes_and_first_visit_states(self):
  for lib in self.libs:
   for a in range(0x3d):
    for e in (0,1,2):
     for c in (0,1):
      for s in (0,1):self.assertEqual(self.run_case(lib,0,a,e,c,s),self.run_case(lib,0,a,e,c,s,0))
 def test_on_changes_only_movie_result_for_first_native_secret_entries(self):
  for lib in self.libs:
   for a in range(0x3d):
    native=self.run_case(lib,area=a);on=self.run_case(lib,skip=2,area=a)
    secret=0x15<=a<0x35 and SECRET_TABLE[a-0x15]!=255
    self.assertEqual(on[0],0 if secret else native[0]);self.assertEqual(on[1:6],native[1:6]);self.assertEqual(on[6],2)
 def test_already_seen_and_red_coin_completed_modes_remain_native(self):
  for lib in self.libs:
   for c,s in ((0,1),(1,0),(1,1)):
    a=self.run_case(lib,skip=2,complete=c,seen=s);b=self.run_case(lib,complete=c,seen=s,hook=0)
    self.assertEqual(a[:6],b[:6])
 def test_pianta_three_and_other_story_movies_still_play(self):
  for lib in self.libs:
   for a,e,m in ((8,2,5),(0,0,1),(1,0,3),(1,1,4)):
    self.assertEqual(self.run_case(lib,skip=2,area=a,ep=e)[:2],(1,m))
 def test_native_seen_event_happens_once_and_fludd_is_still_removed(self):
  for lib in self.libs:
   self.assertEqual(self.run_case(lib,skip=2),(0,5,16,1,0,0,2));self.assertEqual(lib.decide(1),0)
   self.assertEqual(self.values(lib),(5,16,1,0,0,2))
   self.assertEqual(self.run_case(lib),(1,5,16,1,0,0,0));self.assertEqual(lib.decide(0),0)
   self.assertEqual(self.values(lib),(5,16,1,0,0,0))
 def test_existing_id_key_and_default_fmv_mode_are_preserved(self):
  for lib in self.libs:self.assertEqual(lib.ordinal(),5)
  rows=re.findall(r'X\((SETTING_[A-Z0-9_]+),\s*"[^"]+"\)',(ROOT/'include/susamune/settings_list.h').read_text())
  self.assertEqual(len(rows),174);self.assertEqual(rows[-1],'SETTING_NATIVE_TIMER_DECIMAL_SEPARATOR')
  self.assertIn('SCHOICE("Movie skips", 1, CHOICES_MOVIE_SKIPS, SETTING_CAT_QOL)',(ROOT/'src/settings_descs.inc').read_text())
  page=(ROOT/'src/menu.cpp').read_text().split('const u8 kGameplaySkipSettings[] = {',1)[1].split('};',1)[0];self.assertIn('SETTING_FMV_SKIPS',page)
 def test_original_enabled_mode_does_not_also_skip_theft(self):
  for lib in self.libs:
   self.assertEqual(self.run_case(lib,skip=1),(1,5,16,1,0,0,1))
 def test_new_choice_labels_have_stable_map_ordinals(self):
  source=(ROOT/'src/settings.cpp').read_text();part=source.split('const char kChoiceLabels[] =',1)[1].split(';',1)[0]
  labels=''.join(ast.literal_eval(v) for v in re.findall(r'"(?:[^"\\]|\\.)*"',part)).split('\0')
  self.assertEqual(labels[94:],['FMVs','FMVs and FLUDD theft'])
  self.assertIn('0, 94, 95, // movie skips',source)
  self.assertIn('188, 190, 193',source)
 def test_hook_targets_only_the_audited_regional_native_call(self):
  rows=[p for p in patches.patches if p.get('sym')=='susamuneSecretIntroMovie'];self.assertEqual(len(rows),1)
  for r,site,w,target in (('jp',0x800f9ea8,0x48000345,0x800fa1ec),('us',0x802a64a4,0x48000345,0x802a67e8),('pal',0x8029e3c4,0x4800037d,0x8029e740)):
   self.assertEqual(rows[0][r],site);self.assertEqual(site+(w&0x3fffffc),target)
  self.assertEqual(rows[0]['type'],patches.PatchType.BL)
if __name__=='__main__':unittest.main()
