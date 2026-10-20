"""Keep recycled private ghost packets out of saved native render graphs."""
import ctypes as C
import _ctypes
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class GhostSnapshotPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = (ROOT / 'src/ghost_model.cpp').read_text()
        cls.save = (ROOT / 'src/savestate.cpp').read_text()
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-snapshot-packets-')
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        code = r'''
typedef unsigned u32;
typedef unsigned char u8;
struct J3DPacket {u32 *vTable;J3DPacket *mParentPacket,*mChildPacket;};
struct J3DShapePacket : J3DPacket {};
struct J3DMatPacket : J3DPacket {J3DShapePacket *mShapePacket;};
struct J3DDrawBuffer {J3DPacket **mFrames;u32 mSize;J3DPacket *mPacket;};
u32 ghostMaterialPacketVtable[1],shapeVtable[1];
J3DMatPacket nativeMat[3],ghostMat[3];
J3DShapePacket nativeShape[3],ghostShape[3];
J3DPacket *heads[4];
J3DDrawBuffer buffer;
bool inside(const void*p,const void*b,unsigned long long n,unsigned long long size){
 auto a=(unsigned long long)p,start=(unsigned long long)b;
 return a>=start&&a-start<=n&&size<=n-(a-start);
}
bool privateGhostPacket(const void*p){return inside(p,ghostMat,sizeof(ghostMat),1)||inside(p,ghostShape,sizeof(ghostShape),1);}
bool readableGhostQueue(const void*p,u32 n){
 return inside(p,nativeMat,sizeof(nativeMat),n)||inside(p,ghostMat,sizeof(ghostMat),n)||
 inside(p,nativeShape,sizeof(nativeShape),n)||inside(p,ghostShape,sizeof(ghostShape),n)||
 inside(p,heads,sizeof(heads),n)||inside(p,&buffer,sizeof(buffer),n);
}
'''
        code += '\n'.join(function(cls.model, name) for name in
                          ('onlyGhostPackets', 'stripGhostPacketList', 'stripGhostDrawBuffer'))
        code += r'''
void reset(){
 for(u32 i=0;i<3;++i){nativeMat[i]={};ghostMat[i]={};nativeShape[i]={};ghostShape[i]={};
 nativeMat[i].vTable=ghostMat[i].vTable=ghostMaterialPacketVtable;
 nativeShape[i].vTable=ghostShape[i].vTable=shapeVtable;
 nativeMat[i].mShapePacket=&nativeShape[i];ghostMat[i].mShapePacket=&ghostShape[i];}
 for(u32 i=0;i<4;++i)heads[i]=nullptr;
 buffer={heads,4,nullptr};
}
bool drawNative(J3DPacket*p,u32&count,u32&budget){
 for(;p;p=p->mParentPacket){
  if(!budget--||privateGhostPacket(p)||!readableGhostQueue(p,sizeof(J3DPacket)))return false;
  ++count;
  if(!drawNative(p->mChildPacket,count,budget))return false;
  if(p->vTable==ghostMaterialPacketVtable&&!drawNative(static_cast<J3DMatPacket*>(p)->mShapePacket,count,budget))return false;
 }
 return true;
}
extern "C" __declspec(dllexport) int scenario(u32 which){
 reset();u32 budget=512;
 if(which==0||which==1){
  // Save while a native material contains a merged ghost shape and the
  // material chain contains private attachments between native objects.
  heads[0]=&nativeMat[0];nativeMat[0].mParentPacket=&ghostMat[0];
  ghostMat[0].mParentPacket=&nativeMat[1];nativeMat[1].mParentPacket=&ghostMat[1];
  nativeMat[0].mShapePacket=&ghostShape[2];ghostShape[2].mParentPacket=&nativeShape[0];
  if(which&&!stripGhostDrawBuffer(&buffer,budget))return 10;
  J3DMatPacket saved[3];J3DShapePacket savedShapes[3];J3DPacket*savedHeads[4];
  for(u32 i=0;i<3;++i){saved[i]=nativeMat[i];savedShapes[i]=nativeShape[i];}
  for(u32 i=0;i<4;++i)savedHeads[i]=heads[i];
  // A remote nozzle/item change recycles this arena between Save and Load.
  for(u32 i=0;i<3;++i){ghostMat[i].vTable=(u32*)0x4035da3e;ghostMat[i].mParentPacket=(J3DPacket*)0x4035da4e;
   ghostShape[i].vTable=(u32*)0x4035da3e;ghostShape[i].mParentPacket=(J3DPacket*)0x4035da4e;nativeMat[i]={};}
  for(u32 i=0;i<3;++i){nativeMat[i]=saved[i];nativeShape[i]=savedShapes[i];}
  for(u32 i=0;i<4;++i)heads[i]=savedHeads[i];
  u32 count=0;budget=32;const bool safe=drawNative(heads[0],count,budget);
  return which?(safe&&count==4?0:11):(!safe?0:12);
 }
 if(which==2){
  heads[0]=&ghostMat[0];ghostMat[0].mParentPacket=&ghostMat[1];ghostMat[1].mParentPacket=&nativeMat[0];
  nativeMat[0].mParentPacket=&ghostMat[2];
  if(!stripGhostDrawBuffer(&buffer,budget)||heads[0]!=&nativeMat[0]||nativeMat[0].mParentPacket)return 20;
  // The same queue owner can be visited twice without deleting native work.
  if(!stripGhostDrawBuffer(&buffer,budget)||heads[0]!=&nativeMat[0])return 21;
  return 0;
 }
 if(which==3){
  buffer.mPacket=&nativeShape[0];nativeShape[0].mChildPacket=&ghostShape[0];
  ghostShape[0].mParentPacket=&nativeShape[1];nativeShape[1].mParentPacket=&ghostShape[1];
  return stripGhostDrawBuffer(&buffer,budget)&&nativeShape[0].mChildPacket==&nativeShape[1]&&
         !nativeShape[1].mParentPacket?0:30;
 }
 if(which==4){
  heads[0]=&nativeMat[0];nativeMat[0].mShapePacket=&ghostShape[0];
  return stripGhostDrawBuffer(&buffer,budget)&&heads[0]==&nativeMat[0]&&!nativeMat[0].mShapePacket?0:40;
 }
 if(which==5){
  heads[0]=&ghostMat[0];ghostMat[0].mShapePacket=&nativeShape[0];
  // Unexpected ordering must refuse Save rather than discard a native shape.
  return !stripGhostDrawBuffer(&buffer,budget)&&heads[0]==&ghostMat[0]?0:50;
 }
 if(which==6){
  heads[0]=&nativeMat[0];nativeMat[0].mParentPacket=&nativeMat[0];budget=8;
  return !stripGhostDrawBuffer(&buffer,budget)&&budget==0?0:60;
 }
 if(which==7){
  heads[0]=(J3DPacket*)0x4035da4e;
  return !stripGhostDrawBuffer(&buffer,budget)?0:70;
 }
 if(which==8){
  heads[0]=&ghostMat[0];ghostMat[0].mShapePacket=&ghostShape[0];ghostShape[0].mParentPacket=&ghostShape[0];budget=8;
  return !stripGhostDrawBuffer(&buffer,budget)&&budget==0?0:80;
 }
 return 99;
}
'''
        cpp, dll = directory / 'test.cpp', directory / 'test.dll'
        cpp.write_text(code)
        subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                        '-shared', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry',
                        '-O2', str(cpp), '-o', str(dll)], check=True, capture_output=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))
        cls.lib.scenario.argtypes = [C.c_uint]

    def test_saved_native_graph_survives_attachment_arena_recycling(self):
        for index in (0, 1):
            with self.subTest(filtered=bool(index)):
                self.assertEqual(self.lib.scenario(index), 0)

    def test_head_tail_and_duplicate_owner_preserve_native_materials(self):
        self.assertEqual(self.lib.scenario(2), 0)

    def test_child_and_merged_shape_lists_preserve_native_work(self):
        for index in (3, 4):
            self.assertEqual(self.lib.scenario(index), 0)

    def test_unexpected_native_child_of_private_material_refuses_capture(self):
        self.assertEqual(self.lib.scenario(5), 0)

    def test_cycles_and_invalid_links_fail_without_unbounded_traversal(self):
        for index in (6, 7, 8):
            self.assertEqual(self.lib.scenario(index), 0)

    def test_capture_boundary_and_unsafe_legacy_snapshot_version(self):
        save = function(self.save, 'SavestateManager::saveSlotExplicit')
        self.assertLess(save.index('GXDrawDone()'), save.index('GhostModel::prepareSavestate()'))
        self.assertLess(save.index('GhostModel::prepareSavestate()'), save.index('captureRegion('))
        self.assertIn('const u32 kSnapshotVersion = 18u;', self.save)
        self.assertIn('file.snapshotVersion != kSnapshotVersion', self.save)
        self.assertIn('h->version != kSnapshotVersion', self.save)
        self.assertIn('Savestate is from another build', self.save)


if __name__ == '__main__':
    unittest.main()
