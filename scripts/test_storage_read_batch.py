"""Check production SD and USB drivers with the enlarged mapped-read batch."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_practice_tape import function_source

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r"""
typedef unsigned char u8;typedef signed char s8;typedef unsigned int u32;typedef int s32;typedef u32 sec_t;
typedef _Bool bool;
#define true 1
#define false 0
#define NULL ((void*)0)
#define PAGE_SIZE512 512
#define SDIO_CMD_READMULTIBLOCK 0x12
#define SDIOCMD_TYPE_AC 3
#define SDIO_RESPONSE_R1 1
#define MAX_TRANSFER_SIZE_V5 16384
#define USBSTORAGE_CYCLE_RETRIES 2
#define USBSTORAGE_OK 0
#define USBSTORAGE_ETIMEDOUT -100
#define USBSTORAGE_EDATARESIDUE -101
#define USBSTORAGE_ESTATUS -102
#define CBW_OUT 0
#define CBW_IN 0x80
#define SCSI_READ_10 0x28
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=d;const u8*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int v,__SIZE_TYPE__ n){u8*a=d;while(n--)*a++=(u8)v;return d;}
__declspec(align(32)) static u8 sdBounce[65536+64],usbBounce[16384+64];
static u8 *rw_buffer=sdBounce+32,*transferbuffer=usbBounce+32;
static u8 *destination;static u32 capacity,sdCalls,usbCalls,maxSd,maxUsb,bad,selected,deselected,failAt,cbws,csws,resets;
static u32 usbOffset,usbStart,expectedCount,expectedSector;
static u32 __sd0_sdhc=1,__mounted=1,s_size=512;static u8 __ep_out=2,__ep_in=0x81,__lun=0;static s32 __usb_fd=1;
static u8 sample(u32 offset){return (u8)(offset^(offset>>8)^(offset>>16));}
static int inside(void*p,u32 n,u8*base,u32 size){__UINTPTR_TYPE__ a=(__UINTPTR_TYPE__)p,b=(__UINTPTR_TYPE__)base;return a>=b&&a-b<=size&&n<=size-(a-b);}
static void check(void*p,u32 n){if(!inside(p,n,destination,capacity)&&!inside(p,n,rw_buffer,65536)&&!inside(p,n,transferbuffer,16384))++bad;}
static void sync_before_read(void*p,u32 n){check(p,n);}static void sync_after_write(void*p,u32 n){check(p,n);}static void _ahbMemFlush(u32 n){}
static s32 __sd0_select(void){++selected;return 0;}static s32 __sd0_deselect(void){++deselected;return 0;}
static s32 __sdio_sendcommand(u32 cmd,u32 type,u32 response,u32 sector,u32 count,u32 block,void*out,void*unused,u32 unusedSize){
 ++sdCalls;if(count*block>maxSd)maxSd=count*block;
 if(cmd!=SDIO_CMD_READMULTIBLOCK||type!=3||response!=1||block!=512)++bad;
 if(out==rw_buffer&&count>128)++bad;
 check(out,count*block);if(sdCalls==failAt)return -1;
 u32 start=__sd0_sdhc?sector*512:sector;
 for(u32 i=0;i<count*block;++i)((u8*)out)[i]=sample(start+i);
 return 0;
}
static s32 __send_cbw(u8 lun,u32 length,u8 dir,u8*cmd,u8 bytes){
 ++cbws;usbOffset=0;usbStart=((u32)cmd[2]<<24)|((u32)cmd[3]<<16)|((u32)cmd[4]<<8)|cmd[5];
 u32 count=((u32)cmd[7]<<8)|cmd[8];
 if(lun||dir!=CBW_IN||bytes!=10||cmd[0]!=SCSI_READ_10||usbStart!=expectedSector||count!=expectedCount||length!=count*512)++bad;
 return 0;
}
static s32 USB_WriteBlkMsg(s32 fd,u8 ep,u32 length,void*out){
 ++usbCalls;if(length>maxUsb)maxUsb=length;
 if(fd!=1||ep!=__ep_in||length>16384)++bad;check(out,length);
 if(usbCalls==failAt)return USBSTORAGE_ETIMEDOUT;
 for(u32 i=0;i<length;++i)((u8*)out)[i]=sample(usbStart*512+usbOffset+i);
 usbOffset+=length;return length;
}
static s32 __read_csw(u8*status,u32*residue){++csws;*status=0;*residue=0;return 0;}
static s32 __usbstorage_reset(void){++resets;return USBSTORAGE_ETIMEDOUT;}
"""
EXPORTS=r"""
#define API __declspec(dllexport)
API int take(unsigned usb,void*buffer,unsigned sector,unsigned count,unsigned sdhc,unsigned fail){
 destination=buffer;capacity=count*512;expectedSector=sector;expectedCount=count;failAt=fail;
 sdCalls=usbCalls=maxSd=maxUsb=bad=selected=deselected=cbws=csws=resets=usbOffset=0;__sd0_sdhc=sdhc;
 memset(sdBounce,0xa7,sizeof(sdBounce));memset(usbBounce,0xb6,sizeof(usbBounce));
 return usb?USBStorage_ReadSectors(sector,count,buffer):sdio_ReadSectors(sector,count,buffer);
}
API unsigned stat(unsigned key){switch(key){case 0:return sdCalls;case 1:return usbCalls;case 2:return maxSd;case 3:return maxUsb;case 4:return bad;
 case 5:return selected;case 6:return deselected;case 7:return cbws;case 8:return csws;default:return resets;}}
