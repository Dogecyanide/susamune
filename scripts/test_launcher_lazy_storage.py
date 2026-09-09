"""Run production launcher selection and storage checks against bounded fake devices."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LauncherLazyStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-lazy-storage-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.menu = (ROOT / "launcher/loader/source/SusamuneMenu.c").read_text()
        code = r'''
typedef unsigned u32,UINT;typedef unsigned char u8;typedef unsigned short WCHAR;
typedef int bool;typedef struct {int unused;} FIL;
#define true 1
#define false 0
#define NULL ((void*)0)
#define DEV_SD 0
#define DEV_USB 1
#define FR_OK 0
#define FA_READ 1
#define FA_OPEN_EXISTING 0
#define SUSA_PATH_DISC "di"
#define API __declspec(dllexport)
void*memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=d;const u8*b=s;while(n--)*a++=*b++;return d;}
void*memset(void*d,int v,__SIZE_TYPE__ n){u8*a=d;while(n--)*a++=(u8)v;return d;}
int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){const u8*x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;x++;y++;}return 0;}
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return (u8)*a-(u8)*b;}
int strncmp(const char*a,const char*b,__SIZE_TYPE__ n){while(n--){if(*a!=*b)return (u8)*a-(u8)*b;if(!*a)return 0;a++;b++;}return 0;}
char*strcpy(char*d,const char*s){char*out=d;while((*d++=*s++));return out;}
int snprintf(char*out,__SIZE_TYPE__ n,const char*fmt,...){unsigned i=0;while(i+1<n&&fmt[i]){out[i]=fmt[i];i++;}out[i]=0;return i;}
const char*SusamuneText(const char*english){return english;}
static void*devices[2];static bool isWiiVC;
static const char*const kDevLabel[2]={"SD Card","USB Storage"};
static const char*LauncherDev;static char ErrorLine[128],lastPath[250];
static struct {u8 version;char path[3][250];}gIni;
static unsigned mountCount[2],failureMask,messages,blankMounts,opens,reads,closes,applies;
static unsigned imageID,expectedID,imageMode,imageOffset;
static WCHAR mountName[4];
void ShowMessageScreen(const char*message){if(message[0])messages++;}
const WCHAR*MountDevice(int dev){mountCount[dev]++;if(!messages)blankMounts++;
 if(failureMask&(1u<<dev))return NULL;devices[dev]=(void*)1;return mountName;}
int f_open_char(FIL*f,const char*path,unsigned mode){opens++;imageOffset=0;strcpy(lastPath,path);return imageMode==1?4:0;}
int f_read(FIL*f,void*out,unsigned size,UINT*read){reads++;memset(out,0,size);*read=size;
 if(imageMode==2){*read=size-1;return 0;}
 if(imageMode==4&&!imageOffset){static const u8 magic[8]={'C','I','S','O',0,0,0x20,0};memcpy(out,magic,8);}
 else{memcpy(out,&imageID,4);((u8*)out)[8]=imageMode==3?0:0xaa;}return 0;}
int f_lseek(FIL*f,unsigned offset){imageOffset=offset;return 0;}
int f_close(FIL*f){closes++;return 0;}
bool IsGCGame(const u8*header){return header[8]==0xaa;}
bool SusamuneCheckGameID(u32 id){return id==expectedID;}
const char*SusaVersionName(u8 version){return version==0?"JP":version==1?"US":"PAL";}
void ApplyToNinCFG(void){applies++;}
'''
        for name in ("DeviceMounted", "EnsureDeviceMounted", "DeviceOfPath", "IsDiscPath",
                     "ReadImageGameID", "ValidateSelection", "SusamuneAutoBoot"):
            code += function(cls.menu, name)
        code += r'''
API void reset(unsigned mounted,unsigned failures,unsigned vc){
 memset(devices,0,sizeof(devices));for(unsigned i=0;i<2;i++)if(mounted&(1u<<i))devices[i]=(void*)1;
 failureMask=failures;isWiiVC=vc;mountCount[0]=mountCount[1]=messages=blankMounts=opens=reads=closes=applies=0;
 imageID=expectedID=0x454d5347;imageMode=0;ErrorLine[0]=lastPath[0]=0;
}
API void image(unsigned mode,unsigned wrong){imageMode=mode;imageID=expectedID+wrong;}
API int selectPath(const char*path,unsigned autoboot){strcpy(gIni.path[2],path);gIni.version=2;ErrorLine[0]=0;
 return autoboot?SusamuneAutoBoot("sd"):ValidateSelection();}
API int selectDevice(int dev){return EnsureDeviceMounted(dev);}
API void connect(unsigned dev){failureMask&=~(1u<<dev);}
API unsigned count(unsigned which){switch(which){case 0:return mountCount[0];case 1:return mountCount[1];
 case 2:return messages;case 3:return blankMounts;case 4:return opens;case 5:return reads;case 6:return closes;case 7:return applies;}return 0;}
API const char*error(void){return ErrorLine;}
API const char*openedPath(void){return lastPath;}
'''
        source = Path(cls.temp.name) / "storage.c"
        source.write_text(code, encoding="ascii")
        library = source.with_suffix(".dll")
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                                 "-nostdlib", "-fno-builtin", "-O2", "-fuse-ld=lld", "-Wl,/noentry",
                                 str(source), "-o", str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.selectPath.argtypes = [C.c_char_p, C.c_uint]
        cls.lib.error.restype = cls.lib.openedPath.restype = C.c_char_p

    def test_remembered_sd_path_never_probes_usb_and_reads_only_that_image(self):
        for autoboot in (0, 1):
            self.lib.reset(1, 2, 0)
            path = b"sd:/games/Sunshine PAL/game.iso"
            self.assertEqual(self.lib.selectPath(path, autoboot), 1)
            self.assertEqual([self.lib.count(i) for i in range(8)], [0, 0, 0, 0, 1, 1, 1, autoboot])
            self.assertEqual(self.lib.openedPath(), path)

    def test_requested_other_source_mounts_once_and_renders_before_its_wait(self):
        for mounted, path, dev in ((1, b"usb:/games/us.iso", 1), (2, b"sd:/games/jp.iso", 0)):
            self.lib.reset(mounted, 0, 0)
            self.assertEqual(self.lib.selectPath(path, 0), 1)
            self.assertEqual(self.lib.count(dev), 1)
            self.assertEqual(self.lib.count(dev ^ 1), 0)
            self.assertEqual(self.lib.count(2), 1)
            self.assertEqual(self.lib.count(3), 0)
            self.assertEqual(self.lib.selectPath(path, 1), 1)
            self.assertEqual(self.lib.count(dev), 1)

    def test_unavailable_source_refuses_without_open_then_can_retry_after_connection(self):
        for autoboot in (0, 1):
            self.lib.reset(1, 2, 0)
            self.assertEqual(self.lib.selectPath(b"usb:/game.iso", autoboot), 0)
            self.assertEqual(self.lib.count(1), 1)
            self.assertEqual(self.lib.count(4), 0)
            self.assertEqual(self.lib.count(7), 0)
            self.assertIn(b"not available", self.lib.error())
            self.lib.connect(1)
            self.assertEqual(self.lib.selectDevice(1), 1)
            self.assertEqual(self.lib.selectPath(b"usb:/game.iso", autoboot), 1)
            self.assertEqual(self.lib.count(1), 2)

    def test_disc_unset_invalid_prefix_and_wii_vc_never_probe_unused_devices(self):
        for path, vc, expected in ((b"di", 0, 1), (b"", 0, 0), (b"/bad.iso", 0, 0),
                                   (b"usb:/game.iso", 1, 0)):
            self.lib.reset(1, 0, vc)
            self.assertEqual(self.lib.selectPath(path, 0), expected)
            self.assertEqual([self.lib.count(i) for i in (0, 1, 4)], [0, 0, 0])
        for dev in (-1, 2):
            self.assertEqual(self.lib.selectDevice(dev), 0)

    def test_missing_short_invalid_and_wrong_region_images_still_refuse(self):
        for mode, wrong in ((1, 0), (2, 0), (3, 0), (0, 1)):
            self.lib.reset(1, 0, 0)
            self.lib.image(mode, wrong)
            self.assertEqual(self.lib.selectPath(b"sd:/game.iso", 1), 0)
            self.assertTrue(self.lib.error())
            self.assertEqual(self.lib.count(7), 0)
            self.assertEqual(self.lib.count(6), 0 if mode == 1 else 1)

    def test_ciso_header_remains_supported(self):
        self.lib.reset(1, 0, 0)
        self.lib.image(4, 0)
        self.assertEqual(self.lib.selectPath(b"sd:/game.ciso", 1), 1)
        self.assertEqual(self.lib.count(5), 2)
        self.assertEqual(self.lib.count(6), 1)

    def test_menu_and_browser_wire_checks_only_to_current_selection(self):
        menu = function(self.menu, "SusamuneMenuRun")
        self.assertIn("ValidateSelection();", menu[:menu.index("while (1)")])
        version = menu[menu.index("case ROW_VERSION:"):menu.index("case ROW_PATH:")]
        self.assertIn("ValidateSelection();", version)
        browser = function(self.menu, "BrowseDevices")
        self.assertIn("else if (EnsureDeviceMounted(pos - 1))", browser)
        self.assertIn("Press A to try again.", browser)
        self.assertNotIn("usable = DeviceMounted", browser)


if __name__ == "__main__":
    unittest.main()
