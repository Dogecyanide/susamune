"""Actual ARM storage state machine with deferred networking and in-memory FAT."""
import ctypes as C
import hashlib
import unittest
import test_ghost_kernel_paging as kernel
from test_ghost_format import build_ghost
from test_ghost_service import Entry

class ServiceStorageTests(kernel.GhostKernelPagingTests):
    bridge_source = r'''
__declspec(dllexport) void webSet(const u8 *data,u32 size,int result) {
 webEnabled=true;webHold=webCancelled=false;webData=data;webSize=size;webResult=result;webRelease=0;
}
__declspec(dllexport) void holdWeb(u32 value) { webHold=value!=0; }
__declspec(dllexport) int retireWeb(void) { return SusamuneGhostRetire(); }
__declspec(dllexport) u32 releasedWeb(void) { return webRelease; }
__declspec(dllexport) int accountStore(u32 linked) {
 memset(&WebAccount.secret,0,sizeof(WebAccount.secret));
 if(linked){memset(WebAccount.secret.access,'a',47);memcpy(WebAccount.secret.access,"dga_",4);
  memset(WebAccount.secret.refresh,'r',47);memcpy(WebAccount.secret.refresh,"dgr_",4);strcpy(WebAccount.secret.user,"runner");}
 return WebAccountStore(linked!=0);
}
__declspec(dllexport) int accountReload(void) {
 memset(&WebAccount,0,sizeof(WebAccount));WebAccountLoaded=false;WebAccountGeneration=WebAccountBank=0;
 int r=WebAccountLoad();return r?-r:GhostAccountSecretValid(&WebAccount.secret);
}
'''
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dll.webSet.argtypes=[C.c_void_p,C.c_uint,C.c_int]
    def setUp(self):
        super().setUp()
        self.dll.webSet(None,0,0)
    def download(self,ghost=None,error=0):
        ghost=ghost or build_ghost()
        data=C.create_string_buffer(ghost);self.buffers.append(data)
        self.dll.webSet(data,len(ghost),error)
        e=Entry();e.bytes=len(ghost);e.path=b'/storage/v1/object/public/ghosts/test.smsghost'
        digest=hashlib.sha256(ghost).digest();e.sha256[:]=digest
        path=kernel.IMPORT+'g_'+digest.hex()+'.smsghost'
        return e,ghost,path
    def test_verified_download_installs_only_complete_file(self):
        e,ghost,path=self.download()
        result=self.request(8,profile=4,payload=bytes(e))
        self.assertEqual(result['status'],0)
        self.assertEqual(self.file(path),ghost)
        self.assertIsNone(self.file(kernel.IMPORT+'download.tmp'))
        self.assertEqual(self.dll.releasedWeb(),1)
        self.assertEqual(self.request(8,profile=4,payload=bytes(e))['status'],-10)
        self.assertEqual(self.file(path),ghost)
    def test_account_survives_restart_and_rotation_barrier(self):
        self.assertEqual(self.dll.accountStore(1),0)
        self.assertEqual(self.dll.accountReload(),1)
        self.assertEqual(self.dll.accountStore(0),0)
        self.assertEqual(self.dll.accountReload(),0)
        self.assertEqual(self.dll.accountStore(1),0)
        self.assertEqual(self.dll.accountReload(),1)
    def test_account_failed_sync_preserves_previous_journal(self):
        self.assertEqual(self.dll.accountStore(1),0)
        original=self.file('/Moonshine data/delfino-link-b.bin')
        self.dll.writeFailure(0xffffffff,1)
        self.assertNotEqual(self.dll.accountStore(0),0)
        self.assertEqual(self.file('/Moonshine data/delfino-link-b.bin'),original)
        self.assertEqual(self.dll.accountReload(),1)
    def test_corrupt_account_is_preserved_and_not_used(self):
        self.assertEqual(self.dll.accountStore(1),0)
        self.assertEqual(self.dll.accountStore(0),0)
        broken=b'broken account journal';self.add('/Moonshine data/delfino-link-a.bin',broken)
        self.assertLess(self.dll.accountReload(),0)
        self.assertEqual(self.file('/Moonshine data/delfino-link-a.bin'),broken)
    def test_bad_hash_never_published(self):
        e,ghost,path=self.download(error=-25)
        self.assertEqual(self.request(8,profile=4,payload=bytes(e))['status'],-25)
        self.assertIsNone(self.file(path));self.assertIsNone(self.file(kernel.IMPORT+'download.tmp'))
    def test_local_validation_still_required(self):
        ghost=bytearray(build_ghost());ghost[-1]^=1
        e,_,path=self.download(bytes(ghost))
        self.assertEqual(self.request(8,profile=4,payload=bytes(e))['status'],-4)
        self.assertIsNone(self.file(path))
    def test_failed_write_preserves_existing_files(self):
        e,_,path=self.download();self.add(kernel.IMPORT+'existing.smsghost',b'existing')
        self.dll.writeFailure(60,0)
        self.assertNotEqual(self.request(8,profile=4,payload=bytes(e))['status'],0)
        self.assertIsNone(self.file(path));self.assertEqual(self.file(kernel.IMPORT+'existing.smsghost'),b'existing')
    def test_retirement_waits_for_network_owner(self):
        e,_,path=self.download();self.dll.holdWeb(1)
        self.dll.submit(8,4,0,bytes(e),C.sizeof(e),0)
        self.assertEqual(self.dll.run(1),-1)
        self.assertEqual(self.dll.retireWeb(),0)
        self.assertEqual(self.dll.releasedWeb(),0)
        self.dll.holdWeb(0)
        self.assertEqual(self.dll.retireWeb(),1)
        self.assertEqual(self.dll.releasedWeb(),1)
        self.assertIsNone(self.file(path))

if __name__=='__main__':unittest.main()
