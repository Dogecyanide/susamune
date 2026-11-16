from pathlib import Path
import argparse, os, subprocess, sys
ROOT=Path(__file__).resolve().parents[2]
def build(output):
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    compiler=Path("C:/msys64/mingw64/bin/g++.exe") if sys.platform=="win32" else Path("g++")
    env=os.environ.copy()
    if sys.platform=="win32":env["PATH"]=str(compiler.parent)+os.pathsep+env["PATH"]
    command=[str(compiler),"-std=c++17","-O2","-shared","-DTIMEWARP_LIVE_RACING=1","-I",str(ROOT/"include"),str(Path(__file__).with_name("peer.cpp")),str(ROOT/"src/live_race_session.cpp"),"-o",str(output)]
    command += ["-static","-static-libgcc","-static-libstdc++"] if sys.platform=="win32" else ["-fPIC"]
    subprocess.run(command,env=env,check=True)
    return output
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("output");args=parser.parse_args();print(build(args.output))
