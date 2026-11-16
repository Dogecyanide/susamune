"""Verify kernel-only forward allocation hints preserve filesystem semantics."""
from pathlib import Path
import sys,ctypes as C,subprocess,tempfile,unittest,hashlib,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from test_fatfs_lfn_create import FIXTURE
EXTRA=r"""
static unsigned lastWritten;
static void dword(unsigned offset,DWORD value){word(offset,value);word(offset+2,value>>16);}
API int format(unsigned fat32){
 f_mount(0,drive,0);memset(image,0,sizeof(image));writeProtected=failRead=failWrite=reads=writes=0;
 image[0]=0xeb;image[1]=0x58;image[2]=0x90;memcpy(image+3,"MSDOS5.0",8);word(11,512);image[13]=1;
 image[16]=1;image[21]=0xf8;word(24,32);word(26,64);word(510,0xaa55);
 if(fat32){
  word(14,32);dword(32,70000);dword(36,600);dword(44,2);word(48,1);word(50,6);image[66]=0x29;memcpy(image+82,"FAT32   ",8);
  dword(32*512,0x0ffffff8);dword(32*512+4,0x0fffffff);dword(32*512+8,0x0fffffff);
  dword(512,0x41615252);dword(512+484,0x61417272);dword(512+488,0xffffffff);dword(512+492,0xffffffff);word(512+510,0xaa55);
 }else{
  word(14,1);word(17,512);word(19,8192);word(22,32);image[38]=0x29;memcpy(image+54,"FAT16   ",8);word(512,0xfff8);word(514,0xffff);
 }
 return remount();
}
API int pattern(const char*path,unsigned count,unsigned byte,unsigned mode){
 TCHAR p[256];FIL f;static BYTE data[16384];UINT done;FRESULT result;lastWritten=0;
 if(!pathOf(path,p))return FR_INVALID_NAME;memset(data,byte,sizeof(data));
 result=f_open(&f,p,FA_READ|FA_WRITE|mode);if(result)return result;
 while(count){unsigned chunk=count<sizeof(data)?count:sizeof(data);result=f_write(&f,data,chunk,&done);lastWritten+=done;if(result||done!=chunk)break;count-=done;}
 FRESULT closed=f_close(&f);return result?result:closed;
}
API unsigned written(void){return lastWritten;}
API int at(const char*path,unsigned offset,unsigned count,BYTE*out){
 TCHAR p[256];FIL f;UINT done=0;FRESULT result;if(!pathOf(path,p))return -FR_INVALID_NAME;
 result=f_open(&f,p,FA_READ);if(result)return -result;result=f_lseek(&f,offset);if(!result)result=f_read(&f,out,count,&done);FRESULT closed=f_close(&f);return result?-result:closed?-closed:(int)done;
}
API int sizeOf(const char*path){TCHAR p[256];FILINFO info;if(!pathOf(path,p))return -FR_INVALID_NAME;int r=f_stat(p,&info);return r?-r:(int)info.fsize;}
API unsigned head(const char*path){TCHAR p[256];FIL f;DWORD head;if(!pathOf(path,p)||f_open(&f,p,FA_READ))return 0;head=f.obj.sclust;f_close(&f);return head;}
API unsigned meta(unsigned key){switch(key){case 0:return volume.last_clst;case 1:return volume.n_fatent;case 2:return volume.fs_type;default:return writes;}}
API void hint(unsigned value){volume.last_clst=value;}
API int freeCount(void){DWORD n;FATFS*f;int r=f_getfree(drive,&n,&f);return r?-r:(int)n;}
API int readOnly(const char*path){
 TCHAR p[256];FIL f;DWORD sector,offset;int r;if(!pathOf(path,p))return FR_INVALID_NAME;r=f_open(&f,p,FA_READ);if(r)return r;
 sector=f.dir_sect;offset=(DWORD)(f.dir_ptr-volume.win);r=f_close(&f);if(r)return r;image[sector*512+offset+11]|=AM_RDO;volume.winsect=0xffffffff;return 0;
}
API int corrupt(const char*path){
 DWORD cluster=head(path);if(!cluster)return FR_NO_FILE;unsigned address=volume.fatbase*512+cluster*(volume.fs_type==FS_FAT32?4:2);
 if(volume.fs_type==FS_FAT32)dword(address,1);else word(address,1);volume.winsect=0xffffffff;return 0;
}
"""

