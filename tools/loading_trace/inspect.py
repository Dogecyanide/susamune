"""Summarize private buffered loading markers; IO rows can overlap in time."""
import argparse,json,re
from pathlib import Path
PHASES={1:'requested',2:'kick',3:'waiting for ghost',4:'departure committed',5:'stage loading',6:'object setup',7:'objects ready',8:'canceled'}
LOAD=re.compile(r'^(\d+) load p=(\d+) t=(\d+) hz=(\d+) s=([0-9a-fA-F]+) a=(\d+) lost=(\d+) iso=(\d+)/(\d+)/(\d+)(?:/(\d+))?$')
IO=re.compile(r'^(\d+) io (\w+) id=(\d+) p=(\d+) n=(\d+) ms=(\d+) r=(-?\d+)$')
def inspect(text):
 groups=[];events=[];io=[]
 def finish():
  if not events:return
  intervals=[]
  for before,after in zip(events,events[1:]):
   elapsed=None if before['hz']!=after['hz'] else ((after['tick']-before['tick'])&0xffffffff)*1000/before['hz']
   intervals.append({'from':before['phase'],'to':after['phase'],'ms':None if elapsed is None else round(elapsed,3)})
  groups.append({'events':events.copy(),'intervals':intervals,'completed':events[-1]['id'] in (7,8),'dropped':events[-1]['dropped']})
  events.clear()
 for line in text.splitlines():
  m=LOAD.fullmatch(line.strip())
  if m:
   a,phase,tick,hz,scene,value,dropped,calls,bytes_,ms,max_ms=m.groups();phase=int(phase);hz=int(hz)
   if phase not in PHASES or not hz:raise ValueError('Invalid loading marker')
   if phase==1:finish()
   events.append({'arm_tick':int(a),'id':phase,'phase':PHASES[phase],'tick':int(tick),'hz':hz,'scene':int(scene,16),'value':int(value),'dropped':int(dropped),'iso_calls':int(calls),'iso_bytes':int(bytes_),'iso_ms':int(ms),'iso_max_ms':int(max_ms) if max_ms is not None else None})
   if phase in (7,8):finish()
  m=IO.fullmatch(line.strip())
  if m:
   a,operation,identity,phase,bytes_,ms,result=m.groups();io.append({'arm_tick':int(a),'operation':operation,'id':int(identity),'phase':int(phase),'bytes':int(bytes_),'ms':int(ms),'result':int(result)})
 finish()
 return {'loads':groups,'io':io,'note':'PPC marker intervals use the recorded timer frequency. ISO counters are cumulative snapshots; IO timings can overlap and must not be summed as total load time.'}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('log');parser.add_argument('--output');args=parser.parse_args()
 result=json.dumps(inspect(Path(args.log).read_text(encoding='utf-8')),indent=2)
 if args.output:Path(args.output).write_text(result,encoding='utf-8')
 else:print(result)
