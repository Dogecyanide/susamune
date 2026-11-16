"""Appearance packets and the production per-model texture cache/callback."""
import ctypes as C
from _ctypes import FreeLibrary
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LiveColourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT/'build')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        source = (ROOT/'src/ghost_model.cpp').read_text()
        code = r'''
#include <stdint.h>
#include <string.h>
#include "susamune/live_colours.hxx"
#include "susamune/mario_color_texture.hxx"
#define TIMEWARP_LIVE_RACING 1
#define IS_EMULATOR 0
using u8=unsigned char;using u32=uintptr_t;
struct GXTexObj {const void *pixels;};
struct ResTIMG {unsigned mTextureOffset;};
struct J3DShapePacket{};
struct J3DModel {void *mShapePackets;};
struct J3DModelData {unsigned mShapeNum;};
struct GXColor {u8 r,g,b,a;};
struct ModelSlot {J3DModel *model;J3DModelData *data;};
enum {MODEL_SLOT_COUNT=3,APPEARANCE_MARIO=2,GX_COLOR0A0=0,GX_TEXMAP0=0};
static ModelSlot sSlots[3];static bool sLoadedGroup=true;static int sLoadedAlternative=2;
static GXColor sGhostColor={255,255,255,192},drawColour;
static const unsigned kShapePacketStride=0x34,kShapePacketUserAreaOffset=0x0c;
static unsigned fences,flushes;static const void *loaded;
void GXDrawDone(){++fences;}void DCStoreRange(void*,unsigned){++flushes;}void GXInvalidateTexAll(){}
void GXSetChanMatColor(int,GXColor c){drawColour=c;}void GXLoadTexObj(GXTexObj*p,int){loaded=p->pixels;}
struct Heap {unsigned used,limit;u8 bytes[32768];void *alloc(unsigned n,int){if(n>limit-used)return nullptr;used+=n;return bytes;}};
static Heap heap;static Heap *sAttachmentHeap=&heap;
static u8 work[65536];
#define SUSAMUNE_GHOST_SHADOW_ASSET_BUFFER_SIZE 65536u
#define SUSAMUNE_GHOST_SHADOW_STAGING_PPC_PTR work
struct Texture {ResTIMG image;u8 data[32768];};static Texture texture;
namespace MarioColors {const ResTIMG *sourceTexture(){return &texture.image;}}
namespace ModelColorDraw {void initTexture(GXTexObj&o,const ResTIMG&,const void*p,int,int){o.pixels=p;}}
static LiveColours::Palette palettes[3];
namespace LiveRace {enum {MODEL_MARIO=2};const LiveColours::Palette *opponentColours(unsigned i){return i<3?palettes+i:nullptr;}}
static int selected=2;int onlineModel(){return selected;}
ModelSlot &runnerSlot(int i){return sSlots[i];}
'''
        start = source.index('struct ColourState {')
        code += source[start:source.index('Appearance sLoadedAlternative',start)]
        code += function(source,'bodyPacketCallback')+'\n'+function(source,'refreshColours')
        code += r'''
static u8 packets[3][11*0x34];static J3DModel models[3];static J3DModelData data[3];
#define API extern "C" __declspec(dllexport)
API void reset(unsigned limit){
 memset(sColours,0,sizeof(sColours));memset(palettes,0,sizeof(palettes));memset(work,0,sizeof(work));
 heap.used=0;heap.limit=limit;fences=flushes=0;loaded=nullptr;selected=2;sLoadedGroup=true;
 texture.image.mTextureOffset=sizeof(ResTIMG);
 for(unsigned i=0;i<32768;i+=8){texture.data[i]=0xf8;texture.data[i+1]=0;texture.data[i+2]=0x78;texture.data[i+3]=0;}
 for(unsigned i=0;i<3;++i){models[i].mShapePackets=packets[i];data[i].mShapeNum=11;sSlots[i]={models+i,data+i};
  palettes[i].mask=31;for(unsigned p=0;p<7;++p)palettes[i].rgb[p][i]=255;
  for(unsigned p=0;p<11;++p){static GXColor original={123,124,125,255};*(GXColor**)(packets[i]+p*0x34+12)=&original;}}
}
API void tick(){refreshColours();}
API void colour(unsigned who,unsigned mask,unsigned red){palettes[who].mask=mask;palettes[who].rgb[0][0]=red;}
API unsigned metric(unsigned n){switch(n){case 0:return fences;case 1:return flushes;case 2:return heap.used;
 case 3:return sColours[0].ready|sColours[1].ready<<1|sColours[2].ready<<2;
 case 4:return sColours[0].atlas==work&&sColours[1].atlas==work+32768&&sColours[2].atlas==heap.bytes;
 case 5:return memcmp(sColours[0].atlas,sColours[1].atlas,32768)!=0&&memcmp(sColours[1].atlas,sColours[2].atlas,32768)!=0;
 case 6:return texture.data[0]==0xf8&&texture.data[1]==0;
 }return 0;}
API int packet(unsigned who,unsigned shape,unsigned phase){loaded=nullptr;bodyPacketCallback((J3DShapePacket*)(packets[who]+shape*0x34),phase);
 if(!loaded)return 0;return loaded==sColours[who].atlas?1:loaded==texture.data?2:-1;}
API int codec(unsigned mask,unsigned bytes,unsigned player){LiveColours::Palette p={};p.mask=mask;u8 b[24];LiveColours::encode(b,player,p);
 LiveColours::Palette out={};return LiveColours::decode(b,bytes,out)&&LiveColours::same(p,out);}
'''
        cpp,dll=path/'test.cpp',path/'test.dll'
        cpp.write_text(code)
        compiler=Path('C:/msys64/mingw64/bin/g++.exe')
        env={**os.environ,'PATH':str(compiler.parent)+os.pathsep+os.environ.get('PATH','')}
        result=subprocess.run([str(compiler),'-std=c++17','-O2','-shared','-static-libgcc','-static-libstdc++',
            '-I',str(ROOT/'include'),str(cpp),str(ROOT/'src/mario_color_texture.cpp'),'-o',str(dll)],capture_output=True,text=True,env=env)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        cls.lib=C.CDLL(str(dll));cls.addClassCleanup(lambda:FreeLibrary(cls.lib._handle))

    def test_packet_size_and_mask_are_bounded(self):
        for player in range(4): self.assertEqual(self.lib.codec(127,24,player),1)
        for args in ((128,24,0),(1,23,0),(1,25,0),(1,24,4)): self.assertEqual(self.lib.codec(*args),0)

    def test_three_distinct_palettes_keep_source_and_cache_unchanged(self):
        self.lib.reset(32768);self.lib.tick()
        self.assertEqual([self.lib.metric(i) for i in range(7)],[3,3,32768,7,1,1,1])
        for _ in range(100): self.lib.tick()
        self.assertEqual(self.lib.metric(0),3)
        self.lib.colour(1,31,200);self.lib.tick()
        self.assertEqual(self.lib.metric(0),4)
        for player in range(3):
            self.assertEqual(self.lib.packet(player,4,0),1)
            self.assertEqual(self.lib.packet(player,4,1),2)
            self.assertEqual(self.lib.packet(player,0,0),0)
        self.lib.colour(1,0,0);self.lib.tick()
        self.assertEqual(self.lib.packet(1,4,0),0)
        self.assertEqual(self.lib.metric(0),4)

    def test_full_attachment_heap_keeps_native_rendering(self):
        self.lib.reset(0);self.lib.tick()
        self.assertEqual(self.lib.metric(3),3)
        self.assertEqual(self.lib.metric(2),0)
        self.assertEqual(self.lib.packet(2,4,0),0)


if __name__=='__main__': unittest.main()
