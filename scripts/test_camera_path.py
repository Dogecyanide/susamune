"""Exercise real camera-path interpolation, timing and editing boundaries."""
import os, pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class CameraPathTests(unittest.TestCase):
    def test_path_playback_and_editing(self):
        source=r'''#include "CAMERA_HEADER"
#include <cassert>
#include <cmath>
using namespace CameraPath;
int main(){
 Path p={}; Pose a={0,0,0,3.1f,0,45}, b={100,50,-30,-3.1f,0.5f,60}, out={};
 assert(!p.start(out)); assert(p.add(a)); assert(!p.start(out)); assert(p.add(b));
 p.linear=true; p.frames[1].halves=4; assert(p.start(out)); assert(out.x==0);
 assert(p.advance(1,out)); assert(out.x==50 && out.y==25 && out.fov==52.5f);
 assert(std::fabs(std::fabs(out.yaw)-3.14159265f)<0.0001f);
 assert(p.advance(1,out)); assert(!p.playing && out.x==100 && out.yaw==b.yaw);
 assert(!p.advance(1,out));
 p.linear=false; assert(p.start(out)); p.advance(.5f,out); assert(std::fabs(out.x-15.625f)<.001f);
 p.advance(20,out); assert(!p.playing && out.x==100);
 p.loop=true; p.linear=true; p.frames[0].halves=2; p.start(out); p.advance(2.5f,out);
 assert(p.playing && std::fabs(out.x-50)<.001f); p.advance(.5f,out); assert(out.x==0);
 p.stop(); p.selected=0; p.erase(); assert(p.count==1 && p.selected==0 && p.frames[0].pose.x==100);
 p.erase(); assert(p.count==0 && p.selected==0 && !p.playing);
 for(int i=0;i<16;++i)assert(p.add(a)); assert(!p.add(b)); assert(p.count==16);
 p.clear(); assert(!p.count && !p.playing); p.add(a); p.add(b); p.loop=false; p.linear=true;
 Path q=p; Pose x,y; p.start(x);q.start(y);
 for(int i=0;i<30;++i)p.advance(1.0f/30,x);
 for(int i=0;i<60;++i)q.advance(1.0f/60,y);
 assert(std::fabs(x.x-y.x)<.001f);
 p.stop(); assert(!p.advance(1,x));
}
'''
        compiler = shutil.which('g++') or ('C:/msys64/mingw64/bin/g++.exe' if pathlib.Path('C:/msys64/mingw64/bin/g++.exe').is_file() else None)
        if not compiler: self.skipTest('host C++ compiler unavailable')
        env=dict(os.environ, PATH=str(pathlib.Path(compiler).parent)+os.pathsep+os.environ.get('PATH',''))
        with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='test-camera-path-') as d:
            path=pathlib.Path(d);(path/'test.cpp').write_text(source.replace('CAMERA_HEADER',(ROOT/'include/susamune/camera_path.hxx').as_posix()))
            subprocess.run([compiler,'-std=c++17','-O2',str(path/'test.cpp'),'-o',str(path/'test.exe')],check=True,env=env)
            subprocess.run([str(path/'test.exe')],check=True,env=env)
if __name__=='__main__': unittest.main()
