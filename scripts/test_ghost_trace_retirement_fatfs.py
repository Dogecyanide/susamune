"""Check production cold-create flags against real kernel FatFs access rules."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
#include "ff.h"
#include "diskio.h"
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){BYTE*a=d;const BYTE*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int v,__SIZE_TYPE__ n){BYTE*a=d;while(n--)*a++=(BYTE)v;return d;}
int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){const BYTE*x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;x++;y++;}return 0;}
static BYTE disk[8192*512];static FATFS fs;
DSTATUS disk_initialize(BYTE drive){return drive?STA_NODISK:0;}
DSTATUS disk_status(BYTE drive){return disk_initialize(drive);}
static DRESULT readDisk(BYTE drive,BYTE*out,DWORD sector,UINT count){if(drive||sector>=8192||count>8192-sector)return RES_PARERR;memcpy(out,disk+sector*512,count*512);return RES_OK;}
static DRESULT writeDisk(BYTE drive,const BYTE*in,DWORD sector,UINT count){if(drive||sector>=8192||count>8192-sector)return RES_PARERR;memcpy(disk+sector*512,in,count*512);return RES_OK;}
DiskReadFunc disk_read=readDisk;DiskWriteFunc disk_write=writeDisk;
DRESULT disk_ioctl(BYTE drive,BYTE cmd,void*out){if(drive)return RES_PARERR;if(cmd==CTRL_SYNC)return RES_OK;if(cmd==GET_SECTOR_SIZE){*(WORD*)out=512;return RES_OK;}if(cmd==GET_SECTOR_COUNT){*(DWORD*)out=8192;return RES_OK;}if(cmd==GET_BLOCK_SIZE){*(DWORD*)out=1;return RES_OK;}return RES_PARERR;}
DWORD get_fattime(void){return (46u<<25)|(11u<<21)|(7u<<16);}
static void word(unsigned offset,WORD value){disk[offset]=value;disk[offset+1]=value>>8;}
static void path(const char*in,TCHAR*out){while((*out++=(BYTE)*in++));}
__declspec(dllexport) int probe(unsigned writeOnly){
 static const TCHAR drive[]={'0',':',0};TCHAR oldName[40],newName[40];FIL old,next;FILINFO info;
 BYTE oldData[192],nextData[96],check[192];UINT done;int r;
 f_mount(0,drive,0);memset(disk,0,sizeof(disk));memset(&fs,0,sizeof(fs));
 disk[0]=0xeb;disk[1]=0x3c;disk[2]=0x90;memcpy(disk+3,"MSDOS5.0",8);word(11,512);disk[13]=1;word(14,1);disk[16]=1;word(17,512);word(19,8192);disk[21]=0xf8;word(22,32);word(24,32);word(26,64);disk[38]=0x29;memcpy(disk+54,"FAT16   ",8);word(510,0xaa55);word(512,0xfff8);word(514,0xffff);
 if((r=f_mount(&fs,drive,1)))return -100-r;
 path("0:/trace_A.part",oldName);path("0:/trace_B.part",newName);
 for(unsigned i=0;i<sizeof(oldData);i++)oldData[i]=(BYTE)(i*17+3);
 for(unsigned i=0;i<sizeof(nextData);i++)nextData[i]=(BYTE)(i*29+11);
 if((r=f_open(&old,oldName,writeOnly?(FA_WRITE|FA_CREATE_NEW):COLD_FLAGS)))return -200-r;
 if((r=f_write(&old,oldData,sizeof(oldData),&done))||done!=sizeof(oldData))return -300-r;
 if((r=f_open(&next,newName,COLD_FLAGS)))return -400-r;
 if((r=f_write(&next,nextData,sizeof(nextData),&done))||done!=sizeof(nextData)||f_sync(&next))return -500-r;
 if((r=f_lseek(&old,0)))return -600-r;
 r=f_read(&old,check,64,&done);
 if(writeOnly)return r==FR_DENIED?1:-700-r;
 if(r||done!=64||memcmp(check,oldData,64))return -800-r;
 if(f_size(&old)!=sizeof(oldData)||f_close(&old)||f_unlink(oldName))return -900;
 if(f_stat(oldName,&info)!=FR_NO_FILE)return -1000;
 if(f_lseek(&next,0)||f_read(&next,check,sizeof(nextData),&done)||done!=sizeof(nextData)||memcmp(check,nextData,sizeof(nextData)))return -1100;
 if(f_size(&next)!=sizeof(nextData)||f_close(&next))return -1200;
 return _FS_TINY==1&&_FS_RPATH==0?1:-1300;
}
'''


class RetirementFatFsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='retire-fatfs-');cls.addClassCleanup(cls.temp.cleanup);folder=Path(cls.temp.name)
  source=(ROOT/'launcher/kernel/GhostTraceStorage.c').read_text(encoding='utf-8')
  flags=re.findall(r'f_open_char\(&w->file,w->path,([^)]*)\)',source)
  if len(flags)!=1:raise AssertionError('Expected one normal cold trace create')
  fixture=folder/'fixture.c';fixture.write_text('#define COLD_FLAGS ('+flags[0]+')\n'+FIXTURE,encoding='ascii')
  fatfs=ROOT/'launcher/fatfs';library=folder/'test.dll'
  r=subprocess.run([str(ROOT/'toolchain/clang.exe'),'--target=x86_64-pc-windows-msvc','-U_WIN32','-shared','-nostdlib','-fno-builtin','-mno-stack-arg-probe','-O2','-fuse-ld=lld','-Wl,/noentry','-I',str(fatfs),str(fixture),str(fatfs/'ff.c'),str(fatfs/'option/ccsbcs.c'),'-o',str(library)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(library));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
 def test_actual_cold_create_can_read_old_header_close_unlink_and_preserve_new_writer(self):self.assertEqual(self.lib.probe(0),1)
 def test_real_fatfs_rejects_the_previous_write_only_access_mode(self):self.assertEqual(self.lib.probe(1),1)


if __name__=='__main__':unittest.main()