API unsigned guards(void){for(unsigned i=0;i<32;++i)if(sdBounce[i]!=0xa7||sdBounce[65568+i]!=0xa7||usbBounce[i]!=0xb6||usbBounce[16416+i]!=0xb6)return 0;return 1;}
"""

class StorageReadBatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  compiler=ROOT/'toolchain/clang.exe'
  if not compiler.exists():raise unittest.SkipTest('Bundled Windows compiler required')
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-storage-batch-');cls.addClassCleanup(cls.temp.cleanup)
  source=FIXTURE
  for leaf,signature in [('SDI.c','bool sdio_ReadSectors('),('usbstorage.c','static s32 __cycle('),('usbstorage.c','bool USBStorage_ReadSectors(')]:
   source+=function_source(ROOT/'launcher/kernel'/leaf,signature)
  path=Path(cls.temp.name)/'batch.c';path.write_text(source+EXPORTS);dll=path.with_suffix('.dll')
  subprocess.run([str(compiler),'--target=x86_64-pc-windows-msvc','-std=c11','-shared','-nostdlib','-fno-builtin','-O2','-fuse-ld=lld','-Wl,/noentry',str(path),'-o',str(dll)],check=True,capture_output=True)
  cls.lib=C.CDLL(str(dll));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
  cls.lib.take.argtypes=[C.c_uint,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
  kernel=C.windll.kernel32;kernel.VirtualAlloc.restype=C.c_void_p;kernel.VirtualAlloc.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint]
  cls.memory=kernel.VirtualAlloc(0x11000000,0x100000,0x3000,4)
  if not cls.memory:raise AssertionError('Could not map guarded MEM2-address transfer fixture')
  kernel.VirtualFree.argtypes=[C.c_void_p,C.c_size_t,C.c_uint];cls.addClassCleanup(lambda:kernel.VirtualFree(cls.memory,0,0x8000))
 def run_read(self,usb,count,*,unaligned=False,sdhc=1,fail=0):
  base=self.memory+32;pointer=base+int(unaligned);size=count*512;sector=0x1234
  C.memset(self.memory,0xd8,size+96)
  result=self.lib.take(usb,pointer,sector,count,sdhc,fail)
  self.assertEqual(C.string_at(pointer-32,32),b'\xd8'*32)
  self.assertEqual(C.string_at(pointer+size,32),b'\xd8'*32)
  self.assertEqual(self.lib.guards(),1);self.assertEqual(self.lib.stat(4),0)
  if not fail:
   expected=bytes(((v^(v>>8)^(v>>16))&255) for v in range(sector*512,sector*512+size))
   self.assertEqual(C.string_at(pointer,size),expected)
   self.assertEqual(result,1)
  else:self.assertEqual(result,0)
  return result
 def test_sd_aligned_batch_uses_one_command_and_exact_sector_count(self):
  for count in (1,127,128,129,256,257,1024):
   with self.subTest(count=count):
    self.run_read(0,count);self.assertEqual(self.lib.stat(0),1);self.assertEqual(self.lib.stat(2),count*512)
    self.assertEqual((self.lib.stat(5),self.lib.stat(6)),(1,1))
 def test_sd_unaligned_batch_keeps_existing_64k_bounce_limit(self):
  for count in (127,128,129,256,257):
   with self.subTest(count=count):
    self.run_read(0,count,unaligned=True);self.assertEqual(self.lib.stat(0),(count+127)//128);self.assertLessEqual(self.lib.stat(2),65536)
 def test_standard_sd_byte_addressing_and_sdhc_lba_both_preserve_data(self):
  for sdhc in (0,1):
   for unaligned in (False,True):self.run_read(0,256,unaligned=unaligned,sdhc=sdhc)
 def test_sd_read_errors_do_not_overrun_or_skip_deselect(self):
  for unaligned,fail in ((False,1),(True,1),(True,2)):
   self.run_read(0,256,unaligned=unaligned,fail=fail);self.assertEqual(self.lib.stat(6),1)
 def test_usb_read10_keeps_sector_count_and_16k_transfers(self):
  for count in (128,256,257):
   for unaligned in (False,True):
    with self.subTest(count=count,unaligned=unaligned):
     self.run_read(1,count,unaligned=unaligned);self.assertEqual(self.lib.stat(1),(count*512+16383)//16384)
     self.assertLessEqual(self.lib.stat(3),16384);self.assertEqual((self.lib.stat(7),self.lib.stat(8)),(1,1))
 def test_usb_transfer_timeout_fails_cleanly_with_fixed_bounce_buffer(self):
  for unaligned in (False,True):
   self.run_read(1,256,unaligned=unaligned,fail=3);self.assertEqual(self.lib.stat(8),0);self.assertEqual(self.lib.stat(9),1)

if __name__=='__main__':unittest.main()
