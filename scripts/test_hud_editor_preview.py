"""Exercise real counter-preview scopes, including hidden retail animation bounds."""
import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HudPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-hud-preview-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = (ROOT / "src/hud_editor_preview.cpp").read_text()
        source = re.sub(r"^#(?:include|pragma)[^\n]*", "", source, flags=re.M)
        # Host pointers are 64-bit; decode the console's 32-bit offset table in the fixture.
        source = source.replace(
            "const u8 *wrapper = *reinterpret_cast<const u8 *const *>(\n"
            "        reinterpret_cast<const u8 *>(console) + offset);",
            "const u8 *wrapper = console->wrapper(offset);")
        code = r'''
#include "susamune/susamune_cfg.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
extern "C" void*memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void*memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
struct JUTRect {int mX1,mY1,mX2,mY2;};
struct JSUPtrList;
struct JSUPtrLink {void*mItemPtr;JSUPtrList*mParentList;JSUPtrLink*mNextLink;};
struct JSUPtrList {JSUPtrLink*mFirst;};
struct J2DPane {u8 prefix[0x14];JUTRect mRect;u8 geometry[0x90];u32 _B4;
 u8 mAlpha,mAlphaCopy;bool mIsVisible;JSUPtrList mChildrenList;JSUPtrLink mPtrLink;};
struct J2DScreen:J2DPane {J2DPane*root,*timer;u32 tag;J2DPane*search(u32 t){return t=='\0t_0'?timer:tag==t?root:nullptr;}};
struct Wrapper {void*vptr;J2DPane*pane;JUTRect bounds;};
struct TGCConsole2 {J2DScreen*mMainScreen;unsigned offsets[12];const u8*pointers[12];unsigned count;
 const u8*wrapper(unsigned offset){for(unsigned i=0;i<count;i++)if(offsets[i]==offset)return pointers[i];return nullptr;}};
'''
        code += source
        code += r'''
using namespace HudEditorPreview;
static J2DScreen screen;
static J2DPane children[12];
static J2DPane ancestors[2];
static J2DPane timer;
static u8 before[sizeof(screen)+sizeof(children)+sizeof(ancestors)+sizeof(timer)];
static bool equal(const void*a,const void*b,unsigned n){const u8*x=(const u8*)a,*y=(const u8*)b;while(n--)if(*x++!=*y++)return false;return true;}
static void link(J2DPane&parent,J2DPane&child){child.mPtrLink.mItemPtr=&child;child.mPtrLink.mParentList=&parent.mChildrenList;
 child.mPtrLink.mNextLink=parent.mChildrenList.mFirst;parent.mChildrenList.mFirst=&child.mPtrLink;}
extern "C" __declspec(dllexport) unsigned redOffset(unsigned which){return which?kCounters[1].last:kCounters[1].root;}
extern "C" __declspec(dllexport) int run(unsigned color,unsigned fault,unsigned depth,unsigned timerVisible){
 memset(&screen,0,sizeof(screen));memset(children,0,sizeof(children));memset(ancestors,0,sizeof(ancestors));memset(&timer,0,sizeof(timer));
 timer.mIsVisible=timerVisible;timer.mAlpha=77;screen.timer=&timer;
 const unsigned index=color==SUSAMUNE_CREATION_LIFE_TEXT?3:color-SUSAMUNE_CREATION_COIN_BG;
 const Counter&counter=kCounters[index];screen.root=children;screen.tag=counter.tag;
 J2DPane*parent=&screen;
 for(unsigned i=0;i<depth;i++){link(*parent,ancestors[i]);parent=&ancestors[i];}
 link(*parent,timer);
 link(*parent,children[0]);unsigned count=1;
 for(unsigned offset=counter.first;offset<=counter.last;offset+=4)link(children[0],children[count++]);
 Wrapper bindings[12]={};TGCConsole2 console={};console.mMainScreen=&screen;console.count=count;
 for(unsigned i=0;i<count;i++){
  console.offsets[i]=i?counter.first+(i-1)*4:counter.root;
  bindings[i].vptr=(void*)0x1234;bindings[i].pane=children+i;bindings[i].bounds={int(i*10),int(i*5),int(i*10+20),int(i*5+30)};
  if(i==0&&index==1){bindings[i].bounds.mY1=419;bindings[i].bounds.mY2=449;}
  console.pointers[i]=(const u8*)(i&1?(void*)&bindings[i].pane:(void*)&bindings[i]);
  children[i].mRect={20,525,60,600};children[i].mAlpha=0;children[i].mAlphaCopy=37;
  memset(children[i].geometry,0x35+i,sizeof(children[i].geometry));
 }
 if(fault==1)children[1].mPtrLink.mParentList=nullptr;
 if(fault==2)children[1].mPtrLink.mNextLink=&children[1].mPtrLink;
 if(fault==3){for(unsigned i=count;i<12;i++)link(children[0],children[i]);}
 if(fault==4)children[0].mPtrLink.mParentList=nullptr;
 if(fault==5&&depth)ancestors[0].mPtrLink.mParentList=&children[0].mChildrenList;
 memcpy(before,&screen,sizeof(screen));memcpy(before+sizeof(screen),children,sizeof(children));
 memcpy(before+sizeof(screen)+sizeof(children),ancestors,sizeof(ancestors));
 memcpy(before+sizeof(screen)+sizeof(children)+sizeof(ancestors),&timer,sizeof(timer));
 bool active=beginDraw(&console,color);
 if(fault){if(active)return 1;}
 else{
  if(!active||beginDraw(&console,color))return 2;
  if(!screen.mIsVisible||screen.mAlpha!=255)return 3;
  for(unsigned i=0;i<depth;i++)if(!ancestors[i].mIsVisible||ancestors[i].mAlpha!=255)return 7;
  for(unsigned i=0;i<count;i++){
   if(!children[i].mIsVisible||children[i].mAlpha!=255)return 4;
   JUTRect expected=bindings[i].bounds;
   if(i==0&&index==1){expected.mY1=timerVisible?346:419;expected.mY2=expected.mY1+30;}
   if(!equal(&children[i].mRect,&expected,sizeof(JUTRect)))return 5;
   memset(children[i].geometry,0x88,sizeof(children[i].geometry));children[i].mAlphaCopy=255;
  }
  memset(screen.geometry,0x66,sizeof(screen.geometry));screen.mAlphaCopy=255;
  endDraw();endDraw();
 }
 if(!equal(&screen,before,sizeof(screen))||!equal(children,before+sizeof(screen),sizeof(children))||
    !equal(ancestors,before+sizeof(screen)+sizeof(children),sizeof(ancestors))||
    !equal(&timer,before+sizeof(screen)+sizeof(children)+sizeof(ancestors),sizeof(timer)))return 6;
 return 0;
}
'''
        cpp = work / "preview.cpp"
        cpp.write_text(code, encoding="ascii")
        cls.dlls = []
        for region in ("JP", "PAL"):
            library = work / ("preview-" + region + ".dll")
            subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
                "-DSUSAMUNE_VERSION_" + region + "=1", "-I", str(ROOT / "include"), str(cpp), "-o", str(library)], check=True)
            dll = ctypes.CDLL(str(library))
            cls.dlls.append(dll)
            cls.addClassCleanup(lambda dll=dll: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(dll._handle)))

    def test_hidden_counters_and_life_text_use_actual_bounds_then_restore_every_byte(self):
        for dll in self.dlls:
            for color in range(3, 9):
                for depth in range(3):
                    for timer_visible in range(2):
                        with self.subTest(color=color, ancestors=depth, timer=timer_visible):
                            self.assertEqual(dll.run(color, 0, depth, timer_visible), 0)

    def test_wrong_parent_cycles_and_excess_children_are_refused_without_changes(self):
        for dll in self.dlls:
            for fault in range(1, 6):
                with self.subTest(fault=fault):
                    self.assertEqual(dll.run(4, fault, 1, 1), 0)

    def test_region_offsets_match_retail_red_card_accesses(self):
        self.assertEqual([dll.redOffset(0) for dll in self.dlls], [0x428, 0x42C])
        self.assertEqual([dll.redOffset(1) for dll in self.dlls], [0x440, 0x444])


if __name__ == "__main__":
    unittest.main()