def compile_lib(folder,policy):
 folder.mkdir();production=(ROOT/'launcher/fatfs/ff.c').read_text()
 if production.count('MOONSHINE_FATFS_FORWARD_ALLOC_HINT')!=1:raise AssertionError('Production hint policy is missing or ambiguous')
 (folder/'variant.c').write_text(production)
 source=FIXTURE.replace('#define SECTORS 8192','#define SECTORS 70000').replace('word(19,SECTORS);','word(19,8192);')+EXTRA
 if policy=='loader':source=source.replace('DiskReadFunc disk_read=readDisk;\nDiskWriteFunc disk_write=writeDisk;', 'DRESULT disk_read(BYTE d,BYTE*p,DWORD s,UINT n){return readDisk(d,p,s,n); }\nDRESULT disk_write(BYTE d,const BYTE*p,DWORD s,UINT n){return writeDisk(d,p,s,n);}')
 (folder/'test.c').write_text(source,encoding='utf-8');dll=folder/'test.dll'
 flags=['-DMOONSHINE_FATFS_FORWARD_ALLOC_HINT=1'] if policy!='base' else []
 if policy=='loader':flags+=['-D__PPC__']
 result=subprocess.run([str(ROOT/'toolchain/clang.exe'),'--target=x86_64-pc-windows-msvc','-U_WIN32','-std=c11','-shared','-nostdlib','-fno-builtin','-mno-stack-arg-probe','-O2','-fuse-ld=lld','-Wl,/noentry','-I',str(ROOT/'launcher/fatfs'),*flags,str(folder/'test.c'),str(ROOT/'launcher/fatfs/option/ccsbcs.c'),'-o',str(dll)],capture_output=True,text=True)
 if result.returncode:raise AssertionError(result.stderr)
 lib=C.CDLL(str(dll));lib.pattern.argtypes=[C.c_char_p,C.c_uint,C.c_uint,C.c_uint];lib.at.argtypes=[C.c_char_p,C.c_uint,C.c_uint,C.c_void_p]
 for name in ('sizeOf','head','deleteFile','readOnly','corrupt'):getattr(lib,name).argtypes=[C.c_char_p]
 lib.imageBytes.restype=C.c_void_p;return lib

