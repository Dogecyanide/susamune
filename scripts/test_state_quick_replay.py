"""Focused replacement transactions with real Store decode and bounded replay callbacks."""
import ctypes as C
from pathlib import Path
import random
import struct
import tempfile
import unittest
import zlib

from test_state_codec import Guarded, Span, Result
from test_state_store import StoreCodec, StorePool, Identity, identity
from test_timewarp_staged_transaction import StageHarness
from test_timewarp_chunk_pool import plain

ROOT = Path(__file__).resolve().parents[1]
BLOCK = 0x20000
ALLOC = (BLOCK + 8 + 31) & ~31
FRAME = b'MSL4\0\2\0\0'

EXTRA = '#define TIMEWARP_QUICK_REPLAY 1\n#include "' + (ROOT/'src/state_quick_replay.cpp').as_posix() + '"\n' + r'''
static_assert(__builtin_offsetof(StateQuickReplay::Plan, comparison) % __alignof__(StateQuickReplay::VerifyCache) == 0,
 "verification cache alignment");
struct ReplayContext {
 const StateCodec::ReadSpan *blocks;const unsigned *adlers;void *work;
 StateCodec::PreparedQuickSource prepared;unsigned calls,actual,permitted,deferred,checksums;
} replayContext;
static StateQuickReplay::Plan *replayPlan;
static unsigned char *encodeFault;
static void replayEncode(void*p,unsigned n,StateCodec::PreparedQuickBlock&b){
 ReplayContext&c=*(ReplayContext*)p;++c.calls;
 if(encodeFault){*encodeFault^=1;encodeFault=nullptr;}
 if(c.actual){
  if(c.deferred)StateCodec::encodePreparedQuickBlockDeferred(c.work,c.prepared,n,b);
  else StateCodec::encodePreparedQuickBlock(c.work,c.prepared,n,b);return;}
 const unsigned char*bytes=(const unsigned char*)c.blocks[n].data;
 memcpy(b.header,bytes,8);b.payload=bytes+8;b.payloadBytes=c.blocks[n].size-8;
 b.rawBytes=TWChunkWord(bytes);b.adler32=c.deferred?0:c.adlers[n];
}
static unsigned replayChecksum(void*p,unsigned n,const StateCodec::PreparedQuickBlock&b){
 ReplayContext&c=*(ReplayContext*)p;++c.checksums;
 return c.actual?StateCodec::checksumPreparedQuickBlock(c.work,c.prepared,n,b):c.adlers[n];
}
static bool replayAdmitted(void*p){return ((ReplayContext*)p)->permitted!=0;}
#define API extern "C" __declspec(dllexport)
API unsigned replaySize(){return StateQuickReplay::workspaceSize();}
API unsigned replayPrepare(StateStore::Store*s,unsigned slot,const StateCodec::ReadSpan*b,
 const unsigned*a,unsigned count,void*tail,unsigned bytes,void*work,unsigned actual,unsigned permitted,unsigned deferred){
 replayContext={};replayContext.blocks=b;replayContext.adlers=a;replayContext.actual=actual;
 replayContext.work=work;replayContext.permitted=permitted;replayContext.deferred=deferred;unsigned raw=0;
 if(actual){StateCodec::WriteSpan destinations[TW_BANK_MAX+2];unsigned n=0;
  for(unsigned i=0;i<s->memory->pool->count;++i)destinations[n++]={s->memory->pool->banks[i],s->memory->pool->sizes[i]};
  if(s->memory->size)destinations[n++]={s->memory->staging,s->memory->size};destinations[n++]={tail,bytes};
  if(StateCodec::prepareQuickSource(work,0x4e000,b,count,destinations,n,replayContext.prepared)!=StateCodec::SUCCESS)return 1;
  raw=replayContext.prepared.rawBytes;
 }else for(unsigned i=0;i<count;++i)raw+=TWChunkWord((const unsigned char*)b[i].data);
 StateQuickReplay::Source source={&replayContext,raw,replayEncode,replayAdmitted,deferred?replayChecksum:nullptr};
 return StateQuickReplay::prepare(*s,slot,s->roots[slot],source,tail,bytes,replayPlan);
}
API void replayInfo(StateStore::Identity*i,unsigned generation){
 const StateCodec::Result r=StateQuickReplay::result(*replayPlan);
 *i={generation,0xACE1,r.rawBytes,r.compressedBytes,r.adler32,StateQuickReplay::checksum(*replayPlan),StateStore::QUICK};
}
API unsigned replayStat(unsigned n){const StateQuickReplay::Stats s=StateQuickReplay::stats(*replayPlan);
 return n==0?s.cachedBytes:n==1?s.spilledBlocks:n==2?s.replayRawBytes:n==3?s.movedBytes:n==4?replayContext.calls:replayContext.checksums;}
API unsigned replayCacheOffset(){return StateQuickReplay::kAdlerCacheOffset;}
API unsigned replayCacheSize(){return sizeof(StateQuickReplay::AdlerCache);}
API unsigned replayCacheCapacity(){return StateQuickReplay::kAdlerCacheEntries;}
API unsigned replayRepack(StateStore::Store*s,unsigned slot,StateStore::Identity*i,void*w,void*p){
 StateStore::Identity next=s->roots[slot];
 if(!StateStore::begin(*s,slot,next))return 0;
 const StateCodec::Result r=StateStore::repack(*s,slot,next,w,0x4e000,p,0x4e000,false);
 next.generation+=1;next.tag+=1;next.packed=r.compressedBytes;next.kind=StateStore::DEFLATE;
 next.checksum=StateStore::pendingChecksum(*s);
 if(r.status!=StateCodec::SUCCESS||!StateStore::seal(*s,next,w,0x4e000)||!StateStore::commit(*s,next)){
  StateStore::abort(*s);return 0;}
 *i=next;return 1;
}
API unsigned replayCommit(StateStore::Identity*i){return StateQuickReplay::commit(*replayPlan,*i);}
API unsigned replayAbort(){return StateQuickReplay::abort(*replayPlan);}
API void replayPermit(unsigned p){replayContext.permitted=p;}
API void replayEncodeFault(void*p){encodeFault=(unsigned char*)p;}
API void replayFault(unsigned n){
 StateQuickReplay::Plan&p=*replayPlan;
 if(n==0)p.fingerprint^=1;
 if(n==1)p.store->roots[(p.token.slot+1)%3].generation^=8;
 if(n==2){const TWChunkPool*q=TWChunkDirectory(p.store->memory->pool);
  unsigned id=q->slots[(p.token.slot+1)%3].ids[0]-1;TWSAddressUnchecked(p.store->memory,q->chunks[id].offset)[16]^=1;}
 if(n==3){unsigned id=p.recipes[0].id;TWSAddressUnchecked(p.store->memory,p.chunks[id].offset)[16]^=1;}
}
API void replayNormal(void*w,const StateCodec::ReadSpan*s,unsigned n,void*out,unsigned bytes,StateCodec::Result*r){
 StateCodec::WriteSpan destination={out,bytes};*r=StateCodec::compress(w,0x4e000,s,n,&destination,1,false,true);}
'''


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='quick-replay-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name); (folder/'allocator').mkdir()
        cls.harness = StageHarness(folder/'allocator'); cls.addClassCleanup(cls.harness.close)
        cls.codec = StoreCodec(folder, EXTRA); cls.addClassCleanup(cls.codec.close)
        # The shim advertises the launcher's whole reservation to the codec.
        cls.codec.work = Guarded(0x4e000)
        p, u = C.c_void_p, C.c_uint
        cls.codec.lib.replaySize.restype = u
        for name,args in {
            'replayPrepare':[p,u,C.POINTER(Span),C.POINTER(u),u,p,u,p,u,u,u],
            'replayInfo':[C.POINTER(Identity),u], 'replayStat':[u],
            'replayCommit':[C.POINTER(Identity)],'replayAbort':[],
            'replayPermit':[u],'replayFault':[u],'replayEncodeFault':[p],
            'replayNormal':[p,C.POINTER(Span),u,p,u,C.POINTER(Result)]
            ,'replayRepack':[p,u,C.POINTER(Identity),p,p]
        }.items(): getattr(cls.codec.lib,name).argtypes=args

    def seeded(self, roots=None, sizes=None, staging=0):
        if roots is None:
            roots = [[random.Random(700+i).randbytes(BLOCK)] for i in range(3)]
        unique = len(set(x for root in roots for x in root))
        store = StorePool(self.harness,self.codec,sizes or [0x8000+unique*ALLOC],staging)
        for slot,blocks in enumerate(roots):
            raw=b''.join(blocks); packed=FRAME+b''.join(map(plain,blocks))
            self.assertTrue(store.put(slot,raw,packed,100+slot,0))
        return store

    def prepare(self,store,slot,blocks,actual=False,permitted=True,scratch=None,deferred=False):
        self.tail=Guarded(self.codec.lib.replaySize())
        self.owners=[C.create_string_buffer(b if actual else plain(b)) for b in blocks]
        self.spans=(Span*len(blocks))(*(Span(C.addressof(o),len(b) if actual else len(b)+8)
                                     for o,b in zip(self.owners,blocks)))
        self.adlers=(C.c_uint*len(blocks))(*(zlib.adler32(b) for b in blocks))
        self.raw=b''.join(blocks)
        if actual:
            out=Guarded(len(self.raw)+len(blocks)*16+4096); r=Result()
            self.codec.lib.replayNormal(self.codec.work.ptr,self.spans,len(blocks),out.ptr,out.size,C.byref(r))
            self.assertEqual(r.status,0);self.packed=out.data()[:r.compressed]
        else:self.packed=FRAME+b''.join(map(plain,blocks))
        status=self.codec.lib.replayPrepare(store.storage.ptr,slot,self.spans,self.adlers,len(blocks),
            self.tail.ptr,self.tail.size if scratch is None else scratch,self.codec.work.ptr,actual,permitted,deferred)
        if status==0:
            self.info=Identity();self.codec.lib.replayInfo(C.byref(self.info),500+slot)
            self.assertEqual((self.info.raw,self.info.packed,self.info.adler,self.info.checksum),
                (len(self.raw),len(self.packed),zlib.adler32(self.raw),zlib.crc32(self.packed)))
        self.assertTrue(self.tail.guards())
        return status

    def publish(self,store,slot):
        self.assertTrue(self.codec.lib.replayCommit(C.byref(self.info)))
        store.identities[slot]=self.info;store.roots[slot]=(self.raw,self.packed)
        for i in range(3):store.decode(i,True)
        self.assertTrue(self.tail.guards())

    def test_full_pool_each_slot_replays_with_no_candidate_buffer(self):
        for slot in range(3):
            with self.subTest(slot=slot):
                store=self.seeded();old=store.pool.states()
                raw=random.Random(1700+slot).randbytes(BLOCK)
                self.assertEqual(self.prepare(store,slot,[raw],actual=True),0)
                self.assertEqual(store.pool.states(),old)
                self.assertEqual(self.codec.lib.replayStat(1),1)
                before=self.codec.lib.replayStat(4)
                self.publish(store,slot)
                self.assertEqual(self.codec.lib.replayStat(4),before+1)
                self.assertEqual(store.pool.stage('stGeneration',slot),3)

    def test_shared_references_cached_prefix_bank_seams_and_spill(self):
        a,b,c,d,e,f,g=[random.Random(2100+i).randbytes(BLOCK) for i in range(7)]
        roots=[[a,b,c],[a,d],[e]]
        store=self.seeded(roots,[0x8000+2*ALLOC+64,2*ALLOC+32,2*ALLOC])
        old=store.pool.states()
        self.assertEqual(self.prepare(store,0,[b,f,g]),0)
        self.assertEqual(store.pool.states(),old)
        self.assertEqual(self.codec.lib.replayStat(0),BLOCK+8)
        self.assertEqual(self.codec.lib.replayStat(1),1)
        self.publish(store,0)

    def test_spilled_hash_collision_and_exact_duplicate(self):
        prefix=random.Random(3100).randbytes(BLOCK-8)
        h=zlib.crc32(struct.pack('>II',BLOCK,BLOCK|0x80000000)+prefix)
        seen={};rng=random.Random(3101)
        for _ in range(300000):
            suffix=rng.randbytes(8);value=zlib.crc32(suffix,h)
            if value in seen and suffix!=seen[value]:
                a,b=prefix+seen[value],prefix+suffix;break
            seen[value]=suffix
        else:self.fail('deterministic collision search exhausted')
        roots=[[random.Random(3200+i).randbytes(BLOCK) for i in range(2)],
               [random.Random(3202).randbytes(BLOCK)],[random.Random(3203).randbytes(BLOCK)]]
        store=self.seeded(roots)
        self.assertEqual(self.prepare(store,0,[a,b,a],deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),2)
        self.assertEqual(self.codec.lib.replayStat(1),2)
        self.publish(store,0)
        ids=store.pool.directory.slots[0].ids
        self.assertEqual(ids[0],ids[2]);self.assertNotEqual(ids[0],ids[1])
        self.assertEqual(self.prepare(store,0,[b,a,b],deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),0)
        self.publish(store,0)

    def test_deferred_adler_cache_reuse_abort_and_corruption(self):
        raw=random.Random(3900).randbytes(BLOCK)
        store=self.seeded([[raw],[bytes([1])*BLOCK],[bytes([2])*BLOCK]],staging=ALLOC)
        self.assertEqual(self.codec.lib.replayCacheOffset()+self.codec.lib.replayCacheSize(),0x8000)
        self.assertEqual(self.codec.lib.replayCacheCapacity(),204)
        self.assertEqual(self.prepare(store,0,[raw],actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),1)
        self.publish(store,0)
        cache=store.pool.memory.banks[0]+self.codec.lib.replayCacheOffset()
        original=C.string_at(cache,self.codec.lib.replayCacheSize())
        self.assertEqual(self.prepare(store,0,[raw],actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),0)
        self.assertTrue(self.codec.lib.replayAbort())
        self.assertEqual(C.string_at(cache,len(original)),original)
        self.assertEqual(self.prepare(store,0,[raw],actual=True,deferred=True),0)
        byte=C.c_ubyte.from_address(cache+36);byte.value^=1
        self.assertFalse(self.codec.lib.replayCommit(C.byref(self.info)))
        byte.value^=1;self.assertTrue(self.codec.lib.replayAbort())
        for offset in (0,4,8,20,24,28,36,len(original)-1):
            byte=C.c_ubyte.from_address(cache+offset);byte.value^=1
            self.assertEqual(self.prepare(store,0,[raw],actual=True,deferred=True),0)
            self.assertEqual(self.codec.lib.replayStat(5),1)
            self.assertTrue(self.codec.lib.replayAbort());byte.value^=1
        self.assertEqual(self.prepare(store,0,[raw],actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),0);self.publish(store,0)

    def test_deferred_cache_invalidates_after_external_commit_repack_and_clear(self):
        a,b,c=[bytes([n])*BLOCK for n in (21,22,23)]
        for operation in ('external_quick','repack','clear'):
            with self.subTest(operation=operation):
                store=self.seeded([[a],[b],[c]],staging=ALLOC)
                self.assertEqual(self.prepare(store,0,[a],deferred=True),0);self.publish(store,0)
                self.assertEqual(self.prepare(store,0,[a],deferred=True),0)
                self.assertEqual(self.codec.lib.replayStat(5),0);self.assertTrue(self.codec.lib.replayAbort())
                if operation=='external_quick':
                    replacement=bytes([99])*BLOCK
                    self.assertTrue(store.put(2,replacement,FRAME+plain(replacement),901,0))
                elif operation=='repack':
                    work=Guarded(0x4e000);info=Identity()
                    self.assertTrue(self.codec.lib.replayRepack(store.storage.ptr,2,C.byref(info),self.codec.work.ptr,work.ptr))
                    store.identities[2]=info;store.roots[2]=(c,zlib.compress(c))
                    self.assertTrue(work.guards())
                else:
                    self.assertTrue(store.call('sd',2,C.byref(store.identities[2]),903))
                self.assertEqual(self.prepare(store,0,[a],deferred=True),0)
                self.assertEqual(self.codec.lib.replayStat(5),1)
                self.assertTrue(self.codec.lib.replayAbort());store.guards()

    def test_deferred_actual_encoder_handles_split_spans_and_duplicate_blocks(self):
        a=random.Random(3950).randbytes(BLOCK);raw=a+a+b'B'*BLOCK
        parts=[raw[:17003],raw[17003:BLOCK+27],raw[BLOCK+27:]]
        store=self.seeded(sizes=[0x8000+7*ALLOC],staging=ALLOC)
        self.assertEqual(self.prepare(store,0,parts,actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),2);self.publish(store,0)
        self.assertEqual(self.prepare(store,0,parts,actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),0);self.publish(store,0)

    def test_deferred_cache_capacity_falls_back_without_losing_any_checksum(self):
        blocks=[bytes([i])*BLOCK for i in range(1,206)]
        store=self.seeded(staging=2*ALLOC)
        self.assertLessEqual(self.codec.lib.replaySize(),0x4e000)
        self.assertEqual(self.prepare(store,0,blocks,actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),205);self.publish(store,0)
        cache=store.pool.memory.banks[0]+self.codec.lib.replayCacheOffset()
        self.assertEqual(C.c_uint.from_address(cache+24).value,204)
        self.assertEqual(self.prepare(store,0,blocks,actual=True,deferred=True),0)
        self.assertEqual(self.codec.lib.replayStat(5),1);self.publish(store,0)

    def test_capacity_busy_cancel_and_corruption_preserve_old_roots(self):
        store=self.seeded();old=store.pool.states()
        new=[random.Random(4100+i).randbytes(BLOCK) for i in range(2)]
        self.assertEqual(self.prepare(store,0,new),2)
        self.assertEqual(store.pool.states(),old)
        self.assertEqual(self.prepare(store,0,new[:1],permitted=False),3)
        self.assertEqual(self.prepare(store,0,new[:1],scratch=32),1)
        self.assertEqual(self.prepare(store,0,new[:1]),0)
        self.codec.lib.replayPermit(0)
        self.assertFalse(self.codec.lib.replayCommit(C.byref(self.info)))
        self.assertEqual(store.pool.states(),old)
        self.assertTrue(self.codec.lib.replayAbort())
        for fault in range(3):
            with self.subTest(fault=fault):
                self.assertEqual(self.prepare(store,0,new[:1]),0)
                self.codec.lib.replayFault(fault)
                self.assertFalse(self.codec.lib.replayCommit(C.byref(self.info)))
                self.codec.lib.replayFault(fault)
                self.assertTrue(self.codec.lib.replayAbort())
                self.assertEqual(store.pool.states(),old)
        for i in range(3):store.decode(i)

    def test_cached_payload_corruption_and_one_pass_commit(self):
        store=self.seeded(staging=ALLOC);old=store.pool.states()
        raw=random.Random(5100).randbytes(BLOCK)
        self.assertEqual(self.prepare(store,1,[raw],actual=True),0)
        self.assertEqual(self.codec.lib.replayStat(1),0)
        self.codec.lib.replayFault(3)
        self.assertFalse(self.codec.lib.replayCommit(C.byref(self.info)))
        self.codec.lib.replayFault(3)
        self.assertTrue(self.codec.lib.replayAbort());self.assertEqual(store.pool.states(),old)
        self.assertEqual(self.prepare(store,1,[raw],actual=True),0)
        calls=self.codec.lib.replayStat(4);self.publish(store,1)
        self.assertEqual(self.codec.lib.replayStat(4),calls)

    def test_retained_opaque_root_keeps_crc_without_a_quick_hash(self):
        store=StorePool(self.harness,self.codec,[0x8100+3*ALLOC],ALLOC)
        for slot in range(3):
            raw=random.Random(6100+slot).randbytes(BLOCK)
            packed=zlib.compress(raw) if slot==1 else FRAME+plain(raw)
            self.assertTrue(store.put(slot,raw,packed,100+slot,slot==1))
        raw=random.Random(6200).randbytes(BLOCK)
        self.assertEqual(self.prepare(store,0,[raw],actual=True),0)
        self.publish(store,0)

    def test_deferred_payload_corruption_refuses_before_destructive_commit(self):
        for when in ('during_encode','before_commit','new_cache'):
            with self.subTest(when=when):
                store=self.seeded(staging=ALLOC);old=store.pool.states()
                chunk=store.pool.directory.chunks[store.pool.directory.slots[1].ids[0]-1]
                address=store.pool.memory.banks[0]+chunk.offset+16
                byte=C.c_ubyte.from_address(address)
                byte.value^=1
                self.assertFalse(store.begin(0))  # Generic transfers still check at begin.
                byte.value^=1
                if when=='during_encode':self.codec.lib.replayEncodeFault(address)
                raw=random.Random(7100).randbytes(BLOCK)
                self.assertEqual(self.prepare(store,0,[raw],actual=True),0)
                if when=='before_commit':byte.value^=1
                if when=='new_cache':self.codec.lib.replayFault(3)
                before=store.pool.states()
                generations=[store.pool.stage('stGeneration',i) for i in range(3)]
                self.assertFalse(self.codec.lib.replayCommit(C.byref(self.info)))
                self.assertEqual(store.pool.states(),before)
                self.assertEqual([store.pool.stage('stGeneration',i) for i in range(3)],generations)
                if when=='new_cache':self.codec.lib.replayFault(3)
                else:byte.value^=1
                self.assertTrue(self.codec.lib.replayAbort())
                self.assertEqual(store.pool.states(),old)
                for slot in range(3):store.decode(slot,True)
                self.assertTrue(self.tail.guards())
        store=self.seeded();old=store.pool.states()
        chunk=store.pool.directory.chunks[store.pool.directory.slots[1].ids[0]-1]
        address=store.pool.memory.banks[0]+chunk.offset+16
        self.codec.lib.replayEncodeFault(address)
        oversized=[random.Random(7200+i).randbytes(BLOCK) for i in range(2)]
        self.assertEqual(self.prepare(store,0,oversized),1)  # Corruption must not become FULL.
        C.c_ubyte.from_address(address).value^=1
        self.assertEqual(store.pool.states(),old)
        for slot in range(3):store.decode(slot,True)


if __name__=='__main__':unittest.main()
