"""Validate and summarize experimental MSTR captures without loading the whole file."""
from pathlib import Path
import argparse, collections, json, math, struct
MAGIC=0x4d535452
BRANCH_HEADER_TAG=0x42524348
BRANCH_HEADER_FLAGS=0x23
PROVENANCE_TAG=0x50525631
CONTINUATION_CAPABILITY=1<<21
KINDS={1:'session',2:'frame',3:'Mario',4:'camera',5:'flags',6:'actor',7:'actor_removed',8:'FLUDD',9:'Yoshi',10:'sound',11:'particle',12:'end',13:'world_summary',14:'controller',15:'RNG_call',16:'water_request',17:'identity',18:'RNG_block',19:'contact',20:'controller_delta',21:'camera_metadata',22:'stage_start',23:'visual',24:'pad_mirrors',25:'pad_mirrors_delta',26:'world_witness',28:'run_provenance',29:'observation'}
def checksum(data):
 h=2166136261
 for b in data:h=((h^b)*16777619)&0xffffffff
 return h


def apply_blob(payload,version,states,kind):
 if len(payload)<16:raise ValueError('Truncated native byte block')
 pointer,offset,total,field=struct.unpack_from('>4I',payload);delta=bool(field&0x80000000);n=field&0x7fffffff
 if not 0<total<=8192 or not 0<n<=512 or offset+n>total or offset%512 or n!=min(512,total-offset) or pointer&3 or not 0x80000000<=pointer<=0x81800000-total:raise ValueError('Invalid native byte block')
 previous=states.get(kind)
 if previous is None or previous[0]!=pointer or len(previous[1])!=total:
  previous=(pointer,bytearray(total),set());states[kind]=previous
 data,seen=previous[1:]
 if delta:
  if version<2 or n&3 or offset not in seen:raise ValueError('Delta lacks a literal baseline')
  masks=(n+127)//128
  if len(payload)<16+4*masks:raise ValueError('Truncated delta mask')
  words=struct.unpack_from('>'+str(masks)+'I',payload,16);pos=16+4*masks
  if any(mask>>(min(32,n//4-32*i)) for i,mask in enumerate(words)):raise ValueError('Delta mask exceeds block')
  for i in range(n//4):
   if words[i//32]&(1<<(i%32)):
    if pos+4>len(payload):raise ValueError('Truncated delta word')
    data[offset+4*i:offset+4*i+4]=payload[pos:pos+4];pos+=4
  if pos!=len(payload):raise ValueError('Extra delta words')
 else:
  if len(payload)!=16+n:raise ValueError('Literal block length mismatch')
  data[offset:offset+n]=payload[16:];seen.add(offset)


def exact(stream,size):
 data=stream.read(size)
 if len(data)!=size:raise ValueError(f'Truncated capture at {stream.tell():#x}')
 return data

def decode_lz4(data,expected):
 if not 0<expected<=0x4000:raise ValueError('LZ4 output exceeds block limit')
 out=bytearray();pos=0
 def length(value):
  nonlocal pos
  if value==15:
   while True:
    if pos>=len(data):raise ValueError('Truncated LZ4 length')
    extra=data[pos];pos+=1;value+=extra
    if value>expected:raise ValueError('LZ4 length exceeds output')
    if extra!=255:break
  return value
 while pos<len(data):
  token=data[pos];pos+=1;literal=length(token>>4)
  if literal>len(data)-pos or literal>expected-len(out):raise ValueError('Invalid LZ4 literals')
  out.extend(data[pos:pos+literal]);pos+=literal
  if pos==len(data):break
  if pos+2>len(data):raise ValueError('Truncated LZ4 offset')
  distance=data[pos]|(data[pos+1]<<8);pos+=2
  if not distance or distance>len(out):raise ValueError('Invalid LZ4 offset')
  count=length(token&15)+4
  if count>expected-len(out):raise ValueError('LZ4 match exceeds output')
  pattern=out[-distance:];out.extend((pattern*((count+distance-1)//distance))[:count])
 if len(out)!=expected:raise ValueError('LZ4 output size mismatch')
 return bytes(out)

def chunk_payload(stream,values,version,end=None):
 def take(size):
  if end is not None and size>end-stream.tell():raise ValueError('Chunk overlaps completion footer')
  return exact(stream,size)
 size,codec,block_size=values[2],values[6],values[7]
 if not codec and not block_size:return take(size)
 if version<3 or codec!=1 or block_size!=0x4000:raise ValueError('Unsupported chunk compression')
 out=bytearray()
 while len(out)<size:
  raw,stored=struct.unpack('>2I',take(8));compressed=bool(stored&0x80000000);stored&=0x7fffffff
  if not 0<raw<=min(block_size,size-len(out)) or not 0<stored<=raw or (compressed and stored>=raw) or (not compressed and stored!=raw):raise ValueError('Invalid compressed block boundary')
  data=take(stored);out.extend(decode_lz4(data,raw) if compressed else data)
 return bytes(out)

def validate_input(body,capabilities):
 if len(body)!=300:raise ValueError('Invalid full controller record')
 cue,flags=struct.unpack_from('>2I',body);valid=struct.unpack_from('>I',body,20)[0]
 if flags&0x80000000:
  if not capabilities&(1<<18) or cue or flags&~0x80000003 or valid&~1:raise ValueError('Invalid frame input')
 elif not cue&1 or flags or valid&~3:raise ValueError('Invalid movement input')
 if body[19] or struct.unpack_from('>H',body,8)[0]&~0x1f7f:raise ValueError('Invalid raw controller')
 if not valid&1 and any(body[24:264]):raise ValueError('Absent processed controller contains data')
 if not valid&2 and any(body[264:]):raise ValueError('Absent controller work contains data')
 offsets=[]
 if valid&1:offsets=[24+o for o in (0x28,0x2c,0x48,0x4c,0x50,0x58,0x5c,0x60,*range(0xa8,0xd0,4))]
 if any(not math.isfinite(struct.unpack_from('>f',body,o)[0]) for o in offsets):raise ValueError('Nonfinite controller scalar')
 return bool(flags&0x80000000)


def apply_mirrors(body,version,previous,kind):
 if len(body)<8 or struct.unpack_from('>2I',body)!=(1,80):raise ValueError('Invalid shared-pad schema')
 if kind==24:
  if len(body)!=88:raise ValueError('Invalid shared-pad literal size')
  value=bytearray(body[8:])
 else:
  if version<2 or previous is None or len(body)<12:raise ValueError('Shared-pad delta lacks baseline')
  value=bytearray(previous);mask=struct.unpack_from('>I',body,8)[0];at=12
  if mask>>20:raise ValueError('Shared-pad mask exceeds extent')
  for i in range(20):
   if mask&(1<<i):
    if at+4>len(body):raise ValueError('Truncated shared-pad delta')
    value[i*4:i*4+4]=body[at:at+4];at+=4
  if at!=len(body):raise ValueError('Extra shared-pad delta words')
 if any(not math.isfinite(struct.unpack_from('>f',value,o)[0]) for o in (16,20,48,52,56,64,68,72)):raise ValueError('Nonfinite shared-pad scalar')
 return value

def validate_visual(body):
 if len(body)!=64 or struct.unpack_from('>I',body)[0]!=1:raise ValueError('Bad visual schema')
 flags,qf,scene=struct.unpack_from('>IiI',body,4)
 if flags&~3 or scene>0xffff or body[41]>1 or any(body[42:44]):raise ValueError('Bad visual flags')
 if not flags&1 and any(body[16:52]):raise ValueError('Missing pose contains data')
 if not flags&2 and qf:raise ValueError('Missing QFT contains data')
 if not all(math.isfinite(v) for v in struct.unpack_from('>3f',body,16)):raise ValueError('Nonfinite visual position')
 animation,phase=struct.unpack_from('>HH',body,30)
 if animation>=336 or phase>4095 or body[40]>5:raise ValueError('Invalid visual animation')
 f=body[44:52];mode=f[0]
 if mode&0x80:
  if mode&~0xb0 or mode&0x20 and not mode&0x10 or f[1]>=26 or f[4] and f[1]!=15 or f[5] not in (0,3,4) or not f[5] and f[6] or not body[40]:raise ValueError('Invalid Yoshi visual')
 else:
  if mode&0x20 and (not mode&0x10 or mode&7):raise ValueError('Invalid FLUDD burst')
  mode&=~0x20;pitch=((f[5]&15)<<8)|f[6]
  if not mode:
   if any(f[1:]):raise ValueError('Absent FLUDD contains data')
  elif mode&~0x1f or not mode&8 or mode&7>5 or not mode&0x10 and f[7] or 1024<pitch<3072:raise ValueError('Invalid FLUDD visual')
 return flags


def validate_observation(body):
 if len(body)<8:raise ValueError('Invalid observation header')
 schema,kind=struct.unpack_from('>2I',body)
 if schema!=1 or not kind:raise ValueError('Unknown observation schema')
 if kind not in (1,2,3,4,5):return kind
 if len(body)%4:raise ValueError('Invalid observation alignment')
 w=struct.unpack('>'+str(len(body)//4)+'I',body)
 if w[0]!=1 or not w[1]:raise ValueError('Unknown observation schema')
 kind=w[1]
 if kind==1:
  valid=len(w)==11 and w[2]<=4 and w[3]<=65536 and not w[4]&~255 and not w[6]&~15 and w[7]<=255 and not w[8]&~127 and w[10]<=65535
 elif kind==2:valid=len(w)==4 and not w[2]&~2047 and (w[3]<=255 or w[3]==0xffffffff)
 elif kind==3:valid=len(w)==26 and w[2]<5 and w[4]<=32767 and not w[5]&~3
 elif kind==4:valid=len(w)==7 and w[2]!=0 and 1<=w[3]<=9 and w[4]<=1 and w[6]==1 and (w[5] in (2,3) if w[4] else w[5]==4)
 elif kind==5:valid=len(w)==7 and w[2]<=1 and w[3]<=65535 and (not w[2] or (w[4]&0x7f800000!=0x7f800000 and w[5]&0x7f800000!=0x7f800000 and w[6]<=32767))
 else:valid=True
 if not valid:raise ValueError('Invalid observation payload')
 return kind


def header_parent(words):
 tag,nonce,run,chunk=words[11:15]
 if not tag:
  if nonce or run or chunk:raise ValueError('Invalid MSTR parent header')
 elif (tag!=BRANCH_HEADER_TAG or not nonce or not run or not chunk or
       not words[7]&CONTINUATION_CAPABILITY or (nonce,run)==(words[4],words[5]) or
       words[9]!=BRANCH_HEADER_FLAGS or words[10]!=PROVENANCE_TAG):
  raise ValueError('Invalid MSTR parent header')
 return nonce,run,chunk


def inspect(path):
 path=Path(path);counts=collections.Counter();sizes=collections.Counter();frames=ticks=chunks=payload=0;rng_calls=0;native_states={};scene=None;input_state=None;mirror_state=None
 frame_inputs=movement_inputs=pre_stage=late_stage=visual_poses=0
 shared_known=shared_missing=0
 world_complete=world_unavailable=0
 run_flags=0;provenance_count=0;stage_provenance=False;required_frame=None;last_provenance=None
 file_bytes=path.stat().st_size
 if not 96<=file_bytes<=0x7f000000:raise ValueError('Invalid capture file size')
 footer_at=file_bytes-32
 with path.open('rb') as f:
  header=exact(f,64);words=struct.unpack('>16I',header)
  if words[0]!=MAGIC or words[1] not in (1,2,3) or words[2]!=64 or words[3] not in (0x474d534a,0x474d5345,0x474d5350) or not words[5] or words[7]&0xff000000 or words[8]!=0x80000 or checksum(header[:60])!=words[15]:raise ValueError('Invalid MSTR header')
  game,nonce,run,start_scene,capabilities=words[3:8];version=words[1]
  header_parent_nonce,header_parent_run,header_parent_chunk=header_parent(words);requires_parent=bool(header_parent_nonce)
  f.seek(footer_at);footer=exact(f,32);done=struct.unpack('>8I',footer)
  if done[0]!=0x444f4e45 or done[1]!=run or done[3]!=footer_at or done[4]&0xffffff!=capabilities or done[2]>(file_bytes-96)//32:raise ValueError('Invalid completion footer')
  f.seek(64)
  while True:
   offset=f.tell()
   if offset>footer_at or offset!=footer_at and offset+32>footer_at:raise ValueError('Chunk header overlaps completion footer')
   block=exact(f,32);values=struct.unpack('>8I',block)
   if values[0]==0x444f4e45:
    if required_frame is not None and last_provenance!=required_frame:raise ValueError('Missing frame provenance')
    if words[10]==0x50525631 and provenance_count and bool(words[9]&32)!=bool(run_flags&32):raise ValueError('TAS summary disagrees with recording')
    if block!=footer or offset!=footer_at or values[1:4]!=(run,chunks,offset) or f.read(1):raise ValueError('Invalid final capture boundary')
    error=values[4]>>24
    return dict(path=str(path.resolve()),bytes=file_bytes,game_id=game,boot_nonce=nonce,run=run,start_scene=start_scene,version=version,capabilities=capabilities,
                complete=error==0,producer_error=error,requires_parent=requires_parent,parent_nonce=header_parent_nonce,parent_run=header_parent_run,parent_chunk=header_parent_chunk,standalone_replay=error==0 and not requires_parent,compression_max_ms=values[5]*1000/1898437 if version>=3 else None,compression_total_ms=values[6]*1000/1898437 if version>=3 else None,compression_blocks=values[7] if version>=3 else None,run_flags=run_flags|words[9],tas=bool((run_flags|words[9])&32),provenance_records=provenance_count,rng_calls=rng_calls,frames=frames,movement_updates=ticks,chunks=chunks,payload_bytes=payload,records=dict(counts),record_bytes=dict(sizes),frame_inputs=frame_inputs,movement_inputs=movement_inputs,visual_pose_frames=visual_poses,pre_stage_samples=pre_stage,late_stage_samples=late_stage,input_shared_known=shared_known,input_shared_missing=shared_missing,world_witness_complete=world_complete,world_witness_unavailable=world_unavailable,full_world_replay_proven=False)
   chunk_run,seq,n,digest,first,last,r0,r1=values
   if chunks>=done[2] or chunk_run!=run or seq!=chunks+1 or not 0<n<=0x80000 or first<frames or first>last:raise ValueError('Invalid chunk boundary')
   data=chunk_payload(f,values,version,footer_at)
   if checksum(data)!=digest:raise ValueError(f'Chunk {seq} checksum mismatch')
   pos=0;record_first=record_last=None
   while pos<len(data):
    if len(data)-pos<12:raise ValueError('Truncated record header')
    kind,size,frame,tick=struct.unpack_from('>HHII',data,pos);pos+=12
    if not kind or size>len(data)-pos or frame<frames or tick<ticks:raise ValueError('Invalid record boundary/order')
    body=data[pos:pos+size]
    capability={1:0,2:1,14:10,20:10,15:11,18:11,22:16,23:17,24:19,25:19,26:20,27:21}.get(kind)
    if capability is not None and not capabilities&(1<<capability):raise ValueError('Record capability absent')
    if kind==1:
     maximum=(1,2,1,1,1,2,1,1,1,1,1,1,1,1,2,1,3,1,1,1,1,1,1,1,1,1,1,1,2,1,1,1,1,1,5,1,4,4,99,99,1,4,4,4,1,1,1)
     if size!=64 or any(v>maximum[i] and not (i==46 and v==255) for i,v in enumerate(body[:47])) or body[40] and not body[0] or body[47] or any(body[56:]):raise ValueError('Invalid simulation settings')
     cadence,stick=struct.unpack_from('>2I',body,48)
     if not 0x3f800000<=cadence<=0x43700000 or stick>1:raise ValueError('Invalid simulation settings scalars')
    if kind==22:
     phase=bool(capabilities&(1<<23))
     if size not in ((964,968) if phase else (960,)):raise ValueError('Bad stage-start size')
     start=struct.unpack_from('>16I',body)
     if start[0]!=(3 if size==968 else 2 if phase else 1) or start[1]&~7 or start[2]>0xffff or not start[7] or start[8]!=896 or start[12]!=game:raise ValueError('Bad stage-start schema')
     if start[11]>0x1800000 or start[9]>start[11] or start[10]>start[11]-start[9] or not start[1]&2 and any(start[9:12]):raise ValueError('Bad initial heap extent')
     if not start[1]&1 and any(body[64:960]):raise ValueError('Absent initial flags contain data')
     if phase and struct.unpack_from('>I',body,960)[0]>=30:raise ValueError('Invalid initial NPC phase')
     if size==968 and struct.unpack_from('>I',body,964)[0]&~15:raise ValueError('Unsupported consumer observations')
     stage_provenance=size==968 and bool(struct.unpack_from('>I',body,964)[0]&2)
     if start[1]&4:pre_stage+=1
     else:late_stage+=1
    if kind==27:
     if size!=48:raise ValueError('Bad continuation size')
     schema,flags,actions,parent_nonce,parent_run,parent_chunk,parent_hash,seed,qf,attempt,generation,context=struct.unpack('>12I',body)
     if schema!=1 or flags!=0x23 or actions&~7 or actions&6==6 or not parent_nonce or not parent_run or not parent_chunk or context&~1 or (qf>0x7fffffff if context&1 else qf!=0):raise ValueError('Bad continuation context')
     native_states.clear();input_state=None;mirror_state=None;run_flags|=flags
    if kind==29:validate_observation(body)
    if kind==28:
     if size!=8 or struct.unpack_from('>I',body)[0]!=1:raise ValueError('Bad run provenance schema')
     flags=struct.unpack_from('>I',body,4)[0]
     if flags&~0x27 or flags&32 and not flags&1 or flags&6 and flags&0x21!=0x21 or run_flags&~flags:raise ValueError('Invalid or decreasing run provenance')
     run_flags=flags;provenance_count+=1;last_provenance=frame
    if kind==23:visual_poses+=bool(validate_visual(body)&1)
    if kind==26:
     if size!=20:raise ValueError('Bad world-witness size')
     schema,scope,status,count,digest=struct.unpack('>5I',body)
     if schema!=1 or scope!=511 or status>6 or count>1024 or status and (count or digest):raise ValueError('Bad world-witness schema')
     if status:world_unavailable+=1
     else:world_complete+=1
    if kind==2:
     if required_frame is not None and last_provenance!=required_frame:raise ValueError('Missing frame provenance')
     required_frame=frame if stage_provenance else None
     if size!=32:raise ValueError('Bad frame record')
     fscene,_,_,_,_,mtick,dstate,fflags=struct.unpack('>8I',body)
     if fscene>0xffff or mtick!=tick or fflags&~15 or dstate>255 and dstate!=0xffffffff:raise ValueError('Bad frame fields')
     if fscene!=scene:native_states.clear();scene=fscene;input_state=None;mirror_state=None
    if kind in (3,4,5,8,9):apply_blob(body,version,native_states,kind)
    if kind in (24,25):mirror_state=apply_mirrors(body,version,mirror_state,kind)
    if kind==14:
     if size!=300:raise ValueError('Invalid full controller record')
     input_state=bytearray(body)
    if kind==20:
     if version<2 or input_state is None or size<16 or struct.unpack_from('>I',body)[0]!=300:raise ValueError('Invalid controller delta')
     masks=struct.unpack_from('>3I',body,4);cursor=16
     if masks[2]>>11:raise ValueError('Controller mask exceeds extent')
     for word in range(75):
      if masks[word//32]&(1<<(word%32)):
       if cursor+4>size:raise ValueError('Truncated controller word')
       input_state[word*4:word*4+4]=body[cursor:cursor+4];cursor+=4
     if cursor!=size:raise ValueError('Extra controller words')
    if kind in (14,20):
     if mirror_state is None:shared_missing+=1
     else:shared_known+=1
     if validate_input(input_state,capabilities):frame_inputs+=1
     else:movement_inputs+=1
    if kind==19:
     if size!=88 or struct.unpack_from('>I',body)[0]>3:raise ValueError('Invalid contact record')
    if kind==21 and size!=88:raise ValueError('Invalid camera metadata')
    if kind==17:
     if size!=16:raise ValueError('Invalid identity')
     igame,_,_,region=struct.unpack('>4I',body)
     if igame!=game or region!={0x474d534a:1,0x474d5345:2,0x474d5350:3}[game]:raise ValueError('Identity region mismatch')
    if kind==15:
     if size!=12:raise ValueError('Invalid RNG call')
     caller=struct.unpack_from('>I',body)[0]
     if caller&3 or not 0x80000000<=caller<0x81800000:raise ValueError('Invalid RNG caller')
     rng_calls+=1
    if kind==18:
     if version<2 or size<16:raise ValueError('Invalid RNG block')
     seed,rng_last,count,callers=struct.unpack_from('>4I',body)
     if not 0<count<=512 or not 0<callers<=64 or size!=16+callers*4+count or any(i>=callers for i in body[16+callers*4:]):raise ValueError('Invalid RNG callers')
     if any(p&3 or not 0x80000000<=p<0x81800000 for p in struct.unpack_from('>'+str(callers)+'I',body,16)):raise ValueError('Invalid RNG caller address')
     for _ in range(count-1):seed=(seed*1103515245+12345)&0xffffffff
     if seed!=rng_last:raise ValueError('RNG sequence mismatch')
     rng_calls+=count
    if kind==6:
     if size<28:raise ValueError('Short actor delta')
     ident,pointer,extent,created,m0,m1,m2=struct.unpack_from('>7I',body)
     mask=m0|(m1<<32)|(m2<<64)
     if extent not in (0xf4,0x150) or mask>>(extent//4) or created not in (0,1) or size!=28+4*mask.bit_count() or (created and mask!=(1<<(extent//4))-1):raise ValueError('Invalid actor delta')
    frames=frame;ticks=tick
    if record_first is None:record_first=frame
    record_last=frame;label=KINDS.get(kind,f'optional_{kind}')
    counts[label]+=1;sizes[label]+=size+12;pos+=size
   if (record_first,record_last)!=(first,last):raise ValueError('Chunk frame range mismatch')
   chunks+=1;payload+=n

def unpack_to_v2(source,destination):
 inspect(source)
 destination=Path(destination)
 with Path(source).open('rb') as src, destination.open('xb') as dst:
  header=bytearray(exact(src,64));version=struct.unpack_from('>I',header,4)[0]
  if version<2:raise ValueError('Unpacking requires v2 or v3 input')
  struct.pack_into('>I',header,4,2);struct.pack_into('>I',header,60,checksum(header[:60]));dst.write(header)
  while True:
   values=list(struct.unpack('>8I',exact(src,32)))
   if values[0]==0x444f4e45:
    values[3]=dst.tell();values[5:]=[0,0,0];dst.write(struct.pack('>8I',*values));break
   data=chunk_payload(src,values,version,Path(source).stat().st_size-32)
   if checksum(data)!=values[3]:raise ValueError('Chunk checksum mismatch during unpack')
   values[6:]=[0,0];dst.write(struct.pack('>8I',*values));dst.write(data)
 return inspect(destination)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('capture',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--unpack',type=Path,help='Write an equivalent uncompressed v2 file; never overwrites');args=parser.parse_args()
 result=inspect(args.capture)
 if args.unpack:result['unpacked']=unpack_to_v2(args.capture,args.unpack)
 text=json.dumps(result,indent=2)+'\n'
 if args.output:args.output.write_text(text,encoding='utf-8')
 print(text,end='')
