"""Stage seed provenance and raw-clock ownership, using the production observer."""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from audit_rng_calls import read_symbols, direct_calls

ROOT = Path(__file__).resolve().parents[1]
SITES = {"jp": (0x800f9f70, 0x4bff03ad, 0x800ea31c),
         "us": (0x802a656c, 0x4bff07f5, 0x80296d60),
         "pal": (0x8029e4a8, 0x4bff0751, 0x8028ebf8)}
ISOS = {"jp": "SUper Mario Sunshine (Japan).iso", "us": "Super Mario Sunshine (USA).iso",
        "pal": "Super Mario Sunshine (Europe) (En,Fr,De,Es,It).iso"}


class StageContextTests(unittest.TestCase):
    def test_observation_ownership_and_passthrough(self):
        compiler = shutil.which("g++") or "C:/msys64/mingw64/bin/g++.exe"
        if not Path(compiler).is_file(): self.skipTest("host C++ compiler unavailable")
        with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="ghost-stage-test-") as directory:
            folder = Path(directory)
            headers = {
                "Dolphin/types.h": "#pragma once\nusing u32=unsigned int; using s32=int; using u8=unsigned char;\n",
                "susamune/addresses.hxx": "#pragma once\n#include <cstdint>\nextern unsigned int testSeed;\n#define SUSAMUNE_MEM1_ADDR(j,u,p) (j)\n#define SUSAMUNE_ADDR_LIBC_RAND_SEED reinterpret_cast<uintptr_t>(&testSeed)\n",
                "susamune/features.hxx": "#pragma once\nvoid writeGameCode(unsigned int,unsigned int);\n",
                "susamune/retail_input.hxx": "#pragma once\nclass TMarDirector; namespace RetailInput { TMarDirector *stageDirector(); }\n",
                "SMS/System/MarDirector.hxx": """#pragma once
#include "Dolphin/types.h"
namespace JDrama { struct TDisplay {}; }
struct TMarioGamePad {};
struct TMarDirector {
 unsigned char _260=0,mAreaID=0,mEpisodeID=0;
 int unk58=0,unk5C=0;
 s32 setup(JDrama::TDisplay*,TMarioGamePad**,u8,u8);
};
extern TMarDirector *gpMarDirector;
""",
            }
            for name, text in headers.items():
                path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            source = r'''#include <cassert>
#include <cstdint>
#include "SMS/System/MarDirector.hxx"
unsigned int testSeed;
TMarDirector *gpMarDirector, *actual;
JDrama::TDisplay *expectedDisplay;
TMarioGamePad **expectedPads;
int returnValue, calls, writes;
namespace RetailInput { TMarDirector *stageDirector(){return actual;} }
void writeGameCode(unsigned int,unsigned int){++writes;}
s32 TMarDirector::setup(JDrama::TDisplay *display,TMarioGamePad **pads,u8 area,u8 episode){
 assert(display==expectedDisplay && pads==expectedPads);
 mAreaID=area;mEpisodeID=episode;++calls;testSeed=testSeed*0x41c64e6dU+0x3039U;return returnValue;
}
#include "PRODUCTION"
int main(){
 using namespace GhostStageContext;
 TMarDirector d,other; JDrama::TDisplay display; TMarioGamePad pad; TMarioGamePad *pads[]={&pad};
 expectedDisplay=&display;expectedPads=pads;actual=gpMarDirector=&d;
 Sample out={};out.seed=0xdeadbeef;
 assert(!sample(&out) && out.seed==0xdeadbeef && !sample(nullptr) && !restoredStage());
 sInstalled=true;testSeed=0x87654321;
 assert(susamuneGhostStageSetup(&d,&display,pads,6,5)==0 && calls==1);
 assert(testSeed!=0x87654321 && !sample(&out));
 d._260=1;d.unk58=84;d.unk5C=88;
 assert(sample(&out) && out.seed==0x87654321 && out.movementTicks==84 && out.directorTicks==88);
 assert(out.area==6 && out.episode==5 && out.generation==1);
 // Ordinary pause changes only the director counter; observation is read-only.
 d.unk5C+=12;unsigned int seed=testSeed;assert(sample(&out));
 assert(out.movementTicks==84 && out.directorTicks==100 && testSeed==seed && !writes);
 actual=&other;assert(!sample(&out));actual=&d;
 gpMarDirector=&other;assert(!sample(&out));gpMarDirector=&d;
 d.mAreaID=3;assert(!sample(&out));d.mAreaID=6;
 d.mEpisodeID=4;assert(!sample(&out));d.mEpisodeID=5;
 invalidateAfterRestore();assert(!sample(&out) && restoredStage());
 testSeed=7;d._260=0;assert(susamuneGhostStageSetup(&d,&display,pads,6,5)==0);
 d._260=1;assert(sample(&out) && out.seed==7 && out.generation==2 && !restoredStage());
 sInstalled=false;assert(!sample(&out));sInstalled=true;
 returnValue=37;assert(susamuneGhostStageSetup(&d,&display,pads,1,0)==37 && !sample(&out));
 sGeneration=0xffffffff;returnValue=0;assert(susamuneGhostStageSetup(&d,&display,pads,1,0)==0);
 assert(sample(&out) && out.generation==1 && calls==4 && !writes);
}
'''
            source=source.replace("PRODUCTION",(ROOT/"src/ghost_stage_context.cpp").as_posix())
            path=folder/"test.cpp";path.write_text(source)
            env=dict(os.environ,PATH=str(Path(compiler).parent)+os.pathsep+os.environ.get("PATH",""))
            subprocess.run([compiler,"-std=c++17","-O2","-I",str(folder),"-I",str(ROOT/"include"),str(path),"-o",str(folder/"test.exe")],check=True,env=env)
            subprocess.run([str(folder/"test.exe")],check=True,env=env)

    def test_retail_hook_and_tick_sequences_all_regions(self):
        source=(ROOT/"src/ghost_stage_context.cpp").read_text()
        for region,(site,word,target) in SITES.items():
            with self.subTest(region=region):
                path=Path("X:/Games and Isos/GC and WII")/ISOS[region]
                if not path.exists(): self.skipTest("clean retail ISOs unavailable")
                with path.open("rb") as stream:
                    stream.seek(0);self.assertEqual(stream.read(6),{"jp":b"GMSJ01","us":b"GMSE01","pal":b"GMSP01"}[region])
                    stream.seek(0x420);base=struct.unpack(">I",stream.read(4))[0]
                    stream.seek(base);header=stream.read(256)
                    spans=[(struct.unpack_from(">I",header,i*4)[0],struct.unpack_from(">I",header,0x48+i*4)[0],struct.unpack_from(">I",header,0x90+i*4)[0]) for i in range(18)]
                    stream.seek(base);data=stream.read(max(o+n for o,_,n in spans))
                def read(address,size):
                    offset=next(o+address-a for o,a,n in spans if a<=address<address+size<=a+n)
                    return data[offset:offset+size]
                symbols={s.name:s for s in read_symbols(ROOT/"maps"/(region+".map"))}
                self.assertEqual(symbols["setup__12TMarDirectorFPQ26JDrama8TDisplayPP13TMarioGamePadUcUc"].address,target)
                self.assertEqual(list(direct_calls(data,target,False)),[site])
                self.assertEqual(read(site,4),struct.pack(">I",word))
                self.assertIn(f"0x{site:08x}u",source);self.assertIn(f"0x{word:08x}u",source)
                # Store area/episode, create the resource thread, then resume it.
                setup=read(target,0x74)
                self.assertEqual(struct.unpack_from(">I",setup,0x30)[0],0x98c8007c)
                self.assertEqual(struct.unpack_from(">I",setup,0x3c)[0],0x98e8007d)
                self.assertEqual(struct.unpack_from(">I",setup,0x50)[0]>>26,18)
                self.assertEqual(struct.unpack_from(">I",setup,0x58)[0]>>26,18)
                direct=symbols["direct__12TMarDirectorFv"]
                words=read(direct.address,direct.size)
                # Movement +0x58 can be skipped; director +0x5c increments regardless.
                pattern=struct.pack(">9I",0x576007ff,0x40820010,0x807a0058,0x38030001,0x901a0058,0x807a005c,0x38030001,0x901a005c,0xa01a004c)
                self.assertEqual(words.count(pattern),1)
                self.assertEqual(struct.unpack_from(">I",words,0x34)[0],0x7f2303d6)
                self.assertIn(struct.pack(">2I",0x3803fffb,0x901a0054),words)

if __name__=="__main__":unittest.main()
