"""Exercise first-frame presentation and theme preloading without Wii hardware."""

import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LauncherStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-startup-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        cls.main = (ROOT / "launcher/loader/source/main.c").read_text()
        graphics = (ROOT / "launcher/loader/source/grrlib.c").read_text()
        source = r'''
typedef unsigned short WCHAR; typedef int bool;
#define true 1
#define false 0
#define NULL ((void*)0)
#define DEV_SD 0
#define DEV_USB 1
#define GX_TRUE 1
#define GX_FALSE 0
#define GX_LEQUAL 3
#define VI_NON_INTERLACE 1
static bool UseSD,isWiiVC,enable_output;
static int mountOK,themeOK,mountCount,loadCount,closeCount,event,sequence,lastDev,timeout;
static char launch_dir[]="sd:/apps/moonshine_launcher/";
static void *background;
static WCHAR mountedName[4];
const WCHAR *MountDeviceWithTimeout(int dev,int seconds){
 mountCount++;lastDev=dev;timeout=seconds;sequence=sequence*10+1;
 return mountOK?mountedName:NULL;
}
const char *GetRootDevice(void){return UseSD?"sd":"usb";}
bool SusamuneThemeLoad(const char*device,void**out){
 loadCount++;sequence=sequence*10+2;*out=(void*)0x1234;return themeOK;
}
void UnmountDevice(int dev){closeCount++;sequence=sequence*10+3;}
static void *xfb[2];static int fb,depthTest,depthWrite,blackPending,blackVisible,copies,copyDepth,flushes;
static int copyQueued,copyComplete,publishedTooSoon;
static const char *drawnMessage,*displayedMessage;
static struct {int viTVMode;} mode;
static void *nextFramebuffer;
static typeof(mode) *rmode=&mode;
void GX_DrawDone(void){if(copyQueued){copyComplete=1;copyQueued=0;}}
void GX_InvalidateTexAll(void){}
void GX_SetZMode(int test,int compare,int write){depthTest=test;depthWrite=write;}
void GX_SetColorUpdate(int value){}
void GX_CopyDisp(void*frame,int clear){copies++;copyDepth=depthWrite;copyQueued=1;copyComplete=0;displayedMessage=drawnMessage;}
void VIDEO_SetNextFramebuffer(void*frame){nextFramebuffer=frame;if(!copyComplete)publishedTooSoon=1;}
void VIDEO_Flush(void){blackVisible=blackPending;flushes++;}
void VIDEO_SetBlack(int value){blackPending=value;}
void VIDEO_WaitVSync(void){}
'''
        source += function(cls.main, "PreloadLauncherTheme")
        source += function(graphics, "GRRLIB_RenderMode")
        source += r'''
#define DEFAULT_SIZE 16
#define BLACK 0x000000ff
unsigned long long strlen(const char*s){unsigned long long n=0;while(s[n])n++;return n;}
const char *strchr(const char*s,int c){while(*s&&*s!=c)s++;return *s==c?s:NULL;}
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a-*b;}
void ClearScreen(void){drawnMessage=NULL;}
void PrintInfo(void){}
void PrintFormat(int size,int color,int x,int y,const char*fmt,int len,const char*line){drawnMessage=line;}
void GRRLIB_Render(void){GRRLIB_RenderMode(true);}
'''
        menu = (ROOT / "launcher/loader/source/menu.c").read_text()
        source += function(menu, "ShowMessageScreen")
        source += r'''
static int warningMask,menuOpened,mountChecks,blankChecks,elapsedTicks;
static bool LauncherCanSave;
void SusamuneMusicInit(void){}
void SusamuneMusicLoad(const char*root){}
void SusamuneMusicStart(void){}
const char *SusamuneThemeWarning(void){return warningMask&1?"Theme warning":"";}
const char *SusamuneMusicWarning(void){return warningMask&2?"Music warning":"";}
void usleep(unsigned ticks){elapsedTicks+=ticks;}
bool MountDeviceOnce(int dev){
 for(int i=0;i<(dev==DEV_USB?600:3);i++){
  mountChecks++;
  if(!displayedMessage||strcmp(displayedMessage,"Checking storage devices..."))blankChecks++;
  usleep(16667);
 }
 return true;
}
void SusamuneMenuRun(const char*root,bool canSave){menuOpened++;}
'''
        # The menu must not probe unused storage after loading theme/music.
        start = cls.main.index("\n\tif(!(ncfg->Config & NIN_CFG_AUTO_BOOT))")
        start = cls.main.index("{", start)
        depth, end = 1, start + 1
        while depth:
            depth += (cls.main[end] == "{") - (cls.main[end] == "}")
            end += 1
        source += "void prepareMenu(void)" + cls.main[start:end]
        source += r'''
__declspec(dllexport) int menu_storage_wait(int warnings){
 warningMask=warnings;menuOpened=mountChecks=blankChecks=elapsedTicks=0;
 drawnMessage=displayedMessage="Loading settings...";
 prepareMenu();
 if(menuOpened!=1||mountChecks!=0)return 1;
 return blankChecks?2:0;
}
'''
        source += r"""
typedef int DRESULT;typedef unsigned char BYTE;
#define RES_OK 0
#define RES_PARERR 1
static bool disk_isInit[2];static void *cache[2];static int sdClose,usbClose,usbHandles,cacheFreed;
int closeSD(void){sdClose++;return 1;}int closeUSB(void){usbClose++;return 1;}
static struct {int(*shutdown)(void);} sdDriver={closeSD},usbDriver={closeUSB};
static typeof(sdDriver)*driver[2]={&sdDriver,&usbDriver};
void USBStorageOGC_Deinitialize(void){usbClose++;}
void USB_OGC_Deinitialize(void){usbHandles++;}
void _FAT_cache_destructor(void*p){cacheFreed++;}
"""
        disk = (ROOT / "launcher/loader/source/diskio.c").read_text()
        source += function(disk.replace("disk_shutdown (", "disk_shutdown("), "disk_shutdown")
        source += r"""
__declspec(dllexport) int partial_probe(int dev){
 sdClose=usbClose=usbHandles=cacheFreed=0;
 disk_isInit[dev]=false;cache[dev]=NULL;
 if(disk_shutdown(dev)!=RES_OK||cacheFreed)return 1;
 if(dev==DEV_SD)return sdClose==1&&!usbClose&&!usbHandles?0:2;
 return !sdClose&&usbClose==1&&usbHandles==1?0:3;
}
"""
        source += r'''
__declspec(dllexport) int preload(int test){
 UseSD=test!=1&&test!=3;isWiiVC=test==3;mountOK=test!=2;themeOK=test!=4;
 mountCount=loadCount=closeCount=sequence=0;timeout=-1;background=NULL;
 int result=PreloadLauncherTheme();
 if(test==3)return result||mountCount||loadCount||closeCount?1:0;
 if(mountCount!=1||closeCount!=1||timeout!=0||lastDev!=(UseSD?DEV_SD:DEV_USB))return 2;
 if(test==2)return result||loadCount||sequence!=13?3:0;
 if(loadCount!=1||sequence!=123||background!=(void*)0x1234)return 4;
 return result!=themeOK?5:0;
}
__declspec(dllexport) int first_frame(int preserve){
 enable_output=false;fb=0;depthTest=depthWrite=1;blackPending=blackVisible=1;
 copies=flushes=copyQueued=copyComplete=publishedTooSoon=0;mode.viTVMode=0;xfb[0]=(void*)0x1111;xfb[1]=(void*)0x2222;
 GRRLIB_RenderMode(!preserve);
 if(blackVisible||!enable_output||copies!=1||flushes!=1||nextFramebuffer!=xfb[1])return 1;
 return depthTest||depthWrite||!copyDepth||!copyComplete||publishedTooSoon?2:0;
}
'''
        cfile = work / "startup.c"
        cfile.write_text(source, encoding="ascii")
        library = work / "startup.dll"
        subprocess.run([str(ROOT / "toolchain/clang.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        str(cfile), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_own_device_theme_probe_closes_even_when_storage_or_png_fails(self):
        for case in range(5):
            with self.subTest(case=case):
                self.assertEqual(self.dll.preload(case), 0)

    def test_partial_probe_closes_each_devices_driver_handles(self):
        for device in range(2):
            self.assertEqual(self.dll.partial_probe(device), 0)

    def test_first_frame_unblanks_with_its_framebuffer_and_releases_depth_state(self):
        for preserve in range(2):
            with self.subTest(preserve=preserve):
                self.assertEqual(self.dll.first_frame(preserve), 0)

    def test_theme_is_visible_before_kernel_work_and_music_waits_for_menu(self):
        main = self.main[self.main.index("int main(int argc, char **argv)"): ]
        self.assertLess(main.index("PreloadLauncherTheme()"), main.index('ShowMessageScreen("Starting Moonshine...")'))
        self.assertLess(main.index('ShowMessageScreen("Starting Moonshine...")'), main.index("LoadKernel()"))
        self.assertLess(main.index("KernelLoaded = 1"), main.index("SusamuneMusicInit()"))
        self.assertNotIn("RevealBackground(false)", main)

    def test_menu_does_not_wait_for_unused_storage_with_or_without_asset_warnings(self):
        for warnings in range(4):
            with self.subTest(warnings=warnings):
                self.assertEqual(self.dll.menu_storage_wait(warnings), 0)

    def test_first_launcher_device_probe_keeps_visible_storage_message(self):
        start = self.main.index("KernelLoaded = 1")
        end = self.main.index('ShowMessageScreen("Loading settings...")', start)
        probe = self.main[start:end]
        self.assertLess(probe.index('ShowMessageScreen("Checking storage devices...")'),
                        probe.index("MountLauncherDevice()"))


if __name__ == "__main__":
    unittest.main()