A=b'0:/A.BIN';B=b'0:/B.BIN';CFILE=b'0:/C.BIN';D=b'0:/D.BIN';TRACE=b'0:/TRACE.BIN';FILL=b'0:/FILL.BIN'
class AllocationHintTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if sys.platform!='win32' or not (ROOT/'toolchain/clang.exe').exists():raise unittest.SkipTest('Bundled Windows compiler required')
  cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-allocation-hint-');cls.addClassCleanup(cls.temp.cleanup)
  cls.libs={}
  for policy in ('base','forward','loader'):
   lib=compile_lib(Path(cls.temp.name)/policy,policy);cls.libs[policy]=lib
   cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
 def reset(self,lib,fat32):self.assertEqual(lib.format(fat32),0);self.assertEqual(lib.meta(2),3 if fat32 else 2)
 def put(self,lib,name,count,byte,mode=4):
  self.assertEqual(lib.pattern(name,count,byte,mode),0);self.assertEqual(lib.written(),count)
 def take(self,lib,name,offset,count,byte):
  data=C.create_string_buffer(count+64);C.memset(data,0xa7,len(data));n=lib.at(name,offset,count,C.byref(data,32));self.assertEqual(n,count)
  self.assertEqual(data.raw[:32],b'\xa7'*32);self.assertEqual(data.raw[32:32+count],bytes([byte])*count);self.assertEqual(data.raw[32+count:],b'\xa7'*32)
 def gap(self,lib,fat32):
  self.reset(lib,fat32);self.put(lib,A,64,0xa5);head=lib.head(A);self.put(lib,B,1024*1024,0xb6);return head
 def full(self,lib):
  self.assertEqual(lib.pattern(FILL,64*1024*1024,0x6a,4),0);self.assertGreater(lib.written(),0);self.assertEqual(lib.freeCount(),0)
 def test_valid_forward_hint_avoids_repeated_gap_without_data_or_free_count_change(self):
  for fat32 in (0,1):
   results=[]
   for policy in ('base','forward'):
    lib=self.libs[policy];old=self.gap(lib,fat32);hint=lib.meta(0);free=lib.freeCount();self.put(lib,A,400,0xc7,8)
    self.assertGreater(lib.meta(0),hint) if policy=='forward' else self.assertLess(lib.meta(0),hint)
    self.put(lib,TRACE,64,0xd8);self.take(lib,A,0,400,0xc7);self.take(lib,B,1024*1024-32,32,0xb6);self.take(lib,TRACE,0,64,0xd8)
    results.append((lib.sizeOf(A),lib.sizeOf(B),lib.sizeOf(TRACE),lib.freeCount(),free))
    self.assertEqual(lib.remount(),0);self.take(lib,A,0,400,0xc7)
   self.assertEqual(results[0],results[1])
 def test_loader_retains_upstream_hole_reuse_even_with_define(self):
  for fat32 in (0,1):
   lib=self.libs['loader'];old=self.gap(lib,fat32);self.put(lib,A,512,0xc7,8);self.assertEqual(lib.head(A),old);self.take(lib,A,0,512,0xc7)
 def test_invalid_or_unknown_hint_still_uses_the_freed_hole(self):
  lib=self.libs['forward']
  for fat32 in (0,1):
   for invalid in (0,0xffffffff,'end'):
    old=self.gap(lib,fat32);lib.hint(lib.meta(1) if invalid=='end' else invalid);self.put(lib,A,512,0xc7,8);self.assertEqual(lib.head(A),old)
 def test_equal_cursor_keeps_upstream_immediate_hole_reuse(self):
  lib=self.libs['forward']
  for fat32 in (0,1):
   old=self.gap(lib,fat32);lib.hint(old);self.put(lib,A,400,0xc7,8);self.assertEqual(lib.head(A),old)
 def test_full_disk_wrap_reuses_the_only_freed_low_hole(self):
  for fat32 in (0,1):
   for policy in ('base','forward'):
    lib=self.libs[policy];self.reset(lib,fat32);self.put(lib,A,512,0xa5);head=lib.head(A);self.full(lib);size=lib.sizeOf(FILL)
    self.put(lib,A,512,0xc7,8);self.assertEqual(lib.head(A),head);self.assertEqual(lib.freeCount(),0)
    self.take(lib,A,0,512,0xc7);self.take(lib,FILL,size-32,32,0x6a)
 def test_fragmented_low_holes_are_all_reused_after_wrap(self):
  for fat32 in (0,1):
   for policy in ('base','forward'):
    lib=self.libs[policy];self.reset(lib,fat32)
    for path in (A,B,CFILE,D):self.put(lib,path,512,0xa5)
    self.full(lib);self.assertEqual(lib.deleteFile(B),0);self.assertEqual(lib.deleteFile(D),0);self.assertEqual(lib.freeCount(),2)
    self.put(lib,A,1536,0xc7,8);self.assertEqual(lib.freeCount(),0);self.take(lib,A,0,1536,0xc7);self.take(lib,CFILE,0,512,0xa5)
 def test_readonly_and_existing_create_new_preserve_every_disk_byte(self):
  for fat32 in (0,1):
   for policy in ('base','forward'):
    lib=self.libs[policy];self.gap(lib,fat32);self.assertEqual(lib.readOnly(A),0)
    before=hashlib.sha256(C.string_at(lib.imageBytes(),lib.imageSize())).digest();lib.faults(0,0,0)
    self.assertEqual(lib.pattern(A,64,0xc7,8),7);self.assertEqual(lib.pattern(B,64,0xc7,4),8);self.assertEqual(lib.statIo(1),0)
    self.assertEqual(hashlib.sha256(C.string_at(lib.imageBytes(),lib.imageSize())).digest(),before)
 def test_corrupt_chain_has_identical_error_and_disk_effects(self):
  for fat32 in (0,1):
   results=[]
   for policy in ('base','forward'):
    lib=self.libs[policy];self.reset(lib,fat32);self.put(lib,A,1024,0xa5);self.put(lib,B,512,0xb6);self.assertEqual(lib.corrupt(A),0)
    result=lib.pattern(A,64,0xc7,8);self.assertEqual(result,2);self.take(lib,B,0,512,0xb6)
    results.append(hashlib.sha256(C.string_at(lib.imageBytes(),lib.imageSize())).hexdigest())
   self.assertEqual(results[0],results[1])
 def test_read_and_write_errors_match_upstream_protection(self):
  for fat32 in (0,1):
   for readFail,writeFail in ((1,0),(0,1)):
    results=[]
    for policy in ('base','forward'):
     lib=self.libs[policy];self.gap(lib,fat32);lib.faults(readFail,writeFail,0);result=lib.pattern(A,64,0xc7,8);self.assertEqual(result,1)
     results.append(hashlib.sha256(C.string_at(lib.imageBytes(),lib.imageSize())).hexdigest())
    self.assertEqual(results[0],results[1])
 def test_preprocessor_does_not_change_exfat_allocation_branch(self):
  source=(ROOT/'launcher/fatfs/ff.c').read_text();start=source.index('fp->obj.sclust = ld_dword(fs->dirbuf + XDIR_FstClus)');end=source.index('/* Clean directory info */',start)
  self.assertNotIn('MOONSHINE_FATFS_FORWARD_ALLOC_HINT',source[start:end]);self.assertIn('fs->last_clst = fp->obj.sclust - 1;',source[start:end])
if __name__=='__main__':unittest.main()
