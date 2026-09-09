"""Execute episode choice parsing and regional INI copy-through with host storage."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class Episodes(C.Structure):
    _fields_ = [("magic", C.c_uint), ("version", C.c_ushort), ("count", C.c_ushort),
                ("episodes", C.c_ubyte * 20), ("reserved", C.c_ubyte * 36)]


class EpisodePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-episodes-")
        cls.addClassCleanup(cls.temp.cleanup)
        kernel = (ROOT / "launcher/kernel/SusamuneCfg.c").read_text()
        loader = (ROOT / "launcher/loader/source/SusamuneIni.c").read_text()
        iling = (ROOT / "src/iling.cpp").read_text()
        cls.keys = re.findall(r'X\(\d+, "([^"]+)"\)',
                             (ROOT / "include/susamune/iling_episodes.h").read_text())
        code = r'''
#include "susamune/susamune_cfg.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;typedef int s32;
typedef unsigned UINT;typedef unsigned FSIZE_t;
#define API extern "C" __declspec(dllexport)
#define NULL 0
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int v,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)v;return d;}
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return (u8)*a-(u8)*b;}
unsigned strlen(const char*s){unsigned n=0;while(s[n])n++;return n;}
char*strchr(char*s,int c){while(*s&&*s!=c)s++;return *s==c?s:0;}
char*number(char*out,unsigned v){char d[10];unsigned n=0;do{d[n++]='0'+v%10;v/=10;}while(v);while(n)*out++=d[--n];return out;}
int _sprintf(char*out,const char*fmt,...){char*start=out;__builtin_va_list a;__builtin_va_start(a,fmt);
 while(*fmt){if(*fmt!='%'){*out++=*fmt++;continue;}fmt++;if(*fmt=='s'){const char*s=__builtin_va_arg(a,const char*);while(*s)*out++=*s++;}
 else if(*fmt=='u')out=number(out,__builtin_va_arg(a,unsigned));fmt++;}__builtin_va_end(a);*out=0;return out-start;}
#define SUSAMUNE_INI_BUF_SIZE 49152
#define SUSAMUNE_SECTION_NAME_MAX 24
#define SUSAMUNE_INI_TRANSACTION_PATH_MAX 128
static char SettingsSection[24],BindsSection[24],InputDisplaySection[24],MetadataDisplaySection[24],QftDisplaySection[24],CreationSection[24];
static SusamuneILEpisodesCfg episodes;
#undef SUSAMUNE_IL_EPISODES_PHYS_PTR
#define SUSAMUNE_IL_EPISODES_PHYS_PTR (&episodes)
static SusamuneCfg cfg;
static SusamuneMarioColorsCfg mario;static SusamuneFluddColorsCfg fludd;
SusamuneMarioColorsCfg*MarioColorsBlock(){return &mario;}SusamuneFluddColorsCfg*FluddColorsBlock(){return &fludd;}
static bool SawSettingsSection;
int FindSettingKey(const char*){return -1;}int FindBindKey(const char*){return -1;}
bool ParseBindMask(const char*,u16*){return false;}
enum {FR_OK=0,FR_DISK_ERR=1,FR_NOT_READY=3,FR_NO_FILE=4,FR_NO_PATH=5,FR_DENIED=7,FR_NOT_ENOUGH_CORE=17,FR_INVALID_NAME=6,AM_RDO=1,FA_READ=1,FA_WRITE=2,FA_OPEN_EXISTING=0,FA_CREATE_ALWAYS=8};
struct FIL {struct {unsigned attr;}obj;char*text;unsigned length;};
struct FILINFO {unsigned fattrib;};
static char original[65536],output[65536],scratch[65536];static unsigned originalLength,outputLength;
static unsigned attrPoison,realAttr,tempOpens,sourceCloses,commits;static int statError,closeError;
void*malloca(unsigned,unsigned){return scratch;}void free(void*){}
void*malloc(unsigned){return scratch;}
const char*SusamuneCfgIniPath(){return "settings.ini";}
bool BuildIniSiblingPath(char*out,unsigned,const char*,const char*){out[0]='t';out[1]=0;return true;}
int RecoverIniFile(const char*){return 0;}
int f_open_char(FIL*f,const char*,unsigned mode){f->obj.attr=attrPoison;f->text=mode&FA_WRITE?output:original;f->length=mode&FA_WRITE?0:originalLength;if(mode&FA_WRITE)tempOpens++;return 0;}
int f_stat_char(const char*,FILINFO*info){info->fattrib=realAttr;return statError;}
unsigned f_size(FIL*f){return f->length;}
int f_read(FIL*f,void*out,unsigned n,UINT*read){*read=f->length<n?f->length:n;memcpy(out,f->text,*read);return 0;}
int f_write(FIL*f,const void*in,unsigned n,UINT*written){if(f->length+n>=65536)return 1;memcpy(f->text+f->length,in,n);f->length+=n;*written=n;return 0;}
int f_close(FIL*f){if(f->text==output){outputLength=f->length;output[outputLength]=0;return 0;}sourceCloses++;return closeError;}
int CommitIniFile(const char*,const char*,const char*,bool){memcpy(original,output,outputLength+1);originalLength=outputLength;commits++;return 0;}
static const char kIniBanner[]="; test\r\n";
#define SUSA_INI_BUF_SIZE 32768
#define SUSA_INI_TRANSACTION_PATH_MAX 128
#define SUSA_SECTION_NAME_MAX 24
static bool LoadSafe=true;
void BuildPath(char*out,unsigned,const char*){memcpy(out,"settings.ini",13);}
unsigned DeviceForName(const char*){return 0;}void RemountDevice(unsigned){}
'''
        for name in re.findall(r"\b(Apply\w+)\(", function(kernel, "ParseIni")):
            if name != "ApplyILEpisodeKey":
                code += f"template<class... T>void {name}(T...){{}}\n"
        code += kernel[kernel.index("enum IniSection {"):kernel.index("static enum IniSection ClassifySection")]
        code += kernel[kernel.index("#define IL_EPISODE_KEY"):kernel.index("static void ApplyILEpisodeKey")]
        keys = kernel[kernel.index("static const char *const CreationColorKeys"):]
        code += keys[:keys.index("};") + 2]
        for name in ("BuildSectionName", "IsSpace", "Trim", "ParseU8", "ClassifySection",
                     "ApplyILEpisodeKey", "ParseIni", "Emit", "EmitStr", "EmitILEpisodes"):
            code += function(kernel, name)
        for name in ("EmitMovementOverlayStyle", "EmitNativeTimerStyle", "EmitMarioColors", "EmitFluddColors"):
            code += f"template<class... T>void {name}(T...){{}}\n"
        for name in ("Settings", "Binds", "InputDisplay", "MetadataDisplay", "QftDisplay"):
            code += f'void Emit{name}Section(FIL*f,int*e,const SusamuneCfg*){{EmitStr(f,e,"[");EmitStr(f,e,{name}Section);EmitStr(f,e,"]\\r\\n");}}\n'
        code += function(kernel, "EmitCreationSection") + function(kernel, "WriteIniFile")
        code += 'void EmitNintendontSection(FIL*f,int*e){EmitStr(f,e,"[nintendont]\\r\\ngame_version = 2\\r\\n");}\n'
        code += function(loader, "SusamuneIniSave")
        code += 'static u8 sEpisodeChoices[SUSAMUNE_IL_EPISODE_COUNT];\n'
        for name in ("resetEpisodeChoices", "adoptEpisodes", "stageEpisodes"):
            code += function(iling, name)
        code += r'''
API void selectRegion(const char*region){
 BuildSectionName(SettingsSection,SUSAMUNE_INI_SECTION_SETTINGS,region);
 BuildSectionName(BindsSection,SUSAMUNE_INI_SECTION_BINDS,region);
 BuildSectionName(InputDisplaySection,SUSAMUNE_INI_SECTION_INPUT_DISPLAY,region);
 BuildSectionName(MetadataDisplaySection,SUSAMUNE_INI_SECTION_METADATA_DISPLAY,region);
 BuildSectionName(QftDisplaySection,SUSAMUNE_INI_SECTION_QFT_DISPLAY,region);
 BuildSectionName(CreationSection,SUSAMUNE_INI_SECTION_CREATION,region);
 resetEpisodeChoices();stageEpisodes(&episodes);memset(&cfg,0,sizeof(cfg));
 attrPoison=0xa5;realAttr=0x20;statError=closeError=0;tempOpens=sourceCloses=commits=0;
}
API void parse(const char*text){static char input[65536];memcpy(input,text,strlen(text)+1);ParseIni(input,&cfg);}
API void getEpisodes(SusamuneILEpisodesCfg*out){*out=episodes;}
API void setEpisodes(const SusamuneILEpisodesCfg*in){episodes=*in;}
API void adopt(const SusamuneILEpisodesCfg*in,SusamuneILEpisodesCfg*out){adoptEpisodes(in);stageEpisodes(out);}
API const char*rewrite(const char*input){originalLength=strlen(input);memcpy(original,input,originalLength+1);return WriteIniFile(&cfg)?0:original;}
API void attributes(unsigned poison,unsigned actual,int stat,int close){attrPoison=poison;realAttr=actual;statError=stat;closeError=close;tempOpens=sourceCloses=commits=0;}
API int attemptRewrite(unsigned loader,const char*input){originalLength=strlen(input);memcpy(original,input,originalLength+1);return loader?SusamuneIniSave("sd"):WriteIniFile(&cfg);}
API const char*readOriginal(){return original;}
API unsigned operations(){return tempOpens|(sourceCloses<<8)|(commits<<16);}
'''
        source = Path(cls.temp.name) / "episodes.cpp"
        source.write_text(code, encoding="ascii")
        dll = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared", "-nostdlib",
                        "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2", "-I", str(ROOT / "include"),
                        str(source), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.selectRegion.argtypes = [C.c_char_p]
        cls.lib.parse.argtypes = [C.c_char_p]
        cls.lib.getEpisodes.argtypes = cls.lib.setEpisodes.argtypes = [C.POINTER(Episodes)]
        cls.lib.adopt.argtypes = [C.POINTER(Episodes), C.POINTER(Episodes)]
        cls.lib.rewrite.argtypes = [C.c_char_p]
        cls.lib.rewrite.restype = C.c_char_p
        cls.lib.attributes.argtypes = [C.c_uint, C.c_uint, C.c_int, C.c_int]
        cls.lib.attemptRewrite.argtypes = [C.c_uint, C.c_char_p]
        cls.lib.readOriginal.restype = C.c_char_p

    def test_both_writers_use_real_attributes_despite_poisoned_file_object(self):
        original = b"[creation_jp]\r\nkeep = 77\r\n[creation_us]\r\nkeep = 88\r\n"
        for loader in (0, 1):
            for poison in (0, 1, 0x20, 0xa5, 0xff):
                with self.subTest(loader=loader, poison=poison):
                    self.lib.attributes(poison, 0x20, 0, 0)
                    self.assertEqual(self.lib.attemptRewrite(loader, original), 0)
                    self.assertTrue(self.lib.readOriginal().startswith(original))
                    self.assertEqual(self.lib.operations(), 0x10101)

    def test_both_writers_preserve_readonly_source_and_attribute_errors(self):
        original = b"[creation_pal]\r\nil_episode_bianco_100 = 4\r\n"
        for loader in (0, 1):
            for actual, stat_error, close_error, expected in (
                    (0x21, 0, 0, 7), (0x20, 1, 0, 1), (0x20, 4, 0, 4),
                    (0x21, 0, 1, 1), (0x20, 0, 1, 1), (0x20, 1, 7, 1)):
                with self.subTest(loader=loader, actual=actual, stat=stat_error, close=close_error):
                    self.lib.attributes(0, actual, stat_error, close_error)
                    self.assertEqual(self.lib.attemptRewrite(loader, original), expected)
                    self.assertEqual(self.lib.readOriginal(), original)
                    self.assertEqual(self.lib.operations(), 0x100)

    def setUp(self):
        self.lib.selectRegion(b"pal")

    def snapshot(self):
        result = Episodes()
        self.lib.getEpisodes(C.byref(result))
        return result

    def test_all_stable_choices_roundtrip_without_touching_other_regions(self):
        other = "[nintendont]\r\ngame_version = 1\r\n[creation_jp]\r\nil_episode_bianco_100 = 2\r\n[creation_us]\r\nil_episode_pinna_100 = 7\r\n"
        source = other + "[creation_pal]\r\n" + "".join(
            f"il_episode_{key} = {i % 9}\r\n" for i, key in enumerate(self.keys))
        self.lib.parse(source.encode())
        expected = bytes(self.snapshot())
        self.assertEqual(list(self.snapshot().episodes), [i % 9 for i in range(20)])
        rewritten = self.lib.rewrite(source.encode()).decode()
        self.assertTrue(rewritten.startswith(other))
        self.lib.selectRegion(b"pal")
        self.lib.parse(rewritten.encode())
        self.assertEqual(bytes(self.snapshot()), expected)
        for region, index, value in ((b"jp", 0, 2), (b"us", 3, 7)):
            self.lib.selectRegion(region)
            self.lib.parse(rewritten.encode())
            self.assertEqual(self.snapshot().episodes[index], value)

    def test_bad_values_and_wrong_sections_leave_existing_choice(self):
        prefix = b"[creation_pal]\nil_episode_bianco_100 = 4\n"
        for text in ("", "9", "255", "256", "-1", "+1", "1.0", "1x", "999999999999999999999"):
            with self.subTest(text=text):
                self.lib.parse(prefix + f"il_episode_bianco_100 = {text}\n".encode())
                self.assertEqual(self.snapshot().episodes[0], 4)
        for section in ("settings_pal", "creation_jp", "creation_us", "creation", "unknown"):
            self.lib.parse(prefix + f"[{section}]\nil_episode_bianco_100 = 8\n".encode())
            self.assertEqual(self.snapshot().episodes[0], 4)
        self.lib.parse(prefix + b"il_episode_bianco_100 =  8 \r\n")
        self.assertEqual(self.snapshot().episodes[0], 8)

    def test_adoption_rejects_bad_headers_and_limits_partial_or_bad_entries(self):
        valid = self.snapshot()
        valid.episodes[:] = range(20)
        valid.reserved[:] = [0xa5] * 36
        out = Episodes()
        self.lib.adopt(C.byref(valid), C.byref(out))
        self.assertEqual(list(out.episodes), list(range(9)) + [0] * 11)
        self.assertEqual(bytes(out.reserved), bytes(36))
        valid.count = 3
        self.lib.adopt(C.byref(valid), C.byref(out))
        self.assertEqual(list(out.episodes), [0, 1, 2] + [0] * 17)
        for field, value in (("magic", 0), ("version", 2), ("count", 21)):
            broken = Episodes.from_buffer_copy(valid)
            setattr(broken, field, value)
            self.lib.adopt(C.byref(broken), C.byref(out))
            self.assertEqual(bytes(out.episodes), bytes(20))
        self.lib.adopt(None, C.byref(out))
        self.assertEqual(bytes(out.episodes), bytes(20))

    def test_wii_handoff_flush_and_read_are_explicit(self):
        kernel = (ROOT / "launcher/kernel/SusamuneCfg.c").read_text()
        init = function(kernel, "SusamuneCfgInit")
        self.assertIn("sync_after_write(SUSAMUNE_IL_EPISODES_PHYS_PTR", init[init.index("ParseIni(buf, cfg)"):])
        self.assertIn("sync_before_read(SUSAMUNE_IL_EPISODES_PHYS_PTR", function(kernel, "SusamuneCfgService"))


if __name__ == "__main__":
    unittest.main()
