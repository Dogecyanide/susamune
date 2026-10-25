"""Run production Watch clocks, both pose samplers and checkpoint transitions."""
import ctypes as C
import _ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function
from ghost_scrub_render_fixture import render_fixture

ROOT = Path(__file__).resolve().parents[1]


class GhostScrubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-watch-scrub-', dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        source = (ROOT / 'src/ghost.cpp').read_text()
        code = r'''
#include "susamune/ghost.hxx"
#include "susamune/ghost_format.h"
#include "susamune/ghost_teaching.h"
#include "susamune/ghost_camera.h"
using namespace Ghost;
enum {OBSERVER_OFF,OBSERVER_ACTIVE_ONE,OBSERVER_ACTIVE_TWO,OBSERVER_WARPING_ONE,OBSERVER_WARPING_TWO};
typedef SusamuneGhostPoseSample Sample;
struct TVec3f {f32 x,y,z;void set(f32 a,f32 b,f32 c){x=a;y=b;z=c;}};
struct Segment {u32 firstSample,sampleCount,startQf,endQf;s32 routeVariant;u8 routeArea,routeEpisode,routeParentArea,routeFlags;};
struct Track {Segment*segments;u16 segmentCount;u32 startQf,endQf;bool valid;u8 splitCount;SusamuneGhostSplitSample splits[8];
 Sample*samples;u16 formatVersion;u8 attachmentCount;SusamuneGhostAttachmentDescriptor attachments[8];};
Track sPlayback,sObserverSecondary;
Segment scenes[2][2];
Sample poses[2][6];
int sObserverPhase,sObserverPrimarySegment,sObserverSecondarySegment,sPlaybackSegment;
int sObserverBaseQf,sObserverEndQf,sObserverLastQf,sObserverRawQf,sObserverLastLiveQf;
s32 sObserverQfOffset,sObserverStageAnchorQf,sPlaybackCursorQf,sObserverSecondaryCursorQf;
u32 sPlaybackCursor,sObserverSecondaryCursor,sObserverVisualToken;
bool sObserverScrubClock,sObserverPaused,sFrameFrozen,sObserverClockReady,sObserverStageReady,sObserverPastEnd;
bool sObserverContinuousClock,sObserverExitArmed,sGhostVisible,sSecondaryGhostVisible;
TVec3f sGhostPosition,sSecondaryGhostPosition;
s16 sGhostYaw,sSecondaryGhostYaw;
u16 sGhostAnimationId,sSecondaryGhostAnimationId,sGhostAnimationPhase,sSecondaryGhostAnimationPhase;
u8 sGhostYoshi,sSecondaryGhostYoshi;
u32 sGhostHeldObjectId,sSecondaryGhostHeldObjectId;
u16 sGhostHeldNameKey,sSecondaryGhostHeldNameKey;
int sVisualQf;
int sObserverSeekQf,sObserverSecondaryOffset;
s8 sObserverAlignedSplit;
const u32 kMaxDurationQf=108000;
const s32 kPositionScale=SUSAMUNE_GHOST_POSITION_SCALE;
struct TMarDirector {enum {STATE_NORMAL=4,STATE_STAGE_EXIT_2=12};int unk5C,mCurState;bool _260;};
TMarDirector director,*gpMarDirector=&director;
struct Timer {int qf;bool stopped;bool currentQf(s32*out,bool*stop=nullptr){*out=qf;if(stop)*stop=stopped;return true;}int attemptSerial(){return 0;}}gQFTTimer;
bool observerRunning(){return sObserverPhase!=OBSERVER_OFF;}
bool observerHasTwo(){return sObserverPhase==OBSERVER_ACTIVE_TWO||sObserverPhase==OBSERVER_WARPING_TWO;}
namespace Ghost {bool observerLoading(){return sObserverPhase==OBSERVER_WARPING_ONE||sObserverPhase==OBSERVER_WARPING_TWO;}}
int warps;
void anchorObserverMario(){}
void armObserverSegment(){++warps;sObserverPhase=observerHasTwo()?OBSERVER_WARPING_TWO:OBSERVER_WARPING_ONE;sObserverStageReady=false;}
extern "C" void *memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" {int _fltused=0;}
'''
        for name in ('readU24', 'readS24', 'writeU24', 'writeS24', 'sampleX', 'sampleY', 'sampleZ',
                     'sampleAnimationId', 'sampleAnimationPhase', 'sampleYoshi', 'sampleHeld',
                     'sampleAttachments', 'interpolateAnimationPhase', 'samplePosition',
                     'sampleObserverTrack', 'updateObserverVisual', 'segmentRouteEquals',
                     'observerQf', 'observerSegmentRange', 'configureObserverSegment',
                     'startObserverClock', 'observerSegmentAt'):
            code += function(source, name)
        code += '\nnamespace Ghost {\n'
        for name in ('observerTimeline', 'observerSplit', 'observerPause', 'observerPaused',
                     'observerSeek', 'observerAlignSplit', 'observerClearAlignment'):
            code += function(source, name)
        code += '\n}\n'
        code += render_fixture(source, (ROOT / 'src/ghost_model.cpp').read_text(),
                               (ROOT / 'src/ghost_scrub.cpp').read_text())
        code += r'''
#define API extern "C" __declspec(dllexport)
API void reset(){
 scenes[0][0]={0,3,0,800,0,1,0,255,0};
 scenes[0][1]={3,3,1000,1800,0,2,0,255,0};
 scenes[1][0]={0,3,0,850,0,1,0,255,0};
 scenes[1][1]={3,3,1100,1900,0,2,0,255,0};
 sPlayback={};sObserverSecondary={};
 sPlayback.segments=scenes[0];sObserverSecondary.segments=scenes[1];
 sPlayback.samples=poses[0];sObserverSecondary.samples=poses[1];
 sPlayback.formatVersion=sObserverSecondary.formatVersion=8;
 for(int runner=0;runner<2;++runner)for(int i=0;i<6;++i){
  poses[runner][i]={};poses[runner][i].deltaQf=i%3?400:0;
  writeS24(poses[runner][i].x,((i/3)*100+(i%3)*40)*kPositionScale);}
 poses[1][1].deltaQf=460;poses[1][2].deltaQf=390;
 sPlayback.segmentCount=sObserverSecondary.segmentCount=2;
 sPlayback.valid=sObserverSecondary.valid=true;
 sPlayback.endQf=1800;sObserverSecondary.endQf=1900;
 sPlayback.splitCount=sObserverSecondary.splitCount=2;
 sPlayback.splits[0]={400,0x1234,5,0,0};sPlayback.splits[1]={1400,0x1234,5,1,0};
 sObserverSecondary.splits[0]={460,0x1234,5,0,0};sObserverSecondary.splits[1]={1500,0x1234,5,1,0};
 sObserverPhase=OBSERVER_ACTIVE_TWO;sObserverPrimarySegment=sObserverSecondarySegment=0;
 sObserverScrubClock=sObserverPaused=sFrameFrozen=false;
 sObserverClockReady=sObserverStageReady=true;sObserverPastEnd=false;
 sObserverSecondaryOffset=sObserverQfOffset=0;sObserverAlignedSplit=-1;sObserverSeekQf=-1;
 sObserverLastLiveQf=500;sObserverLastQf=500;sObserverBaseQf=0;sObserverEndQf=850;
 director={1000,4,true};gQFTTimer={500,false};warps=0;sVisualQf=-1;menu.open=false;
 sObserverContinuousClock=sObserverExitArmed=false;
 sPlaybackCursor=sObserverSecondaryCursor=0;sPlaybackCursorQf=sObserverSecondaryCursorQf=0;
 updateObserverVisual(500);
}
API int pauseWatch(int v){return Ghost::observerPause(v);}
API int tick(int raw,int frozen,int stopped){director.unk5C=raw;sFrameFrozen=frozen;gQFTTimer.stopped=stopped;int q=observerQf();updateObserverVisual(q);return q;}
API int seek(unsigned q){return Ghost::observerSeek(q);}
API int align(unsigned i){return Ghost::observerAlignSplit((u8)i);}
API int clearAlignment(){return Ghost::observerClearAlignment();}
API int offset(){return sObserverSecondaryOffset;}
API int position(){return sObserverLastQf;}
API int pending(){return sObserverSeekQf;}
API int warped(){return warps;}
API int selectedSegment(){return sObserverPrimarySegment;}
API int aligned(){return sObserverAlignedSplit;}
API int paused(){return Ghost::observerPaused();}
API float poseX(int runner){return runner?sSecondaryGhostPosition.x:sGhostPosition.x;}
API int visible(int runner){return runner?sSecondaryGhostVisible:sGhostVisible;}
API int sampleQf(int runner){return runner?sObserverSecondaryCursorQf:sPlaybackCursorQf;}
API int checkpoint(int runner){return runner?sObserverSecondary.splits[0].qf:sPlayback.splits[0].qf;}
API void secondaryCheckpoint(int qf){sObserverSecondary.splits[0].qf=qf;
 poses[1][1].deltaQf=qf;poses[1][2].deltaQf=850-qf;}
API void oversizedPair(){sPlayback.segmentCount=sObserverSecondary.segmentCount=1;
 sPlayback.endQf=sObserverSecondary.endQf=scenes[0][0].endQf=scenes[1][0].endQf=kMaxDurationQf;
 sPlayback.splitCount=sObserverSecondary.splitCount=1;}
API void unavailable(int kind){if(kind==1)sObserverStageReady=false;if(kind==2)director.mCurState=2;}
API void completeWarp(){sObserverStageReady=true;startObserverClock(0);}
API int split(unsigned i){Ghost::ObserverSplit out;return Ghost::observerSplit(i,&out)&&out.comparable;}
API void mismatch(int kind){auto&b=sObserverSecondary.splits[0];
 if(kind==1)++b.schema;if(kind==2)++b.route;if(kind==3)++b.endpoint;
 if(kind==4)++scenes[1][0].routeEpisode;if(kind==5)b.qf=1500;
 if(kind==6)sObserverSecondary.splitCount=0;}
API void stop(){sObserverPhase=OBSERVER_OFF;}
API int cameraTime(){return observerQf();}
'''
        cpp = Path(cls.temp.name) / 'scrub.cpp'
        dll = cpp.with_suffix('.dll')
        cpp.write_text(code)
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'),
            '--target=x86_64-pc-windows-msvc', '-shared', '-nostdlib', '-fuse-ld=lld',
            '-Wl,/noentry', '-fno-builtin', '-fno-rtti', '-fno-exceptions', '-O2',
            '-DTIMEWARP_LIVE_RACING=1', '-I', str(ROOT / 'include'),
            str(cpp), '-o', str(dll)], capture_output=True, text=True,
            env={**os.environ, 'TEMP': cls.temp.name, 'TMP': cls.temp.name})
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.lib.poseX.restype = C.c_float
        cls.lib.renderedX.restype = C.c_float
        cls.addClassCleanup(lambda: _ctypes.FreeLibrary(cls.lib._handle))

    def setUp(self):
        self.lib.reset()

    def test_paused_clock_does_not_catch_up_and_ignores_stopped_race_clock(self):
        self.assertEqual(self.lib.pauseWatch(1), 1)
        self.assertEqual(self.lib.tick(1120, 0, 1), 500)
        self.assertEqual(self.lib.pauseWatch(0), 1)
        self.assertEqual(self.lib.tick(1124, 0, 1), 504)
        self.assertEqual(self.lib.tick(1244, 1, 1), 504)
        self.assertEqual(self.lib.tick(1248, 0, 1), 508)
        self.assertEqual(self.lib.tick(0, 0, 1), 508)
        self.assertEqual(self.lib.tick(4, 0, 1), 512)

    def test_align_exact_checkpoint_and_clear_without_changing_primary_position(self):
        self.assertEqual(self.lib.align(0), 1)
        self.assertEqual(self.lib.offset(), 60)
        self.assertEqual(self.lib.position(), 400)
        self.assertEqual(self.lib.paused(), 1)
        self.assertEqual(self.lib.pauseWatch(0), 1)
        self.assertEqual(self.lib.tick(1004, 0, 1), 404)
        self.assertEqual(self.lib.clearAlignment(), 1)
        self.assertEqual(self.lib.offset(), 0)
        self.assertEqual(self.lib.position(), 404)

    def test_both_actual_poses_jump_to_own_split_then_share_elapsed_time(self):
        for secondary in (340, 460):
            with self.subTest(secondary=secondary):
                self.lib.reset()
                self.lib.secondaryCheckpoint(secondary)
                self.assertEqual(self.lib.seek(700), 1)
                self.assertEqual(self.lib.align(0), 1)
                self.assertEqual(self.lib.aligned(), 0)
                self.assertEqual(self.lib.paused(), 1)
                for runner, qf in ((0, 400), (1, secondary)):
                    self.assertEqual(self.lib.visible(runner), 1)
                    self.assertEqual(self.lib.sampleQf(runner), qf)
                    self.assertAlmostEqual(self.lib.poseX(runner), 40.0)
                    self.assertEqual(self.lib.checkpoint(runner), qf)
                self.assertEqual(self.lib.tick(1120, 0, 1), 400)
                self.assertAlmostEqual(self.lib.poseX(1), 40.0)
                self.assertEqual(self.lib.pauseWatch(0), 1)
                self.assertEqual(self.lib.tick(1124, 0, 1), 404)
                self.assertEqual(self.lib.cameraTime(), 404)
                self.assertAlmostEqual(self.lib.poseX(0), 40.4, places=4)
                self.assertAlmostEqual(self.lib.poseX(1), 40 + 160 / (850 - secondary), places=4)

    def test_both_checkpoints_survive_guarded_scene_load_paused(self):
        self.assertEqual(self.lib.align(1), 1)
        self.assertEqual(self.lib.warped(), 1)
        self.assertEqual(self.lib.pending(), 1400)
        self.assertEqual(self.lib.offset(), 100)
        self.assertEqual(self.lib.paused(), 0)
        self.lib.completeWarp()
        self.assertEqual(self.lib.paused(), 1)
        self.assertEqual(self.lib.cameraTime(), 1400)
        for runner, qf in ((0, 1400), (1, 1500)):
            self.assertEqual(self.lib.visible(runner), 1)
            self.assertEqual(self.lib.sampleQf(runner), qf)
            self.assertAlmostEqual(self.lib.poseX(runner), 140.0)
        self.assertEqual(self.lib.pauseWatch(0), 1)
        self.assertEqual(self.lib.tick(1004, 0, 1), 1404)

    def test_rejected_alignment_preserves_both_cursors_and_clock(self):
        for kind in (0, 1, 2):
            with self.subTest(kind=kind):
                self.lib.reset()
                if kind == 0:
                    self.lib.secondaryCheckpoint(340)
                    self.lib.oversizedPair()
                else:
                    self.lib.unavailable(kind)
                before = [self.lib.poseX(runner) for runner in (0, 1)]
                self.assertEqual(self.lib.align(0), 0)
                self.assertEqual(self.lib.offset(), 0)
                self.assertEqual(self.lib.position(), 500)
                self.assertEqual(self.lib.aligned(), -1)
                self.assertEqual(self.lib.paused(), 0)
                self.assertEqual([self.lib.poseX(runner) for runner in (0, 1)], before)

    def test_matching_route_alone_never_admits_alignment(self):
        for mismatch in range(1, 7):
            with self.subTest(mismatch=mismatch):
                self.lib.reset()
                self.lib.mismatch(mismatch)
                self.assertEqual(self.lib.split(0), 0)
                self.assertEqual(self.lib.align(0), 0)
                self.assertEqual(self.lib.offset(), 0)
                self.assertEqual(self.lib.position(), 500)

    def test_gap_snaps_to_next_scene_and_holds_target_through_warp(self):
        self.assertEqual(self.lib.seek(900), 1)
        self.assertEqual(self.lib.warped(), 1)
        self.assertEqual(self.lib.selectedSegment(), 1)
        self.assertEqual(self.lib.pending(), 1000)
        self.assertEqual(self.lib.paused(), 0)  # loading must run
        self.assertEqual(self.lib.seek(400), 0)

    def test_backward_end_clamp_and_exit_release(self):
        self.assertEqual(self.lib.seek(0), 1)
        self.assertEqual(self.lib.position(), 0)
        self.assertEqual(self.lib.seek(0xffffffff), 1)
        self.assertEqual(self.lib.pending(), 1800)
        self.lib.reset()
        self.lib.pauseWatch(1)
        self.lib.stop()
        self.assertEqual(self.lib.paused(), 0)

    def test_select_then_play_rewinds_both_rendered_models_and_camera(self):
        for secondary in (340, 460):
            with self.subTest(secondary=secondary):
                self.lib.reset()
                self.lib.secondaryCheckpoint(secondary)
                self.assertEqual(self.lib.seek(700), 1)
                self.lib.render(1000, 1)
                self.assertGreater(self.lib.renderedX(0), 40)
                self.assertGreater(self.lib.renderedX(1), 40)
                self.assertEqual(self.lib.openTimeline(), 1)
                self.assertEqual(self.lib.selected(), 255)
                self.assertEqual(self.lib.press(1), 0)  # R selects the first split.
                self.assertEqual(self.lib.selected(), 0)
                self.assertEqual(self.lib.paused(), 1)
                self.lib.render(1120, 1)
                for runner, qf in ((0, 400), (1, secondary)):
                    self.assertEqual(self.lib.submitted(runner), 1)
                    self.assertAlmostEqual(self.lib.renderedX(runner), 40)
                    self.assertEqual(self.lib.renderedQf(runner), qf)
                self.assertEqual(self.lib.cameraQf(), 400)
                self.assertEqual(self.lib.menuShown(), 1)
                self.lib.render(1240, 1)
                self.assertEqual(self.lib.cameraQf(), 400)
                self.assertEqual(self.lib.press(5), 1)  # A resumes the held pair.
                self.assertEqual(self.lib.menuShown(), 0)
                self.lib.render(1244, 0)
                self.assertEqual(self.lib.cameraQf(), 404)
                self.assertEqual(self.lib.renderedQf(0), 404)
                self.assertEqual(self.lib.renderedQf(1), secondary + 4)
                self.assertAlmostEqual(self.lib.renderedX(0), 40.4, places=4)
                self.assertAlmostEqual(self.lib.renderedX(1), 40 + 160 / (850 - secondary), places=4)

    def test_both_jump_buttons_rewind_pair_and_back_keeps_visible_pause(self):
        for button in (3, 4):
            with self.subTest(button=button):
                self.lib.reset()
                self.lib.seek(700)
                self.lib.openTimeline()
                self.assertEqual(self.lib.press(button), 0)
                self.assertEqual(self.lib.selected(), 0)
                self.assertEqual(self.lib.press(6), 1)  # B returns without resuming.
                self.lib.showMenu(0)
                self.lib.render(1120, 1)
                for runner in (0, 1):
                    self.assertEqual(self.lib.submitted(runner), 1)
                    self.assertAlmostEqual(self.lib.renderedX(runner), 40)
                self.assertEqual(self.lib.paused(), 1)

    def test_unmatched_selection_cannot_play_the_old_position(self):
        self.lib.seek(700)
        self.lib.openTimeline()
        self.lib.mismatch(1)
        self.lib.press(1)
        self.assertEqual(self.lib.selected(), -1)
        self.assertEqual(self.lib.position(), 700)
        self.assertEqual(self.lib.press(5), 0)
        self.assertEqual(self.lib.menuShown(), 1)
        self.assertEqual(self.lib.paused(), 1)
        self.assertEqual(self.lib.toastCount(), 2)
        self.assertEqual(self.lib.press(7), 0)  # Deliberate manual scrub cancels refusal.
        self.assertEqual(self.lib.selected(), 255)
        self.assertEqual(self.lib.press(5), 1)

    def test_left_selects_last_checkpoint_through_scene_load(self):
        self.lib.openTimeline()
        self.assertEqual(self.lib.selected(), 255)
        self.assertEqual(self.lib.press(2), 1)
        self.assertEqual(self.lib.selected(), 1)
        self.assertEqual(self.lib.pending(), 1400)
        self.assertEqual(self.lib.menuShown(), 0)
        self.lib.completeWarp()
        self.lib.render(1120, 1)
        for runner, qf in ((0, 1400), (1, 1500)):
            self.assertEqual(self.lib.submitted(runner), 1)
            self.assertAlmostEqual(self.lib.renderedX(runner), 140)
            self.assertEqual(self.lib.renderedQf(runner), qf)
        self.assertEqual(self.lib.paused(), 1)

    def test_regular_menu_still_hides_models_without_paused_watch(self):
        self.lib.showMenu(1)
        self.lib.render(1000, 1)
        self.assertEqual(self.lib.submitted(0), 0)
        self.assertEqual(self.lib.submitted(1), 0)


if __name__ == '__main__':
    unittest.main()
