"""Reproduce FIL attribute poisoning with the bundled FatFs on an in-memory disk."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FatFsAttributesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-fatfs-attributes-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "attributes.c"
        source.write_text(r'''
#include "ff.h"
#include "diskio.h"
void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){BYTE*a=d;const BYTE*b=s;while(n--)*a++=*b++;return d;}
void *memset(void*d,int v,__SIZE_TYPE__ n){BYTE*a=d;while(n--)*a++=(BYTE)v;return d;}
static BYTE disk[8192*512];
static FATFS volume;
static FIL file;
static FILINFO info;
static const TCHAR drive[]={'0',':',0};
static const TCHAR path[]={'0',':','/','s','u','s','a','m','u','n','e','.','i','n','i',0};
static unsigned writes;
DSTATUS disk_initialize(BYTE drive){return drive?STA_NODISK:0;}
DSTATUS disk_status(BYTE drive){return disk_initialize(drive);}
DRESULT disk_read(BYTE drive,BYTE*out,DWORD sector,UINT count){
 if(drive||sector>=8192||count>8192-sector)return RES_PARERR;
 memcpy(out,disk+sector*512,count*512);return RES_OK;
}
DRESULT disk_write(BYTE drive,const BYTE*in,DWORD sector,UINT count){
 if(drive||sector>=8192||count>8192-sector)return RES_PARERR;
 memcpy(disk+sector*512,in,count*512);writes++;return RES_OK;
}
DRESULT disk_ioctl(BYTE drive,BYTE cmd,void*out){
 if(drive)return RES_PARERR;
 if(cmd==CTRL_SYNC)return RES_OK;
 if(cmd==GET_SECTOR_SIZE){*(WORD*)out=512;return RES_OK;}
 if(cmd==GET_SECTOR_COUNT){*(DWORD*)out=8192;return RES_OK;}
 if(cmd==GET_BLOCK_SIZE){*(DWORD*)out=1;return RES_OK;}
 return RES_PARERR;
}
DWORD get_fattime(void){return (46u<<25)|(9u<<21)|(9u<<16);}
static void word(unsigned offset,WORD value){disk[offset]=value;disk[offset+1]=value>>8;}
__declspec(dllexport) int probe(unsigned poison,unsigned readonly){
 UINT written;int ret;
 f_mount(0,drive,0);memset(disk,0,sizeof(disk));memset(&volume,0,sizeof(volume));
 disk[0]=0xeb;disk[1]=0x3c;disk[2]=0x90;
 memcpy(disk+3,"MSDOS5.0",8);word(11,512);disk[13]=1;word(14,1);disk[16]=1;
 word(17,512);word(19,8192);disk[21]=0xf8;word(22,32);word(24,32);word(26,64);
 disk[38]=0x29;memcpy(disk+54,"FAT16   ",8);word(510,0xaa55);
 word(512,0xfff8);word(514,0xffff);
 if((ret=f_mount(&volume,drive,1)))return -100-ret;
 if((ret=f_open(&file,path,FA_CREATE_ALWAYS|FA_WRITE)))return -200-ret;
 if((ret=f_write(&file,"[creation_pal]\r\n",16,&written))||written!=16)return -300-ret;
 if((ret=f_close(&file)))return -400-ret;
 unsigned entry=33*512;
 for(;entry<65*512;entry+=32){
  unsigned i=0;while(i<11&&disk[entry+i]==(BYTE)"SUSAMUNEINI"[i])i++;
  if(i==11)break;
 }
 if(entry==65*512)return -500;
 disk[entry+11]=(disk[entry+11]&~AM_RDO)|(readonly?AM_RDO:0);
 if((ret=f_mount(0,drive,0)))return -510-ret;
 if((ret=f_mount(&volume,drive,1)))return -520-ret;
 memset(&file,poison,sizeof(file));writes=0;
 if((ret=f_open(&file,path,FA_READ|FA_OPEN_EXISTING)))return -600-ret;
 if((ret=f_stat(path,&info)))return -700-ret;
 unsigned attributes=file.obj.attr|((unsigned)info.fattrib<<8);
 if((ret=f_close(&file)))return -800-ret;
 if(writes)return -900;
 return attributes;
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        fatfs = ROOT / "launcher/fatfs"
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-U_WIN32",
                                 "-D__PPC__", "-shared", "-nostdlib", "-fno-builtin", "-O2",
                                 "-fuse-ld=lld", "-Wl,/noentry", "-I", str(fatfs), str(source),
                                 str(fatfs / "ff.c"), str(fatfs / "option/ccsbcs.c"),
                                 "-o", str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.probe.argtypes = [C.c_uint, C.c_uint]
        cls.lib.probe.restype = C.c_int

    def test_opened_file_attr_retains_poison_but_stat_reads_real_attributes(self):
        for readonly in (0, 1):
            for poison in (0, 1, 0x20, 0xa5, 0xff):
                with self.subTest(readonly=readonly, poison=poison):
                    result = self.lib.probe(poison, readonly)
                    self.assertGreaterEqual(result, 0)
                    self.assertEqual(result & 0xff, poison)
                    self.assertEqual((result >> 8) & 1, readonly)


if __name__ == "__main__":
    unittest.main()
