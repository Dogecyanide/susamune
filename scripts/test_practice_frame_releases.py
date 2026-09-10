"""Execute production tape packing and held/menu decoder-history handling."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]

class FrameReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        production = ROOT / "src/practice_session.cpp"
        helpers = "\n".join(function_source(production, name) for name in (
            "void capturePad(", "void restorePad(", "u32 packReleases(",
            "u32 releaseButtons(", "u32 buttonMeanings(", "void applyReleases(",
            "void retainPausedReleases(", "void writeFrame(", "u32 frameReleases(",
            "SusamunePracticeInput frameInput("))
        source = Path(cls.temp.name) / "frames.cpp"
        source.write_text(r'''
#include "Dolphin/types.h"
#include "susamune/practice_input.h"
extern "C" void *memcpy(void*d,const void*s,size_t n){for(size_t i=0;i<n;++i)((volatile u8*)d)[i]=((const u8*)s)[i];return d;}
struct Button {u32 mInput,mFrameInput,released;u8 rest[36];};
struct Stick {u8 rest[16];};
struct JUTGamePad {static Button mPadButton[1];static Stick mPadMStick[1],mPadSStick[1];};
Button JUTGamePad::mPadButton[1];Stick JUTGamePad::mPadMStick[1],JUTGamePad::mPadSStick[1];
struct TMarioGamePad {Button mButtons;Stick main,sub;u32 _A4;u8 prefix[40];
    u32 mMeaning,mFrameMeaning,_D8;u16 _DC,_DE,_E0;u8 suffix[14];void updateMeaning();};
struct PadHistory {u8 shared[80],controls[80],meaning[0x4c];};
struct Frame {SusamunePracticeInput input;u32 fingerprint;};
static_assert(sizeof(Frame)==16,"fixed tape stride");
static_assert(sizeof(TMarioGamePad)==156,"captured retail ranges");
const u32 kDigitalButtons=0x1f7fu,kFrameFingerprintMask=0x7fffffffu;
static PadHistory sBeforeRead,sModalPad,initial;
static TMarioGamePad pad,*sReadPad=&pad;
static struct {TMarioGamePad *mGamePads[1];} gpApplication={{&pad}};
static bool sModal,sRecord,sTakeAttached,sModalPadValid,sHaveRead;
static u32 sPendingReleases,count,currentR;
static Frame frames[64];
static SusamunePracticeInput sPhysical,sConsumed;
bool normalStage(){return true;}
''' + helpers + r'''
void TMarioGamePad::updateMeaning(){
    u32 prev=mMeaning,dc=_DC;_DC=0;
    if(mButtons.mInput&15u)_DC|=1;
    if(currentR>(dc&1?37u:75u))_DC|=1;
    _DE=_DC&~dc;_E0=dc&~_DC;mMeaning=0;
    const u32 sources[]={0x1000,0x100,0x200,0x20,0x10,0x40,0x800,0x40,0x400};
    const u32 meanings[]={1,0x80,0x100,0x400,0x1000,0x2000,0x4000,0x8000,0x200000};
    for(unsigned n=0;n<9;++n)if((mButtons.mFrameInput&sources[n])||
        ((mButtons.mInput&sources[n])&&(prev&meanings[n])))mMeaning|=meanings[n];
    if((_DE&1)||((_DC&1)&&(prev&0x200)))mMeaning|=0x200;
    mFrameMeaning=mMeaning&~prev;_D8=prev&~mMeaning;
}
u32 stickBits(s8 x,s8 y){return(x<=-27?1:x>=27?2:0)|(y<=-27?4:y>=27?8:0);}
void readButtons(const SusamunePracticeInput&i){
    u32 buttons=i.buttons|(stickBits(i.stickX,i.stickY)<<24)|(stickBits(i.substickX,i.substickY)<<16);
    Button &b=JUTGamePad::mPadButton[0];b.mFrameInput=buttons&~b.mInput;b.released=b.mInput&~buttons;b.mInput=buttons;
    pad.mButtons=b;currentR=i.triggerR;
}
void read(const SusamunePracticeInput&i){readButtons(i);pad.updateMeaning();}
void inject(const SusamunePracticeInput&i,TMarioGamePad*){restorePad(sBeforeRead,&pad);readButtons(i);}
''' + function_source(production, "void retainModalHistory()") + r'''
extern "C" __declspec(dllexport) void reset(unsigned buttons,unsigned analog){
    pad={};JUTGamePad::mPadButton[0]={};sPhysical={};sPhysical.buttons=buttons;sPhysical.triggerR=analog;read(sPhysical);
    pad.mFrameMeaning=pad._D8=0;capturePad(initial,&pad);sBeforeRead=initial;
    sPendingReleases=count=0;sHaveRead=sRecord=sTakeAttached=true;sModal=sModalPadValid=false;
}
extern "C" __declspec(dllexport) u32 frame(unsigned buttons,unsigned analog,unsigned sticks,unsigned mode){
    capturePad(sBeforeRead,&pad);sPhysical={};sPhysical.buttons=buttons;sPhysical.triggerR=analog;
    sPhysical.stickX=(sticks&1)?-54:(sticks&2)?54:0;sPhysical.stickY=(sticks&4)?-54:(sticks&8)?54:0;
    sPhysical.substickX=(sticks&16)?-54:(sticks&32)?54:0;sPhysical.substickY=(sticks&64)?-54:(sticks&128)?54:0;
    read(sPhysical);sConsumed=sPhysical;
    if(mode==2){sModal=true;retainModalHistory();return pad.mFrameMeaning;}
    if(mode==3){sModal=false;retainModalHistory();}
    if(mode==0){retainPausedReleases(&pad);restorePad(sBeforeRead,&pad);return 0;}
    writeFrame(frames[count++],sConsumed,0xa1234567,sPendingReleases);sPendingReleases=0;
    return pad.mFrameMeaning;
}
extern "C" __declspec(dllexport) void rewind(){restorePad(initial,&pad);}
extern "C" __declspec(dllexport) u32 replay(unsigned i){
    applyReleases(&pad,frameReleases(frames[i]));read(frameInput(frames[i]));return pad.mFrameMeaning;
}
extern "C" __declspec(dllexport) u32 rawEdges(){return pad.mButtons.mFrameInput;}
extern "C" __declspec(dllexport) u32 pending(){return sPendingReleases;}
extern "C" __declspec(dllexport) u32 held(){return pad.mButtons.mInput;}
extern "C" __declspec(dllexport) unsigned exhaustive(){
    for(u32 r=0;r<0x200000u;++r){
        SusamunePracticeInput input={};input.buttons=kDigitalButtons;input.stickX=(s8)r;input.stickY=(s8)(r>>8);
        input.substickX=(s8)(r>>16);input.substickY=-123;input.triggerL=(u8)r;input.triggerR=(u8)(r>>8);
        input.analogA=(u8)(r>>3);input.analogB=(u8)(r>>5);Frame f;writeFrame(f,input,r*17u,r);
        if(frameReleases(f)!=r||(f.fingerprint&kFrameFingerprintMask)!=((r*17u)&kFrameFingerprintMask))return 1;
        SusamunePracticeInput output=frameInput(f);
        for(unsigned i=0;i<sizeof(input);++i)if(((u8*)&input)[i]!=((u8*)&output)[i])return 2;
        if(packReleases(releaseButtons(r),(r&0x100000u)!=0)!=r)return 3;
    }return 0;
}
extern "C" __declspec(dllexport) u32 sharedMeaning(){
    pad.mMeaning=0x10000;pad.mButtons.mInput=0x300;JUTGamePad::mPadButton[0].mInput=0x300;
    applyReleases(&pad,packReleases(0x100,false));return pad.mMeaning;
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2", "-I", str(ROOT / "include"),
                        str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_every_release_mask_roundtrips_without_losing_any_input_field(self):
        self.assertEqual(self.lib.exhaustive(), 0)

    def test_repress_A_while_B_stays_held_replays_same_edges(self):
        self.lib.reset(0x200, 0)
        recorded = [self.lib.frame(0x300, 0, 0, 1)]
        self.lib.frame(0x200, 0, 0, 0)
        recorded.append(self.lib.frame(0x300, 0, 0, 1))
        self.lib.rewind()
        replayed = [self.lib.replay(i) for i in range(2)]
        self.assertEqual(recorded, [0x80, 0x80])
        self.assertEqual(replayed, recorded)

    def test_continuous_buttons_are_not_rearmed(self):
        self.lib.reset(0x300, 0)
        self.lib.frame(0x300, 0, 0, 0)
        self.assertEqual(self.lib.frame(0x300, 0, 0, 1), 0)
        self.lib.rewind()
        self.assertEqual(self.lib.replay(0), 0)

    def test_analog_R_release_rearms_hysteresis_without_releasing_digital_A(self):
        self.lib.reset(0x100, 100)
        self.lib.frame(0x100, 0, 0, 0)
        self.assertEqual(self.lib.pending(), 0x100000)
        expected = self.lib.frame(0x100, 100, 0, 1)
        self.lib.rewind()
        self.assertEqual(expected, 0x200)
        self.assertEqual(self.lib.replay(0), expected)

    def test_both_sticks_preserve_direction_release_edges(self):
        self.lib.reset(0x100, 0)
        self.lib.frame(0x100, 0, 0xAA, 1)
        self.lib.frame(0x100, 0, 0, 0)
        self.lib.frame(0x100, 0, 0xAA, 1)
        expected = self.lib.rawEdges()
        self.lib.rewind()
        self.lib.replay(0)
        self.lib.replay(1)
        self.assertEqual(expected, 0x0A0A0000)
        self.assertEqual(self.lib.rawEdges(), expected)

    def test_modal_history_keeps_UI_edges_but_replays_gameplay_release(self):
        self.lib.reset(0x300, 0)
        self.lib.frame(0x200, 0, 0, 2)
        self.assertEqual(self.lib.held(), 0x200)
        self.assertEqual(self.lib.frame(0x300, 0, 0, 2), 0x80)
        self.assertEqual(self.lib.held(), 0x300)
        expected = self.lib.frame(0x300, 0, 0, 3)
        self.lib.rewind()
        self.assertEqual(expected, 0x80)
        self.assertEqual(self.lib.replay(0), expected)

    def test_shared_camera_A_B_meaning_retains_still_held_source(self):
        self.assertEqual(self.lib.sharedMeaning(), 0x10000)

if __name__ == "__main__": unittest.main()
