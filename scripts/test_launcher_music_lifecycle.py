"""Exercise production music lifetime across the early-start IOS pause."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_timer_creation import function
ROOT=Path(__file__).resolve().parents[1]

class MusicLifecycleTests(unittest.TestCase):
    def test_pause_loop_and_shutdown(self):
        source=(ROOT/'launcher/loader/source/SusamuneMusic.c').read_text()
        code=r"""
#include <cassert>
#include <cstdio>
using u32=unsigned;using s32=int;
static s32 sBufferSize;static bool sAudioReady,sPlaying,sSuspended;
static char sWarning[160];static int starts,inits,mp3inits,stops,ends,invalidates;
static bool mixerPaused,decoder;static int failure;
#define MUSIC_BUFFER ((void*)0x91f00000)
static void gprintf(const char*,...) {}
static void LogHeap(const char*) {}
static void ASND_Init(){++inits;}
static void MP3Player_Init(){++mp3inits;}
static void ASND_Pause(int p){mixerPaused=p;}
static int MP3Player_PlayBuffer(void*,int,void*){++starts;if(failure)return -1;decoder=true;return 0;}
static bool MP3Player_IsPlaying(){return decoder;}
static void MP3Player_Stop(){assert(!mixerPaused);assert(!sPlaying);++stops;decoder=false;}
static void ASND_End(){assert(!decoder);++ends;}
static void DCInvalidateRange(void*,unsigned n){assert(!decoder);assert(n==128);++invalidates;}
"""
        for signature in ('ReleaseMusicBuffer', 'SusamuneMusicInit',
                          'SusamuneMusicStart', 'SusamuneMusicPause',
                          'SusamuneMusicService', 'SusamuneMusicShutdown'):
            code+=function(source,signature)+'\n'
        code+=r"""
int main(){
 SusamuneMusicInit();SusamuneMusicInit();assert(inits==1&&mp3inits==1);
 assert(!SusamuneMusicStart());sBufferSize=127;
 assert(SusamuneMusicStart());assert(SusamuneMusicStart());assert(starts==1);
 SusamuneMusicPause(true);decoder=false;SusamuneMusicService();assert(starts==1);
 SusamuneMusicPause(false);SusamuneMusicService();assert(starts==2&&decoder);
 SusamuneMusicPause(true);SusamuneMusicShutdown();
 assert(stops==1&&ends==1&&invalidates==1&&!sBufferSize&&!sSuspended);
 SusamuneMusicShutdown();assert(ends==1&&invalidates==1);
 SusamuneMusicInit();sBufferSize=127;failure=1;assert(!SusamuneMusicStart());
 SusamuneMusicService();assert(starts==3);SusamuneMusicShutdown();
 assert(stops==1&&ends==2&&invalidates==2);
}
"""
        with tempfile.TemporaryDirectory(prefix='music-lifecycle-') as temp:
            path=Path(temp);(path/'test.cpp').write_text(code)
            compiler='C:/msys64/mingw64/bin/g++.exe' if os.name=='nt' else 'g++'
            env=dict(os.environ,PATH=str(Path(compiler).parent)+os.pathsep+os.environ.get('PATH',''))
            subprocess.run([compiler,'-std=c++17','-static',str(path/'test.cpp'),'-o',str(path/'test.exe')],check=True,capture_output=True,env=env)
            subprocess.run([str(path/'test.exe')],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
