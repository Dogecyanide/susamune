"""Execute production checkpoint observers with controlled retail event edges."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/split_events.cpp').read_text()
HEADER = (ROOT / 'include/susamune/split_stats.hxx').read_text()
ROUTES = {name: int(value, 0) for name, value in
          re.findall(r'(ROUTE_\w+)\s*=\s*(0x[0-9a-f]+|\d+)', HEADER)}


def function(signature):
    start = SOURCE.rindex(signature)
    brace = SOURCE.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end] + '\n'


class EventEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='moonshine-split-edges-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name) / 'edges.cpp'
        enum = HEADER[HEADER.index('enum RouteId'):HEADER.index('struct Summary')]
        red = SOURCE[SOURCE.index('struct RedDesc'):SOURCE.index('int recoveredPiantaIndex')]
        prelude = r'''
typedef unsigned char u8; typedef unsigned short u16;
typedef unsigned int u32; typedef int s32;
extern "C" int _fltused=0;
namespace SplitStats { ENUM }
struct TMarDirector { u8 mAreaID, mEpisodeID; u16 mGameState; } stage;
TMarDirector *sStageDirector=&stage;
struct Scene { u8 mAreaID, mEpisodeID; };
typedef Scene TGameSequence;
struct Application { Scene mNextScene,mCurrentScene,mPrevScene; } gpApplication;
int selectedEpisode=-1;
namespace ILing { int activeParentEpisode(u8) { return selectedEpisode; } }
u8 routeParentEpisode(u16,u8,u8);
struct Timer { u32 attemptSerial() { return 1; } } gQFTTimer;
u32 sAttemptSerial=1;
bool sAttemptInvalid,sCarryAttempt,sBlockNextAttempt;
volatile u16 capturedTarget;
#define SUSAMUNE_ADDR_QFT_TRANSITION_TARGET (&capturedTarget)
bool sceneMatches(const Scene &s,u8 a,u8 e) { return s.mAreaID==a&&s.mEpisodeID==e; }
struct TFlagManager {
 struct { s32 mGoldCoinCount; } Type4Flag;
 struct { bool mRedCoinSwitchPressed; } Type5Flag;
 struct { s32 mRedCoinCount,mBJRBalloonCount; } Type6Flag;
 static TFlagManager *smInstance;
} flags;
TFlagManager *TFlagManager::smInstance=&flags;
struct Vec { float x,y,z; };
struct TBaseNPC { const void *mDummyConnectActor; Vec mTranslation; const char *mKeyName; };
struct THitActor {};
struct TSpineEnemy { u8 mHealth; };
struct TMapObjBase { u16 mState; };
struct TShine { u32 vtable,mMapObjID; };
u16 sActiveRoute,sArmedCarryRoute,statsRoute;
u8 expected,sGatekeeperHits,sGenericTalkCount,sMirrorsCleared,sHanachanHits,sTinKoopaHits;
s32 sLastRedCoinCount,sPreGoldCoins,sPreBalloons;
void *sClearedMirrors[3];
bool sRetailDirectOpen,valid,sPinnaIntroTalkPending;
namespace SplitStats { bool routeActive(u16 r) { return r==statsRoute; } }
u32 emitted[16],emittedCount;
const u32 kEmarioVtable=1,kEnemyMarioVtable=2,kShineVtable=3;
u32 objectVtable(const void *p) { return p?*(const u32*)p:0; }
bool stageIdentityValid() { return valid&&!sAttemptInvalid; }
bool routeScene(u16 r,u8 a,u8 e) {
 return stageIdentityValid()&&r==sActiveRoute&&stage.mAreaID==a&&stage.mEpisodeID==routeParentEpisode(r,a,e);
}
bool hookScene(u16 r,u8 a,u8 e) { return sRetailDirectOpen&&routeScene(r,a,e); }
bool publishEvent(u16 r,u8 e) {
 if(r!=sActiveRoute||e!=expected||emittedCount==16)return false;
 emitted[emittedCount++]=e;++expected;return true;
}
int strcmp(const char *a,const char *b) { while(*a&&*a==*b){++a;++b;}return *a-*b; }
bool accept; s32 nextValue;
void retailItem(void*) {}
void retailCastle(void *p) { if(accept)((TMapObjBase*)p)->mState=(u16)nextValue; }
bool retailMirror(void *p,THitActor*,u32) { if(accept)*(s32*)((u8*)p+0x19c)=nextValue;return accept; }
bool retailRedSwitch(void *p,THitActor*,u32) { if(accept)((TMapObjBase*)p)->mState=(u16)nextValue;return accept; }
void retailHanachan(void *p) { if(accept)((TSpineEnemy*)p)->mHealth=(u8)nextValue; }
void retailMecha(void *p) { if(accept)*(s32*)((u8*)p+0x1c8)=nextValue; }
void retailMovie(TMarDirector *p,u8 movie) {
 if(!accept||(p->mGameState&0x100))return;
 if(movie==2)gpApplication.mNextScene={0,1};
 else if(movie==7)gpApplication.mNextScene={13,6};
 else if(movie==8)gpApplication.mNextScene={13,7};
 else if(movie==10)gpApplication.mNextScene={0x3b,0xff};
 else return;
 p->mGameState|=0x100;
}
void clearAttemptState() {
 sActiveRoute=0xffff;sGenericTalkCount=sTinKoopaHits=0;sPinnaIntroTalkPending=false;
}
u16 findActiveRoute() { return statsRoute; }
void samplePreDirect() {}
typedef bool (*ReceiveMessageFn)(void*,THitActor*,u32);
auto sMapObjAppearTrampoline=&retailItem;
auto sRedSwitchMessageTrampoline=&retailRedSwitch;
auto sSandCastleTrampoline=&retailCastle;
auto sMirrorMessageTrampoline=&retailMirror;
auto sHanachanDamageTrampoline=&retailHanachan;
auto sTinKoopaHitTrampoline=&retailMecha;
auto sStreamingMovieTrampoline=&retailMovie;
void retailOpen(void*,TBaseNPC*) {}
typedef void (*OpenTalkFn)(void*,TBaseNPC*);
auto sOpenTalkTrampoline=&retailOpen;
'''.replace('ENUM', enum)
        carry = SOURCE[SOURCE.index('struct CarryDesc'):SOURCE.index('const int kPiantaCount')]
        carry = carry[:carry.index('};',carry.index('const CarryDesc kCarryRoutes'))+2]
        bodies = ''.join(function(sig) for sig in (
            'u8 routeParentEpisode(',
            'bool isShadowRoute(', 'u8 shadowEvent(', 'bool hundredCourseTransition(',
            'bool pinnaOneParkScene()',
            'void armCarryTransition()', 'void beforeStageSetup()',
            'void onStageSetup(', 'void beginFrame()', 'void armPinnaOneRetailExit()',
            'void noteGatekeeper(', 'void noteTalk(', 'void updateCountEvents()',
            'extern "C" void susamuneSplitOpenTalk(',
            'extern "C" void susamuneSplitMapObjAppear(',
            'extern "C" bool susamuneSplitRedSwitchMessage(',
            'extern "C" void susamuneSplitSandCastle(',
            'extern "C" bool susamuneSplitMirrorMessage(',
            'extern "C" void susamuneSplitHanachanDamage(',
            'extern "C" void susamuneSplitTinKoopaHit(',
            'extern "C" void susamuneSplitStreamingMovie('))
        exports = r'''
extern "C" {
__declspec(dllexport) void reset(int r,int a,int e,int first) {
 sActiveRoute=statsRoute=(u16)r;stage={(u8)a,(u8)e,0};expected=(u8)first;
 sAttemptSerial=1;capturedTarget=0xffff;
 selectedEpisode=-1;sAttemptInvalid=sCarryAttempt=sBlockNextAttempt=false;
 sArmedCarryRoute=0xffff;sRetailDirectOpen=valid=true;sPinnaIntroTalkPending=false;
 sGatekeeperHits=sGenericTalkCount=sMirrorsCleared=sHanachanHits=sTinKoopaHits=0;
 sLastRedCoinCount=sPreGoldCoins=sPreBalloons=0;emittedCount=0;
 for(int i=0;i<3;++i)sClearedMirrors[i]=0;
 flags.Type4Flag.mGoldCoinCount=0;flags.Type5Flag.mRedCoinSwitchPressed=false;
 flags.Type6Flag.mRedCoinCount=flags.Type6Flag.mBJRBalloonCount=0;
}
__declspec(dllexport) int size() { return emittedCount; }
__declspec(dllexport) int eventAt(int i) { return emitted[i]; }
__declspec(dllexport) void enabled(int live,int identity) { sRetailDirectOpen=live;valid=identity; }
__declspec(dllexport) void redCoin(int n) { flags.Type6Flag.mRedCoinCount=n;noteRedCoin(); }
__declspec(dllexport) int redSwitchEdge(int before,int after,int message,int accepted) {
 TMapObjBase object={(u16)before};accept=accepted;nextValue=after;
 return susamuneSplitRedSwitchMessage(&object,0,message);
}
__declspec(dllexport) void redSwitch(int pressed) { redSwitchEdge(1,2,1,pressed); }
__declspec(dllexport) void counts(int goldBefore,int goldAfter,int ballBefore,int ballAfter) {
 sPreGoldCoins=goldBefore;flags.Type4Flag.mGoldCoinCount=goldAfter;
 sPreBalloons=ballBefore;flags.Type6Flag.mBJRBalloonCount=ballAfter;updateCountEvents();
}
__declspec(dllexport) void plant(int before,int after) { noteGatekeeper(0,0,0,(u8)before,(u8)after); }
__declspec(dllexport) void talk(int actor,const char *name) {
 u32 type=actor;TBaseNPC npc={&type,{0,0,0},name};noteTalk(&npc);
}
__declspec(dllexport) void introTalk(int carried,int live,int npcPresent) {
 sCarryAttempt=carried;onStageSetup(&stage);valid=live;sRetailDirectOpen=false;
 gpApplication.mCurrentScene={stage.mAreaID,stage.mEpisodeID};
 TBaseNPC npc={0,{0,0,0},0};susamuneSplitOpenTalk(0,npcPresent?&npc:0);
}
__declspec(dllexport) void nextFrame() { beginFrame(); }
__declspec(dllexport) void nextStage() { sCarryAttempt=false;onStageSetup(&stage); }
__declspec(dllexport) void castle(int before,int after,int accepted) {
 TMapObjBase object={(u16)before};accept=accepted;nextValue=after;susamuneSplitSandCastle(&object);
}
__declspec(dllexport) int mirror(int actor,int before,int after,int message,int accepted) {
 static u32 objects[4][128];void *p=objects[actor];*(s32*)((u8*)p+0x19c)=before;
 accept=accepted;nextValue=after;return susamuneSplitMirrorMessage(p,0,message);
}
__declspec(dllexport) void wiggler(int before,int after,int accepted) {
 TSpineEnemy object={(u8)before};accept=accepted;nextValue=after;susamuneSplitHanachanDamage(&object);
}
__declspec(dllexport) void mecha(int before,int after,int accepted) {
 u32 object[128];*(s32*)((u8*)object+0x1c8)=before;
 accept=accepted;nextValue=after;susamuneSplitTinKoopaHit(object);
}
__declspec(dllexport) void movie(int id,int queuedBefore,int accepted) {
 stage.mGameState=queuedBefore?0x100:0;accept=accepted;susamuneSplitStreamingMovie(&stage,(u8)id);
}
__declspec(dllexport) int armed() { return sArmedCarryRoute; }
__declspec(dllexport) void retailExit() { armPinnaOneRetailExit(); }
__declspec(dllexport) int completeTransition(int area,int episode,int movieDirector) {
 gpApplication.mNextScene={(u8)area,(u8)episode};armCarryTransition();
 gpApplication.mPrevScene=movieDirector?Scene{0xff,0}:Scene{stage.mAreaID,stage.mEpisodeID};
 gpApplication.mCurrentScene=gpApplication.mNextScene;beforeStageSetup();
 stage={(u8)area,(u8)episode,0};onStageSetup(&stage);beginFrame();
 return !sAttemptInvalid;
}
__declspec(dllexport) void selected(int episode) { selectedEpisode=episode; }
__declspec(dllexport) int transition(int target,int episode) {
 capturedTarget=(u16)target;gpApplication.mNextScene={(u8)target,(u8)episode};
 armCarryTransition();gpApplication.mPrevScene={stage.mAreaID,stage.mEpisodeID};
 gpApplication.mCurrentScene=gpApplication.mNextScene;beforeStageSetup();
 stage.mAreaID=(u8)target;stage.mEpisodeID=(u8)episode;return sCarryAttempt;
}
__declspec(dllexport) int carry(int r,int a,int b) { return hundredCourseTransition((u16)r,(u8)a,(u8)b); }
__declspec(dllexport) void shine(int id,int actualShine) {
 TShine object={actualShine?kShineVtable:4,(u32)id};susamuneSplitMapObjAppear(&object);
}
}
'''
        path.write_text(prelude + carry + red + bodies + exports)
        dll = path.with_suffix('.dll')
        subprocess.run([str(ROOT/'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                        '-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry','-O2','-fno-builtin',
                        '-mno-stack-arg-probe',str(path),'-o',str(dll)],check=True)
        cls.lib=C.CDLL(str(dll))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.talk.argtypes=[C.c_int,C.c_char_p]

    def reset(self,route,area,episode=0,first=0):
        self.lib.reset(ROUTES['ROUTE_'+route],area,episode,first)

    def events(self):
        return [self.lib.eventAt(i) for i in range(self.lib.size())]

    def test_pinna_automatic_intro_talk_waits_for_carried_live_frame(self):
        self.reset('PINNA_1', 0x0d, 6)
        self.lib.introTalk(1, 1, 1)
        self.assertEqual(self.events(), [])
        self.lib.nextFrame()
        self.assertEqual(self.events(), [0])
        self.lib.nextFrame()
        self.assertEqual(self.events(), [0])
        self.lib.mecha(4, 3, 1)  # The park cannot manufacture boss hits.
        self.assertEqual(self.events(), [0])

    def test_pinna_intro_talk_does_not_admit_wrong_route_scene_or_lifetime(self):
        for route, area, episode, carried, live, npc in (
            ('PINNA_1', 0x0d, 6, 0, 1, 1),
            ('PINNA_1', 0x0d, 6, 1, 0, 1),
            ('PINNA_1', 0x0d, 6, 1, 1, 0),
            ('PINNA_1', 0x0d, 5, 1, 1, 1),
            ('PINNA_8', 0x0d, 6, 1, 1, 1),
        ):
            self.reset(route, area, episode)
            self.lib.introTalk(carried, live, npc)
            self.lib.nextFrame()
            self.assertEqual(self.events(), [], (route, area, episode, carried, live, npc))
        self.reset('PINNA_1', 0x0d, 6)
        self.lib.introTalk(1, 1, 1)
        self.lib.nextStage()
        self.lib.nextFrame()
        self.assertEqual(self.events(), [])

    def test_red_thresholds_and_held_duplicates(self):
        self.reset('BIANCO_3_REDS',0x2f)
        for coins in (1,2,2,4,5,7,8,8):self.lib.redCoin(coins)
        self.assertEqual(self.events(),[0,1,2])

    def test_reds_require_live_matching_stage(self):
        for area,live,identity in ((2,1,1),(0x2f,0,1),(0x2f,1,0)):
            self.reset('BIANCO_3_REDS',area);self.lib.enabled(live,identity)
            self.lib.redCoin(8);self.assertEqual(self.events(),[])

    def test_all_full_reds_reuse_secret_thresholds_after_prefix(self):
        pairs=(('BIANCO_3',0x2f,1),('BIANCO_6',0x2e,1),('RICCO_4',0x30,2),
               ('GELATO_1',0x20,2),('PINNA_2',0x32,1),('PINNA_6',0x29,2),
               ('SIRENA_2',0x33,3),('SIRENA_4',0x28,3),('NOKI_6',0x1f,3),('PIANTA_5',0x2a,2))
        for name,area,first in pairs:
            thresholds=[]
            for coins in range(1,9):
                self.reset(name+'_REDS',area,first=1 if name in ('SIRENA_2','NOKI_6') else 0)
                self.lib.redCoin(coins);thresholds.append(len(self.events()))
            self.reset(name+'_FULL_REDS',area,first=first)
            for coins,n in enumerate(thresholds,1):
                self.lib.redCoin(coins);self.assertEqual(len(self.events()),n,(name,coins))

    def test_full_reds_cannot_skip_unfinished_prefix(self):
        self.reset('RICCO_4_FULL_REDS',0x30)
        self.lib.redCoin(8);self.assertEqual(self.events(),[])

    def test_button_is_captured_before_first_red_on_same_tick(self):
        for name,area,first in (('SIRENA_2_REDS',0x33,0),('NOKI_6_FULL_REDS',0x1f,2)):
            self.reset(name,area,first=first);self.lib.redSwitch(1)
            self.lib.redCoin(8);self.lib.redSwitch(1)
            self.assertEqual(self.events(),list(range(first,first+5)))

    def test_button_requires_accepted_initial_press_not_delayed_flag(self):
        for route,area in (('SIRENA_2_REDS',0x33),('NOKI_6_REDS',0x1f)):
            self.reset(route,area)
            for args in ((1,2,1,0),(1,2,0,1),(2,2,1,1),(1,1,1,1),(3,2,1,1)):
                self.lib.redSwitchEdge(*args);self.assertEqual(self.events(),[])
            self.lib.redSwitchEdge(1,2,1,1);self.assertEqual(self.events(),[0])

    def test_hundreds_use_five_thresholds_and_exclude_delfino(self):
        for route,area in (('BIANCO_100',2),('RICCO_100',3),('GELATO_100',4),('PINNA_100',13),
                           ('SIRENA_100',7),('NOKI_100',9),('PIANTA_100',8)):
            self.reset(route,area);self.lib.counts(0,100,0,0)
            self.assertEqual(self.events(),[0,1,2,3,4],route)
        self.reset('DELFINO_100',1);self.lib.counts(0,100,0,0);self.assertEqual(self.events(),[])

    def test_interior_carry_excludes_restarts_and_other_courses(self):
        for route,a,b,yes in (('PINNA_100',5,13,1),('PINNA_100',13,5,1),('SIRENA_100',7,14,1),
                              ('PINNA_100',5,5,0),('SIRENA_100',7,7,0),('SIRENA_100',7,9,0),
                              ('PINNA_8',5,13,0)):
            self.assertEqual(self.lib.carry(ROUTES['ROUTE_'+route],a,b),yes)

    def test_selected_pinna_beach_park_and_exact_secret_carry(self):
        for selected,park in enumerate((0,0,1,0,2,3,4,5)):
            self.reset('PINNA_6_FULL_REDS',5,selected);self.lib.selected(selected)
            self.assertEqual(self.lib.transition(13,park),1,selected)
            self.assertEqual(self.lib.transition(0x29,0),1,selected)
        self.reset('PINNA_6_FULL_REDS',5,2);self.lib.selected(2)
        self.assertEqual(self.lib.transition(13,2),0)

    def test_selected_sirena_intermediate_scenarios_and_exact_secrets(self):
        for selected,hotel in enumerate((0,0,1,2,2,0,3,4)):
            self.reset('SIRENA_2_FULL_REDS',6,selected);self.lib.selected(selected)
            self.assertEqual(self.lib.transition(7,hotel),1,selected)
            self.assertEqual(self.lib.transition(0x33,0),1,selected)
            self.reset('SIRENA_4_FULL_REDS',6,selected);self.lib.selected(selected)
            self.assertEqual(self.lib.transition(7,hotel),1,selected)
            self.assertEqual(self.lib.transition(14,int(selected==4)),1,selected)
            self.assertEqual(self.lib.transition(0x28,0),1,selected)
        self.reset('SIRENA_4_FULL_REDS',14,1);self.lib.selected(4)
        self.assertEqual(self.lib.transition(0x33,0),0)

    def test_balloon_counts_need_talk_prefix_and_exact_targets(self):
        self.reset('PINNA_8',13,5,first=1)
        self.lib.counts(0,0,0,5);self.assertEqual(self.events(),[])
        for before,after in ((5,6),(6,10),(10,11),(11,19),(19,20),(20,20)):
            self.lib.counts(0,0,before,after)
        self.assertEqual(self.events(),[1,2,3])
        self.reset('PINNA_8',13,5);self.lib.counts(0,0,0,20);self.assertEqual(self.events(),[])

    def test_plants_ignore_waking_healing_and_duplicate_hits(self):
        for route,first in (('BIANCO_PLANT',0),('TRAVEL_SKIP',0),('GELATO_PLANT',0),('AIRSTRIP_1',1),('BIANCO_1',1)):
            self.reset(route,1,first=first)
            for before,after in ((3,3),(2,3),(3,2),(2,2),(2,1),(1,0),(1,0)):
                self.lib.plant(before,after)
            self.assertEqual(self.events(),list(range(first,first+3)),route)

    def test_shadow_mario_only_splits_talking_to_connected_actor(self):
        for route,first in (('DELFINO_SHADOW_MARIO',0),('BIANCO_7',0),('SIRENA_7',1)):
            self.reset(route,7,3,first=first)
            self.lib.talk(0,b'ordinary');self.assertEqual(self.events(),[])
            self.lib.talk(1,b'dummy');self.lib.talk(1,b'dummy')
            self.assertEqual(self.events(),[first])

    def test_pinna_eight_retains_exact_ride_attendant(self):
        for route,area,episode,name,actor in (
            ('PINNA_8',13,5,'\u4fc2\u54e1\u30de\u30fc\u30ec'.encode('cp932'),0),):
            self.reset(route,area,episode);self.lib.talk(0,b'other')
            self.assertEqual(self.events(),[]);self.lib.talk(actor,name)
            self.assertEqual(self.events(),[0])

    def test_gelato_five_accepts_generic_talk_as_requested(self):
        self.reset('GELATO_5',4,4);self.lib.talk(0,b'dummy')
        self.assertEqual(self.events(),[0])

    def test_pinna_one_all_three_retail_park_scenarios_and_boss_carry(self):
        for episode in (0,6,7):
            self.reset('PINNA_1',13,episode);self.lib.talk(0,b'director')
            self.assertEqual(self.events(),[0],episode)
            self.assertEqual(self.lib.transition(0x3a,1),1,episode)
            self.lib.enabled(1,1)
            for health in (4,3,2,1):self.lib.mecha(health,health-1,1)
            self.assertEqual(self.events(),[0,1,2,3,4],episode)

    def test_pinna_one_natural_movies_preserve_complete_checkpoint_chain(self):
        self.reset('PINNA_1',13,0)
        self.lib.movie(7,0,1)
        self.assertEqual(self.lib.armed(),ROUTES['ROUTE_PINNA_1'])
        self.assertEqual(self.lib.completeTransition(13,6,1),1)
        self.lib.talk(0,b'director')
        self.assertEqual(self.lib.completeTransition(0x3a,1,0),1)
        for health in (4,3,2,1):self.lib.mecha(health,health-1,1)
        self.lib.movie(8,0,1)
        self.assertEqual(self.lib.completeTransition(13,7,1),1)
        self.assertEqual(self.events(),[0,1,2,3,4])

    def test_pinna_one_both_retail_exit_skips_preserve_complete_chain(self):
        self.reset('PINNA_1',13,0)
        self.lib.retailExit()
        self.assertEqual(self.lib.completeTransition(13,6,1),1)
        self.lib.talk(0,b'director')
        self.assertEqual(self.lib.completeTransition(0x3a,1,0),1)
        for health in (4,3,2,1):self.lib.mecha(health,health-1,1)
        self.lib.retailExit()
        self.assertEqual(self.lib.completeTransition(13,7,1),1)
        self.assertEqual(self.events(),[0,1,2,3,4])

    def test_pinna_movie_carry_rejects_wrong_scene_movie_and_stale_acceptance(self):
        for route,area,episode,movie,queued,accepted,live,identity in (
            ('PINNA_1',13,0,7,1,1,1,1),('PINNA_1',13,0,7,0,0,1,1),
            ('PINNA_1',13,0,7,0,1,0,1),('PINNA_1',13,0,7,0,1,1,0),
            ('PINNA_1',13,6,7,0,1,1,1),('PINNA_1',13,0,8,0,1,1,1),
            ('PINNA_1',13,6,10,0,1,1,1),
            ('PINNA_1',0x3a,0,8,0,1,1,1),('PINNA_8',13,0,7,0,1,1,1)):
            self.reset(route,area,episode);self.lib.enabled(live,identity)
            self.lib.movie(movie,queued,accepted)
            self.assertEqual(self.lib.armed(),0xffff,(route,area,episode,movie))

    def test_missing_first_movie_carry_invalidates_later_talk(self):
        self.reset('PINNA_1',13,0)
        self.assertEqual(self.lib.completeTransition(13,6,1),0)
        self.lib.talk(0,b'director')
        self.assertEqual(self.events(),[])

    def test_mirror_only_last_enemy_and_each_actor_once(self):
        self.reset('GELATO_2',4,1)
        for args in ((0,2,1,8,1),(0,1,0,1,1),(0,1,0,8,0)):
            self.lib.mirror(*args);self.assertEqual(self.events(),[])
        for actor in (0,0,1,2,3):self.lib.mirror(actor,1,0,8,1)
        self.assertEqual(self.events(),[0,1,2])

    def test_wiggler_and_mecha_only_accepted_damage(self):
        self.reset('GELATO_3',4,2)
        self.lib.wiggler(3,2,0);self.lib.wiggler(3,3,1);self.assertEqual(self.events(),[])
        for health in (3,2,1):self.lib.wiggler(health,health-1,1)
        self.assertEqual(self.events(),[0,1,2])
        self.reset('PINNA_1',0x3a,1,first=1)
        self.lib.mecha(4,3,0);self.assertEqual(self.events(),[])
        for health in (4,3,2,1):self.lib.mecha(health,health-1,1)
        self.assertEqual(self.events(),[1,2,3,4])

    def test_castle_only_actual_collision_enabled_spawn(self):
        self.reset('GELATO_1_FULL',4)
        for before,after,accepted in ((5,6,1),(6,7,0),(7,7,1)):
            self.lib.castle(before,after,accepted);self.assertEqual(self.events(),[])
        self.lib.castle(6,7,1);self.assertEqual(self.events(),[0])

    def test_fludd_movie_requires_new_accepted_movie_two(self):
        self.reset('AIRSTRIP_1',0)
        for args in ((1,0,1),(2,1,1),(2,0,0)):
            self.lib.movie(*args);self.assertEqual(self.events(),[])
        self.lib.movie(2,0,1);self.assertEqual(self.events(),[0])
        self.assertEqual(self.lib.armed(),ROUTES['ROUTE_AIRSTRIP_1'])

    def test_named_shine_appearance_and_rocket_prefix(self):
        for route,shine,area,episode,first in (('LIGHTHOUSE',93,1,2,0),('LEFT_BELL',96,1,2,0),
            ('RIGHT_BELL',97,1,2,1),('SHINE_GATE',99,1,2,1),('BEACH_SHINE',117,1,2,0),
            ('GOLD_BIRD',118,1,2,0),('NOKI_HIDDEN',59,9,6,1)):
            self.reset(route,area,episode,first);self.lib.shine(shine-1,1);self.lib.shine(shine,0)
            self.assertEqual(self.events(),[]);self.lib.shine(shine,1)
            self.assertEqual(self.events(),[first],route)


if __name__=='__main__':unittest.main()
