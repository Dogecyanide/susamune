"""Exercise Creation palette options through the real INI and payload code."""
import ctypes as C
from _ctypes import FreeLibrary
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_timer_creation import function
from test_nested_menu_focus import function as block
ROOT = Path(__file__).resolve().parents[1]

class CreationPersistenceTests(unittest.TestCase):
    def test_ini_payload_and_legacy_layout_options(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as folder:
            folder = Path(folder)
            (folder / "Dolphin").mkdir()
            (folder / "Dolphin/types.h").write_text("typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;")
            kernel = (ROOT / "launcher/kernel/SusamuneCfg.c").read_text()
            extras = (ROOT / "src/creation_extras.cpp").read_text()
            qft = (ROOT / "src/qft_display.cpp").read_text()
            code = r'''
#define private public
#include "susamune/creation_extras.hxx"
#include "susamune/qft_display.hxx"
#include "susamune/gradient_motion.hxx"
#undef private
#define API extern "C" __declspec(dllexport)
extern "C" void *memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return (u8)*a-(u8)*b;}
int memcmp(const void*a,const void*b,unsigned n){const u8*x=(const u8*)a,*y=(const u8*)b;while(n--){if(*x!=*y)return *x-*y;x++;y++;}return 0;}
unsigned strlen(const char*s){unsigned n=0;while(s[n])n++;return n;}
enum SettingId {SETTING_QFT_VERTICAL_GRADIENT,SETTING_QFT_GRADIENT_MOTION,SETTING_QFT_GRADIENT_SPEED,
 SETTING_NATIVE_VERTICAL_GRADIENT,SETTING_NATIVE_GRADIENT_MOTION,SETTING_NATIVE_GRADIENT_SPEED};
struct Settings {u8 values[6];u8 get(SettingId id){return values[id];}void set(SettingId id,u8 v){values[id]=v;}}gSettings;
struct SectionHistoryDisplay {static void adopt(u8){} static u8 style(){return 15;}};
unsigned emitted[3],emitCount;
int _sprintf(char*,const char*,unsigned,unsigned value){emitted[emitCount++]=value;return 0;}
void Emit(void*,int*,char*,unsigned){}
'''
            first=kernel.index("static const char *const CreationColorKeys")
            code+=kernel[first:kernel.index("};",first)+2]
            code+="\n".join(function(kernel,n) for n in ("ParseU16","ParseQftU8","ParseQftRgb","ParseCreationWordKey","ParseCreationCharKey","ApplyCreationKey","ApplyQftDisplayKey"))
            code+="\n".join(function(extras,n) for n in ("clampi","nativeTimerColorSlot","clampStyle","loadStyle","storeStyle","CreationExtras::clampWord","CreationExtras::adopt","CreationExtras::stageInto"))
            code+="\n".join(function(qft,n) for n in ("QftDisplay::clamp","QftDisplay::adopt","QftDisplay::stageInto"))
            code+="\nvoid emitWord(const SusamuneCreationCfg*d,unsigned word){const auto*w=&d->words[word];unsigned n=word+1;void*f=nullptr;int error=0;int*err=&error;char line[128];emitCount=0;"
            code+=block(kernel, "if (w->reserved & 0x80)")+"}\n"
            code+=r'''
API int run(){
 static CreationExtras e;static QftDisplay q;SusamuneCreationCfg c={};SusamuneQftDisplayCfg t={};
 c.magic=SUSAMUNE_CREATION_CFG_MAGIC;c.version=1;t.magic=SUSAMUNE_QFT_DISPLAY_CFG_MAGIC;t.version=2;
 ApplyCreationKey(&c,"native_timer_gradient_stops","5");
 ApplyCreationKey(&c,"word1_gradient_stops","5");ApplyCreationKey(&c,"word1_gradient_motion","2");ApplyCreationKey(&c,"word1_gradient_speed","0");
 ApplyCreationKey(&c,"word1_char_17_rgb","15,71,254");ApplyQftDisplayKey(&t,"gradient_stops","5");
 ApplyQftDisplayKey(&t,"text_5_rgb","25,73,240");
 if(c.words[0].reserved!=0x95||c.reservedAchievement0!=0xd5||t.reserved[0]!=5||t.reserved[1]!=0x47)return 1;
 ApplyCreationKey(&c,"word1_gradient_stops","6");ApplyCreationKey(&c,"word1_gradient_motion","10");ApplyCreationKey(&c,"word1_gradient_speed","255");ApplyQftDisplayKey(&t,"gradient_stops","6");
 if(c.words[0].reserved!=0x95||t.reserved[0]!=5)return 2;
 e.adopt(&c);q.adopt(&t);e.stageInto(&c);q.stageInto(&t);
 if(c.words[0].reserved!=0x95||c.reservedAchievement0!=0xd5||c.words[0].rgb[16][2]!=254||t.reserved[0]!=5||t.textRgb[4][2]!=240)return 3;
 for(unsigned i=0;i<6;++i)gSettings.values[i]=i%3?2:1;
 q.stageInto(&t);memset(gSettings.values,0,6);q.adopt(&t);
 for(unsigned i=0;i<6;++i)if(gSettings.values[i]!=(i%3?2:1))return 4;
 c.words[0].reserved=0;c.reservedAchievement0=0;t.reserved[1]=0;
 e.adopt(&c);q.adopt(&t);
 if(e.mWordGradient[0]!=0x20||e.mNativeGradient||q.mGradientOptions)return 5;
 if(e.mWordRgb[0][16][2]!=254||q.mTextRgb[4][2]!=240)return 6;
 ApplyCreationKey(&c,"word1_gradient_motion","4");ApplyCreationKey(&c,"word2_gradient_motion","3");ApplyCreationKey(&c,"word3_gradient_motion","4");
 if(c.stageSessionReserved!=0xa5)return 7;
 e.adopt(&c);
 if(GradientMotion::wordMotion(e.mWordGradient[0])!=4||GradientMotion::wordMotion(e.mWordGradient[1])!=3||GradientMotion::wordMotion(e.mWordGradient[2])!=4)return 8;
 e.stageInto(&c);if(c.stageSessionReserved!=0xa5)return 9;
 emitWord(&c,0);if(emitCount!=3||emitted[1]!=4)return 16;
 emitWord(&c,1);if(emitCount!=3||emitted[1]!=3)return 17;
 emitWord(&c,2);if(emitCount!=3||emitted[1]!=4)return 18;
 ApplyCreationKey(&c,"word1_gradient_motion","1");
 if(c.stageSessionReserved!=0xa4)return 10;
 e.adopt(&c);if(GradientMotion::wordMotion(e.mWordGradient[0])!=1||GradientMotion::wordMotion(e.mWordGradient[2])!=4)return 11;
 c.stageSessionReserved=0xb4;e.adopt(&c);
 if(GradientMotion::wordMotion(e.mWordGradient[2])!=0)return 12;
 c.stageSessionReserved=0xa4;c.words[2].reserved|=0x18;e.adopt(&c);
 if(GradientMotion::wordMotion(e.mWordGradient[2])!=7)return 13;
 gSettings.values[1]=3;gSettings.values[4]=4;q.stageInto(&t);
 gSettings.values[1]=gSettings.values[4]=0;q.adopt(&t);
 if(gSettings.values[1]!=3||gSettings.values[4]!=4)return 14;
 t.reservedV1[2]=10;t.reservedV1[5]=255;q.adopt(&t);
 if(gSettings.values[1]!=3||gSettings.values[4]!=4)return 15;
 ApplyCreationKey(&c,"word1_gradient_motion","5");ApplyCreationKey(&c,"word2_gradient_motion","6");
 e.adopt(&c);e.stageInto(&c);
 if(GradientMotion::wordMotion(e.mWordGradient[0])!=5||GradientMotion::wordMotion(e.mWordGradient[1])!=6)return 19;
 emitWord(&c,1);if(emitCount!=3||emitted[1]!=6)return 20;
 gSettings.values[1]=5;gSettings.values[4]=6;q.stageInto(&t);
 gSettings.values[1]=gSettings.values[4]=0;q.adopt(&t);
 if(gSettings.values[1]!=5||gSettings.values[4]!=6)return 21;
 ApplyCreationKey(&c,"word1_gradient_motion","8");ApplyCreationKey(&c,"word2_gradient_motion","9");
 ApplyCreationKey(&c,"word3_gradient_motion","7");
 ApplyCreationKey(&c,"word1_gradient_stops","5");ApplyCreationKey(&c,"word2_gradient_speed","2");
 e.adopt(&c);e.stageInto(&c);
 if((c.stageSessionReserved&0xc0)!=0xc0)return 22;
 for(unsigned i=0;i<3;++i){emitWord(&c,i);if(emitted[1]!=(i==0?8:i==1?9:7))return 23+i;}
 if(GradientMotion::wordStops(e.mWordGradient[0])!=5||GradientMotion::wordSpeed(e.mWordGradient[1])!=2)return 26;
 e.adopt(&c);e.stageInto(&c);
 for(unsigned i=0;i<3;++i)if(GradientMotion::wordMotion(e.mWordGradient[i])!=(i==0?8:i==1?9:7))return 27+i;
 return 0;
}
'''
            cpp=folder/"test.cpp";cpp.write_text(code)
            dll=folder/"test.dll"
            subprocess.run([str(ROOT/"toolchain/clang++.exe"),"--target=x86_64-pc-windows-msvc","-shared","-nostdlib","-fno-builtin","-fuse-ld=lld","-Wl,/noentry","-O2","-I",str(folder),"-I",str(ROOT/"include"),str(cpp),"-o",str(dll)],check=True,env={**os.environ,"TEMP":str(folder),"TMP":str(folder)})
            lib=C.CDLL(str(dll))
            try:self.assertEqual(lib.run(),0)
            finally:FreeLibrary(lib._handle)

if __name__=="__main__":unittest.main()
