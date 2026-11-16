"""Exercise provider lifecycle and the native online/local render selection bridge."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'src/ghost.cpp').read_text(encoding='utf-8')

def function(signature):
    at=SOURCE.index(signature);brace=SOURCE.index('{',at);depth=0
    for end in range(brace,len(SOURCE)):
        if SOURCE[end]=='{':depth+=1
        elif SOURCE[end]=='}':
            depth-=1
            if not depth:return SOURCE[at:end+1]
    raise AssertionError(signature)

FIXTURE=r'''
#define TIMEWARP_LIVE_RACING 1
#include "susamune/ghost_visual_provider.hxx"
#include <limits>
namespace {
struct Source { bool valid;unsigned ready,generation,bad,calls,history;int qf[2]; } source;
GhostVisualProvider::Provider providers[2];unsigned generations[2];
Ghost::VisualState rendered;GhostVisualProvider::Frame latched;
GhostCamera::View cameraView;unsigned pathCount;
bool preparing,watching;int onlineModel;unsigned groupPlayers;
bool sourceValid(void *context,unsigned generation) { auto &s=*static_cast<Source*>(context);return s.valid&&s.generation==generation; }
bool sourceCamera(void *,const GhostVisualProvider::Query &q,GhostCamera::View &out) {
    out={{float(q.qf),2,3},{0,0,0,1},45};if(source.bad==6)out.rotation[3]=0;return true;
}
bool sourcePath(void *,const GhostVisualProvider::Query &,SusamuneGhostPoseSample *out,unsigned capacity,unsigned &count) {
    if(capacity!=97)return false;
    count=source.bad==7?98:2;out[0]={};out[1]={};out[1].x[2]=80;
    if(source.bad==8){out[1].x[0]=0x7f;out[1].x[1]=0xff;out[1].x[2]=0xff;}return true;
}
bool sourceSample(void *context,const GhostVisualProvider::Query &query,GhostVisualProvider::Frame &out) {
    auto &s=*static_cast<Source*>(context);++s.calls;s.qf[query.runner]=query.qf;
    if(query.flags&GhostVisualProvider::HISTORY)++s.history;
    if(!(s.ready&(1u<<query.runner)))return false;
    GhostTraceIndex::Sample sample={};sample.frame=1;sample.qf=query.qf;sample.x=float(query.qf);sample.y=10;sample.z=-20;
    sample.yaw=-1234;sample.animationId=78;sample.animationPhase=321;sample.heldObjectId=0x40000016;
    sample.heldNameKey=0x1234;sample.yoshi=3;sample.visible=1;sample.fludd.mode=0x18;sample.fludd.power=65;
    sample.raw.buttons=0x100;sample.raw.stickX=-40;sample.flags=GhostTraceIndex::POSE|GhostTraceIndex::QFT|GhostTraceIndex::INPUT;
    if(!GhostVisualProvider::fromSample(sample,55,out))return false;
    out.runFlags=0x21;
    if(s.bad==1)out.visual.x=std::numeric_limits<float>::infinity();
    if(s.bad==2)out.visual.animationId=336;
    if(s.bad==3)out.input.flags=1;
    if(s.bad==4)out.runFlags=0x20;
    if(s.bad==5)out.visual.fludd.mode=255;
    return true;
}
}
extern "C" float retailSquareRoot(float) asm("sqrtf__3stdFf");
extern "C" float retailSquareRoot(float value){return __builtin_sqrtf(value);}
namespace GhostCamera {bool captureView(View*){return false;}}
namespace LiveRace {
struct Group { struct {unsigned players;} config; } group;
const Group *groupState(){group.config.players=groupPlayers;return groupPlayers?&group:nullptr;}
int opponentModel(){return onlineModel;}
}
namespace LiveGhost {
bool visualState(Ghost::VisualState *out){*out={};out->x=900;out->visible=true;return true;}
bool visualStateFor(unsigned runner,Ghost::VisualState *out){*out={};out->x=float(1000+runner);out->visible=true;return true;}
}
namespace Ghost {
bool observerPreparing(){return preparing;}
bool observerStatsSuppressed(){return watching;}
bool visualState(VisualState *out){GhostVisualProvider::Frame frame;if(!GhostVisualProvider::read(0,frame))return false;*out=frame.visual;return true;}
bool secondaryVisualState(VisualState *out){GhostVisualProvider::Frame frame;if(!GhostVisualProvider::read(1,frame))return false;*out=frame.visual;return true;}
__RENDER_FUNCTION__
}
#define API extern "C" __declspec(dllexport)
API void reset(){GhostVisualProvider::stopActive();providers[0]={};providers[1]={};source={true,3,7,0,0,0,{0,0}};preparing=watching=false;onlineModel=-1;groupPlayers=0;}
API int prepare(unsigned n,unsigned count){GhostVisualProvider::Config config={&source,sourceValid,sourceSample,count,7,55,sourceCamera,sourcePath};return GhostVisualProvider::prepare(providers[n],config,generations[n]);}
API int activate(unsigned n,unsigned generation){return GhostVisualProvider::activate(providers[n],generation?generation:generations[n]);}
API int stop(unsigned n,unsigned generation){return GhostVisualProvider::stop(providers[n],generation?generation:generations[n]);}
API int prepare_alias(){return GhostVisualProvider::prepare(providers[0],providers[0].config,generations[0]);}
API int output_alias(){return GhostVisualProvider::prepare(providers[0],providers[0].config,providers[0].generation);}
API unsigned generation(unsigned n){return generations[n];}
API int active(){return GhostVisualProvider::active();}
API void valid(int value){source.valid=value!=0;}
API void ready(unsigned value){source.ready=value;}
API void bad(unsigned value){source.bad=value;}
API void source_generation(unsigned value){source.generation=value;}
API int refresh(int first,int second,int pair) {
    GhostVisualProvider::Query queries[2]={{0,0,0x204,1,0,first,0,0,255,0},{1,0,0x204,1,66,second,0,0,255,0}};
    return GhostVisualProvider::refresh(queries,GhostVisualProvider::runners(),pair!=0);
}
API int read(unsigned runner){return GhostVisualProvider::read(runner,latched);}
API unsigned token(){return latched.visual.recordingToken;}
API unsigned input_buttons(){return latched.input.buttons;}
API int input_stick(){return latched.input.stickX;}
API unsigned flags(){return latched.runFlags;}
API unsigned phase(){return latched.visual.animationPhase;}
API unsigned held(){return latched.visual.heldObjectId;}
API unsigned yoshi(){return latched.visual.yoshi;}
API unsigned water(){return latched.visual.fludd.power;}
API float x(){return latched.visual.x;}
API unsigned calls(){return source.calls;}
API int qf(unsigned runner){return source.qf[runner];}
API int camera_available(){return GhostVisualProvider::cameraAvailable();}
API int camera(int qf){GhostVisualProvider::Query q={0,0,0x204,1,0,qf,GhostVisualProvider::WATCH,0,255,0};return GhostVisualProvider::camera(q,cameraView);}
API float camera_x(){return cameraView.position[0];}
API int path(){GhostVisualProvider::Query q={0,0,0x204,1,0,100,GhostVisualProvider::WATCH,0,255,0};const SusamuneGhostPoseSample *points;return GhostVisualProvider::path(q,points,pathCount);}
API unsigned path_count(){return pathCount;}
API void suspend(){GhostVisualProvider::suspend();}
API int history(int qf){GhostVisualProvider::Query query={0,0,0x204,1,99,qf,GhostVisualProvider::WATCH|GhostVisualProvider::HISTORY,0,255,0};return GhostVisualProvider::historical(query,latched);}
API int render(unsigned runner){return Ghost::renderVisualState(runner,&rendered);}
API float render_x(){return rendered.x;}
API void online(int model,unsigned group,int watch){onlineModel=model;groupPlayers=group;watching=watch!=0;}
'''

class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='moonshine-visual-provider-');cls.addClassCleanup(cls.temp.cleanup)
        out=Path(cls.temp.name)
        fixture=FIXTURE.replace('__RENDER_FUNCTION__',function('bool renderVisualState(unsigned int runner, VisualState *out)'))
        (out/'fixture.cpp').write_text(fixture,encoding='utf-8')
        env=dict(os.environ,PATH='C:/msys64/mingw64/bin;'+os.environ['PATH'])
        run=subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-builtin-declaration-mismatch','-shared','-static','-I',str(ROOT/'include'),str(out/'fixture.cpp'),str(ROOT/'src/ghost_visual_provider.cpp'),str(ROOT/'src/ghost_camera_track.cpp'),'-o',str(out/'provider.dll')],env=env,capture_output=True,text=True,encoding='utf-8')
        if run.returncode:raise RuntimeError(run.stderr)
        cls.lib=C.CDLL(str(out/'provider.dll'));cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.x.restype=cls.lib.render_x.restype=cls.lib.camera_x.restype=C.c_float
    def setUp(self):self.lib.reset()
    def activate(self,count=2):
        self.assertEqual(self.lib.prepare(0,count),1);self.assertEqual(self.lib.activate(0,0),1)
    def test_explicit_prepare_and_validated_activation(self):
        self.assertEqual(self.lib.active(),0);self.assertEqual(self.lib.activate(0,1),0)
        self.lib.valid(0);self.assertEqual(self.lib.prepare(0,2),0)
        self.lib.valid(1);self.assertEqual(self.lib.prepare(0,2),1)
        self.lib.valid(0);self.assertEqual(self.lib.activate(0,0),0)
        self.assertEqual(self.lib.active(),0)
    def test_generation_ownership_and_replacement(self):
        self.activate();old=self.lib.generation(0)
        self.assertEqual(self.lib.prepare(0,2),0)
        self.assertEqual(self.lib.prepare(1,2),1);self.assertEqual(self.lib.activate(1,0),0)
        self.assertEqual(self.lib.stop(0,old+1),0);self.assertEqual(self.lib.stop(0,old),1)
        self.assertEqual(self.lib.prepare(0,1),1);self.assertGreater(self.lib.generation(0),old)
        self.assertEqual(self.lib.activate(0,old),0);self.assertEqual(self.lib.activate(0,0),1)
        self.assertEqual(self.lib.stop(0,old),0)
    def test_reprepare_copies_config_before_clearing_and_rejects_output_alias(self):
        self.assertEqual(self.lib.prepare(0,2),1)
        old=self.lib.generation(0)
        self.assertEqual(self.lib.output_alias(),0)
        self.assertEqual(self.lib.prepare_alias(),1)
        self.assertGreater(self.lib.generation(0),old)
        self.assertEqual(self.lib.activate(0,0),1)
        self.assertEqual(self.lib.refresh(100,140,1),1)

    def test_fields_input_and_exact_primary_secondary_clocks(self):
        self.activate();self.assertEqual(self.lib.refresh(100,148,1),1)
        self.assertEqual((self.lib.qf(0),self.lib.qf(1)),(100,148))
        for runner,token,x in ((0,55,100),(1,66,148)):
            self.assertEqual(self.lib.read(runner),1);self.assertEqual(self.lib.x(),x)
            self.assertEqual(self.lib.token(),token);self.assertEqual(self.lib.input_buttons(),0x100)
            self.assertEqual(self.lib.input_stick(),-40);self.assertEqual(self.lib.phase(),321)
            self.assertEqual(self.lib.held(),0x40000016);self.assertEqual(self.lib.yoshi(),3)
            self.assertEqual(self.lib.water(),65);self.assertEqual(self.lib.flags(),0x21)
    def test_watch_pair_cannot_publish_half_ready_frame(self):
        self.activate();self.assertEqual(self.lib.refresh(100,140,1),1)
        self.lib.ready(1);self.assertEqual(self.lib.refresh(104,144,1),0)
        self.assertEqual(self.lib.read(0),0);self.assertEqual(self.lib.read(1),0)
        self.assertEqual(self.lib.refresh(104,144,0),1)
        self.assertEqual(self.lib.read(0),1);self.assertEqual(self.lib.read(1),0)
    def test_invalid_source_or_samples_hide_without_stale_fallback(self):
        self.activate();self.assertEqual(self.lib.refresh(100,140,1),1)
        self.lib.source_generation(8);self.assertEqual(self.lib.refresh(104,144,1),0)
        self.assertEqual(self.lib.read(0),0)
        self.lib.source_generation(7)
        for bad in range(1,6):
            self.lib.bad(bad);self.assertEqual(self.lib.refresh(104,144,1),0)
            self.assertEqual(self.lib.read(0),0)
    def test_history_does_not_change_current_pair(self):
        self.activate();self.assertEqual(self.lib.refresh(100,140,1),1)
        self.assertEqual(self.lib.history(80),1);self.assertEqual(self.lib.x(),80)
        self.assertEqual(self.lib.token(),99);self.assertEqual(self.lib.read(0),1)
        self.assertEqual(self.lib.x(),100);self.assertEqual(self.lib.token(),55)
        self.lib.suspend();self.assertEqual(self.lib.read(0),0)
    def test_native_online_selection_keeps_priority(self):
        self.activate();self.assertEqual(self.lib.refresh(100,140,1),1)
        self.assertEqual(self.lib.render(1),1);self.assertEqual(self.lib.render_x(),140)
        self.lib.online(0,0,0);self.assertEqual(self.lib.render(1),1);self.assertEqual(self.lib.render_x(),900)
        self.lib.online(0,3,0)
        self.assertEqual(self.lib.render(0),1);self.assertEqual(self.lib.render_x(),1000)
        self.assertEqual(self.lib.render(1),1);self.assertEqual(self.lib.render_x(),1001)
        self.assertEqual(self.lib.render(2),0)
        self.lib.online(0,3,1);self.assertEqual(self.lib.render(1),1);self.assertEqual(self.lib.render_x(),140)
    def test_bounded_camera_and_path_callbacks_use_validated_source(self):
        self.assertEqual(self.lib.camera_available(),0)
        self.activate();self.assertEqual(self.lib.camera_available(),1)
        self.assertEqual(self.lib.camera(100),0)
        self.assertEqual(self.lib.refresh(100,140,1),1)
        self.assertEqual(self.lib.camera(102),1);self.assertEqual(self.lib.camera_x(),102)
        self.assertEqual(self.lib.path(),1);self.assertEqual(self.lib.path_count(),2)
        self.lib.bad(6);self.assertEqual(self.lib.camera(102),0)
        for bad in (7,8):
            self.lib.bad(bad);self.assertEqual(self.lib.path(),0);self.assertEqual(self.lib.path_count(),0)
        self.lib.bad(0);self.lib.valid(0)
        self.assertEqual(self.lib.path(),0);self.assertEqual(self.lib.camera(102),0)

    def test_native_intercepts_precede_resident_sampling(self):
        for signature,old in [('void updatePlayback(s32 qf)','playbackSegmentAt(qf)'),('void updateObserverVisual(s32 qf)','sampleObserverTrack('),('bool visualState(VisualState *out)','sGhostPosition.x'),('bool secondaryVisualState(VisualState *out)','sSecondaryGhostPosition.x')]:
            body=function(signature);self.assertLess(body.index('GhostVisualProvider::'),body.index(old))
        body=function('void refreshProvidedVisual(s32 qf, bool watch)')
        self.assertLess(body.index('OSIsThreadTerminated'),body.index('GhostVisualProvider::refresh'))
        self.assertIn('sObserverSecondaryOffset',body)
        self.assertIn('watch && count == 2',body)
        self.assertIn('LiveRace::opponentModel() >= 0',body)
        self.assertLess(body.index('LiveRace::groupState()'),body.index('GhostVisualProvider::refresh'))
        for signature in ('void init()','void stopAll()','void clearPlayback()'):
            self.assertIn('GhostVisualProvider::stopActive()',function(signature))
        self.assertIn('GhostVisualProvider::active()',function('bool recordedCameraAvailable()'))
        self.assertIn('GhostVisualProvider::active()',function('bool takeOverObserver()'))
        self.assertIn('GhostVisualProvider::path(',function('void draw(Menu *menu)'))

if __name__=='__main__':unittest.main()
