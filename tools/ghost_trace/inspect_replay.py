"""Decode a bounded replay-failure report and compare its actors to an MSGT capture."""
import argparse,collections,json,struct
from pathlib import Path
from inspect_trace import checksum,chunk_payload
NAMES=['magic','active','started','error','detail','generation','coordinator_error','coordinator_detail','source_frame','source_tick','played_frames','movement_calls','rng_calls','queued_rng','input_error','observed_flags','expected_flags','observed_stick_timer','expected_stick_timer','observed_disabled_frames','expected_disabled_frames','missing_evidence','state_bits','wait_reason','expected_scope','expected_status','expected_count','expected_hash','actual_scope','actual_status','actual_count','actual_hash']
OFFSETS=[('position',0x10),('rotation',0x30),('scale',0x24),('linear_velocity',0x94),('angular_velocity',0xa0),('velocity',0xac)]
def actor(raw):
 fields={'name_key':struct.unpack_from('>H',raw,8)[0],'type':struct.unpack_from('>I',raw,0x4c)[0],'instance':struct.unpack_from('>h',raw,0x7c)[0],'manager':struct.unpack_from('>I',raw,0x70)[0]}
 for group,at in OFFSETS:
  for axis in range(3):
   value=struct.unpack_from('>I',raw,at+axis*4)[0];fields[group+'_'+'xyz'[axis]]=value if value&0x7fffffff else 0
 fields['hit_flags']=struct.unpack_from('>I',raw,0x64)[0];fields['live_flags']=struct.unpack_from('>I',raw,0xf0)[0]
 return fields

def source_at(path,frame):
 actors={};witness=None;scene=None
 with Path(path).open('rb') as f:
  header=struct.unpack('>16I',f.read(64));assert header[0]==0x4d535452
  while True:
   block=f.read(32);assert len(block)==32;values=struct.unpack('>8I',block)
   if values[0]==0x444f4e45:break
   raw=chunk_payload(f,values,header[1]);assert checksum(raw)==values[3];at=0
   while at<len(raw):
    kind,size,n,tick=struct.unpack_from('>HHII',raw,at);at+=12;body=raw[at:at+size];at+=size
    if n>frame:return actors,witness
    if kind==2:
     next_scene=struct.unpack_from('>I',body)[0]
     if scene is not None and scene!=next_scene:actors.clear()
     scene=next_scene
    if kind==6:
     ident,pointer,total,created,*masks=struct.unpack_from('>7I',body)
     assert total in (0xf4,0x150) and not sum(mask<<(i*32) for i,mask in enumerate(masks))>>(total//4)
     if created:actors[ident]={'pointer':pointer,'raw':bytearray(total)}
     assert ident in actors and len(actors[ident]['raw'])==total
     cursor=28
     for word in range(total//4):
      if masks[word//32]&(1<<(word%32)):actors[ident]['raw'][word*4:word*4+4]=body[cursor:cursor+4];cursor+=4
     assert cursor==len(body)
    elif kind==7:actors.pop(struct.unpack('>I',body)[0],None)
    elif kind==26 and n==frame:witness=struct.unpack('>5I',body)
 return actors,witness

def decode(path,source=None):
 data=Path(path).read_bytes();assert len(data)>=352 and len(data)<=0x60000+32
 h=struct.unpack_from('>16I',data);end=struct.unpack_from('>8I',data,len(data)-32)
 assert h[0:3]==(0x4d535250,1,64) and h[3]+32==len(data) and h[10]==256 and h[15]==0
 assert h[3]==320+h[9]*256 and h[9]<=1024
 assert end[0:2]==(0x4d535245,1) and end[4]==h[3] and end[5]==checksum(data[:-32]) and end[6:]==(0,0)
 status=dict(zip(NAMES,struct.unpack_from('>32I',data,64)))
 actual=[]
 for i in range(h[9]):
  row=data[320+i*256:576+i*256];assert row[252:]==bytes(4)
  pointer,ordinal=struct.unpack_from('>2I',row);actual.append({'pointer':pointer,'ordinal':ordinal,**actor(row[8:252])})
 result={'game':hex(h[4]),'file_nonce':hex(h[5]),'run':hex(h[6]),'status':status,'snapshot':{'status':h[11],'hash':h[12],'scope':h[13],'count':h[14]},'actors':len(actual),'snapshot_matches_observation':h[11]==status['actual_status'] and h[12]==status['actual_hash'] and h[14]==status['actual_count']}
 result['visual']={name:{'flags':struct.unpack_from('>I',data,at)[0],'qf':struct.unpack_from('>i',data,at+4)[0],'scene':struct.unpack_from('>I',data,at+8)[0],'position':struct.unpack_from('>3f',data,at+12)} for name,at in (('expected',192),('actual',256))}
 if source and status['error']==119 and result['snapshot_matches_observation']:
  expected,witness=source_at(source,status['source_frame']);ordered=[actor(v['raw']) for _,v in sorted(expected.items())]
  key=lambda a:(a['name_key'],a['type'],a['instance'])
  by_key=collections.defaultdict(list)
  for a in ordered:by_key[key(a)].append(a)
  differences=[]
  for a in actual:
   candidates=by_key[key(a)]
   if not candidates:differences.append({'ordinal':a['ordinal'],'identity':key(a),'missing_source_actor':True});continue
   e=candidates.pop(0)
   changes={name:{'expected':hex(e[name]),'actual':hex(a[name])} for name in e if name not in ('manager','name_key','type','instance') and e[name]!=a[name]}
   if changes:differences.append({'ordinal':a['ordinal'],'identity':key(a),'fields':changes})
  result.update(source_actors=len(ordered),source_witness=witness,different_actors=len(differences),first_differences=differences[:24],unmatched_source=sum(len(v) for v in by_key.values()))
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('report');p.add_argument('--source');p.add_argument('--output');a=p.parse_args();r=decode(a.report,a.source);text=json.dumps(r,indent=2)
 if a.output:Path(a.output).write_text(text,encoding='utf-8')
 else:print(text)
