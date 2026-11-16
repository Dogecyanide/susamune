"""Small checked containers and exact fork edges for admission tests."""
import struct

def fnv(data):
 h=2166136261
 for b in data:h=((h^b)*16777619)&0xffffffff
 return h

def tag_header(data,parent_nonce,parent_run,parent_chunk=1,tag=0x42524348,flags=0x23,provenance=0x50525631):
 out=bytearray(data);struct.pack_into('>6I',out,36,flags,provenance,tag,parent_nonce,parent_run,parent_chunk)
 struct.pack_into('>I',out,60,fnv(out[:60]));return bytes(out)

def capture(nonce,run,payload,caps=0x3fffff,game=0x474d534a,frame=1,tick=1):
 h=struct.pack('>15I',0x4d535452,3,64,game,nonce,run,0x603,caps,0x80000,0,0,0,0,0,0)
 out=h+struct.pack('>I',fnv(h))+struct.pack('>8I',run,1,len(payload),fnv(payload),frame,frame,0,0)+payload
 return out+struct.pack('>8I',0x444f4e45,run,1,len(out),caps,0,0,0)

def branch_graph(nonce=0x87654321,child_run=7,parent_nonce=None,parent_run=6):
 if parent_nonce is None:parent_nonce=nonce
 caps=0x3fffff;game=0x474d534a
 raw=struct.pack('>HHII8I',2,32,1,1,0x603,5,100,1000,1,1,4,6)
 parent=capture(parent_nonce,parent_run,raw,caps,game)
 continuation=struct.pack('>HHII12I',27,48,1,1,1,0x23,1,parent_nonce,parent_run,1,fnv(raw),777,120,44,0,1)
 child=tag_header(capture(nonce,child_run,continuation,caps,game),parent_nonce,parent_run)
 start=64;end=64+32+len(raw)
 b=[nonce,child_run,game,caps,parent_nonce,parent_run,1,1,1,1,len(raw),fnv(raw),5,end,start,len(raw),fnv(raw),struct.unpack_from('>I',parent,60)[0],0,0,0x464f524b,1,1,0]
 edge=bytearray(128);struct.pack_into('>4I',edge,0,0x4d534742,1,128,1);struct.pack_into('>24I',edge,16,*b);struct.pack_into('>I',edge,124,fnv(edge[:124]))
 return child,parent,bytes(edge)

def map_path(nonce,run,temporary=False):
 return f'/Moonshine data/ghosts/recordings/ref_{nonce:08X}_{run:08X}_464F524B_00000001_00000001.'+('mbpt' if temporary else 'msgb')
