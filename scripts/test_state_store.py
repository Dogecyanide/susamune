"""Shared Quick and verbatim Deflate roots through the production store adapter."""
import ctypes as C
from pathlib import Path
import random
import struct
import tempfile
import unittest
import zlib

from mod_transport import encode_quick
from test_state_codec import Guarded, Span, Result, DirectPolicy
from test_timewarp_staged_transaction import StageHarness, StagePool, StageMemory
from timewarp_root_codec import RootCodec
from timewarp_state_measure import quick_blocks

ROOT = Path(__file__).resolve().parents[1]


class Identity(C.Structure):
    _fields_ = [(n, C.c_uint) for n in ('generation', 'tag', 'raw', 'packed', 'adler', 'checksum', 'kind')]


EXTRA = '#include "' + (ROOT / 'src/state_store.cpp').as_posix() + '"\n' + r'''
extern "C" {
__declspec(dllexport) unsigned storeSize(){return sizeof(StateStore::Store);}
__declspec(dllexport) int si(StateStore::Store*s,TWStageMemory*m,void*b,unsigned n){return StateStore::init(*s,*m,73,b,n);}
__declspec(dllexport) int sv(StateStore::Store*s){return StateStore::valid(*s);}
__declspec(dllexport) int sb(StateStore::Store*s,unsigned slot,StateStore::Identity*i){return StateStore::begin(*s,slot,*i);}
__declspec(dllexport) int sa(StateStore::Store*s){return StateStore::abort(*s);}
__declspec(dllexport) int sq(StateStore::Store*s,const unsigned char*p,unsigned n){return StateStore::appendQuick(*s,p,8,p+8,n-8);}
__declspec(dllexport) int so(StateStore::Store*s,const void*p,unsigned n){return StateStore::appendOpaque(*s,p,n);}
__declspec(dllexport) unsigned sr(StateStore::Store*s,unsigned n,StateCodec::WriteSpan*p){return StateStore::reserveOpaque(*s,n,*(StateCodec::WriteSpan(*)[TW_BANK_MAX+1])p);}
__declspec(dllexport) int ss(StateStore::Store*s,StateStore::Identity*i,void*w,unsigned n){return StateStore::seal(*s,*i,w,n);}
__declspec(dllexport) int sc(StateStore::Store*s,StateStore::Identity*i){return StateStore::commit(*s,*i);}
__declspec(dllexport) int sd(StateStore::Store*s,unsigned slot,StateStore::Identity*i,unsigned g){return StateStore::clear(*s,slot,*i,g);}
__declspec(dllexport) unsigned sp(StateStore::Store*s,unsigned slot,StateStore::Identity*i){return StateStore::pin(*s,slot,*i);}
__declspec(dllexport) int sk(StateStore::Store*s,unsigned seq,StateStore::Identity*i){return StateStore::check(*s,seq,*i);}
__declspec(dllexport) int su(StateStore::Store*s,unsigned seq){return StateStore::unpin(*s,seq);}
__declspec(dllexport) const void* st(StateStore::Store*s,unsigned seq,unsigned*n){return StateStore::spans(*s,seq,*n);}
__declspec(dllexport) int sx(StateStore::Store*s,unsigned seq,StateStore::Identity*i,void*w,unsigned wn,StateCodec::WriteSpan*d,unsigned dn,void*p,int write){
 return write?StateStore::restore(*s,seq,*i,w,wn,d,dn,copy,p,direct):StateStore::validateRestore(*s,seq,*i,w,wn,d,dn);}
__declspec(dllexport) int sl(StateStore::Store*s,unsigned slot,StateStore::Identity*i,void*w,unsigned wn,StateCodec::WriteSpan*d,unsigned dn,void*p){
 return StateStore::restoreSlot(*s,slot,*i,w,wn,d,dn,copy,p,direct);}
__declspec(dllexport) int sle(StateStore::Store*s,unsigned slot,StateStore::Identity*i,void*w,unsigned wn,StateCodec::WriteSpan*d,unsigned dn,void*p){
 return StateStore::restoreSlotExperimental(*s,slot,*i,w,wn,d,dn,copy,p,direct);}
__declspec(dllexport) int se(StateStore::Store*s,unsigned seq,StateStore::Identity*i,unsigned crc,SusamuneStateExportPlan*p){return StateStore::exportPlan(*s,seq,*i,crc,*p);}
__declspec(dllexport) unsigned sch(StateStore::Store*s){return StateStore::pendingChecksum(*s);}
__declspec(dllexport) void sz(StateStore::Store*s,void*w,unsigned wn,const StateCodec::ReadSpan*r,unsigned rn,StateCodec::Result*out){*out=StateStore::produceQuick(*s,w,wn,r,rn);}
__declspec(dllexport) void zpack(void*w,unsigned wn,const StateCodec::ReadSpan*r,unsigned rn,StateCodec::WriteSpan*d,unsigned dn,StateCodec::Result*out){*out=StateCodec::compress(w,wn,r,rn,d,dn,false,false);}
__declspec(dllexport) void zrepack(void*w,unsigned wn,void*p,unsigned pn,const StateCodec::ReadSpan*r,unsigned rn,StateCodec::WriteSpan*d,unsigned dn,unsigned raw,unsigned adler,StateCodec::Result*out){*out=StateCodec::repack(w,wn,p,pn,r,rn,d,dn,raw,adler,false);}
}
'''
# The codec shim defines these policies after including the wrapper.
EXTRA = 'extern "C" { void copy(void*,void*,const void*,unsigned); bool direct(void*,void*,unsigned); }\n' + EXTRA


class StoreCodec(RootCodec):
    def __init__(self, folder, extra_source=''):
        super().__init__(folder, EXTRA + extra_source)
        p, u, ident, spans = C.c_void_p, C.c_uint, C.POINTER(Identity), C.POINTER(Span)
        signatures = {'si': [p, C.POINTER(StageMemory), p, u], 'sv': [p],
            'sb': [p, u, ident], 'sa': [p], 'sq': [p, p, u], 'so': [p, p, u],
            'sr': [p, u, spans], 'ss': [p, ident, p, u], 'sc': [p, ident],
            'sd': [p, u, ident, u], 'sp': [p, u, ident], 'sk': [p, u, ident], 'su': [p, u],
            'st': [p, u, C.POINTER(u)], 'sx': [p, u, ident, p, u, spans, u, p, C.c_int],
            'sl': [p, u, ident, p, u, spans, u, p],
            'sle': [p, u, ident, p, u, spans, u, p],
            'se': [p, u, ident, u, p], 'sch': [p], 'sz': [p, p, u, spans, u, C.POINTER(Result)],
            'zpack': [p, u, spans, u, spans, u, C.POINTER(Result)],
            'zrepack': [p, u, p, u, spans, u, spans, u, u, u, C.POINTER(Result)]}
        for name, sig in signatures.items(): getattr(self.lib, name).argtypes = sig
        self.lib.st.restype = p


def identity(raw, encoded, generation, kind):
    return Identity(generation, (0x89172000 + generation * 17 + kind) & 0xffffffff,
                    len(raw), len(encoded), zlib.adler32(raw), zlib.crc32(encoded), kind)


class StorePool:
    def __init__(self, harness, codec, sizes=None, staging=0x2f0000):
        self.pool = StagePool(harness, sizes=sizes, staging=staging)
        C.memset(self.pool.memory.banks[0], 0, 0x8000)
        self.codec = codec
        self.storage = Guarded(codec.lib.storeSize())
        self.table = Guarded(codec.lib.rt())
        self.roots = [None] * 3
        self.identities = [Identity() for _ in range(3)]
        assert codec.lib.si(self.storage.ptr, C.byref(self.pool.stage_memory), self.table.ptr, self.table.size)

    def call(self, name, *args):
        return getattr(self.codec.lib, name)(self.storage.ptr, *args)

    def begin(self, slot, expected=None):
        return self.call('sb', slot, C.byref(expected if expected is not None else self.identities[slot]))

    def append(self, encoded, kind, stop=None):
        if kind:
            pieces = [encoded[n:n+0x20000] for n in range(0, len(encoded), 0x20000)]
        else:
            pieces, off = [], 8
            while off < len(encoded):
                size = (struct.unpack_from('>I', encoded, off + 4)[0] & 0x7fffffff) + 8
                pieces.append(encoded[off:off+size]); off += size
            assert off == len(encoded)
        for index, data in enumerate(pieces):
            if index == stop: return False
            buffer = C.create_string_buffer(data)
            if not self.call('so' if kind else 'sq', buffer, len(data)): return False
        return stop != len(pieces)

    def seal(self, info):
        return self.call('ss', C.byref(info), self.codec.work.ptr, self.codec.work.size)

    def commit(self, slot, raw, encoded, info):
        assert self.call('sc', C.byref(info))
        self.identities[slot] = info
        self.roots[slot] = (raw, encoded)

    def put(self, slot, raw, encoded, generation, kind):
        info = identity(raw, encoded, generation, kind)
        if not self.begin(slot): return False
        if not self.append(encoded, kind) or not self.seal(info) or not self.call('sc', C.byref(info)):
            assert self.call('sa'); return False
        self.identities[slot], self.roots[slot] = info, (raw, encoded)
        return True

    def borrowed(self, slot):
        info = self.identities[slot]
        seq = self.call('sp', slot, C.byref(info))
        assert seq
        count = C.c_uint()
        address = self.call('st', seq, C.byref(count))
        assert address
        return seq, (Span * count.value).from_address(address)

    def decode(self, slot, protected=False):
        raw, encoded = self.roots[slot]
        info = self.identities[slot]
        seq, source = self.borrowed(slot)
        assert b''.join(C.string_at(s.data, s.size) for s in source) == encoded
        destination = Guarded(len(raw))
        before = destination.data()
        out = (Span * 1)(Span(destination.ptr, len(raw)))
        policy = DirectPolicy()
        expected = bytearray(raw)
        if protected:
            off = min(0x4000D, len(raw) // 2)
            count = min(31, len(raw) - off)
            policy.first, policy.last = destination.ptr + off, destination.ptr + off + count
            expected[off:off + count] = before[off:off + count]
        args = [seq, C.byref(info), self.codec.work.ptr, self.codec.work.size, out, 1, C.byref(policy)]
        assert self.call('sx', *args, 0) == 0 and destination.data() == before
        assert self.call('sx', *args, 1) == 0 and destination.data() == expected
        assert destination.guards() and self.call('su', seq)
        self.guards()

    def guards(self):
        assert self.call('sv') and self.storage.guards() and self.table.guards() and self.codec.work.guards()
        self.pool.canaries()


class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='state-store-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name); (folder / 'allocator').mkdir()
        cls.harness = StageHarness(folder / 'allocator'); cls.addClassCleanup(cls.harness.close)
        cls.codec = StoreCodec(folder); cls.addClassCleanup(cls.codec.close)

    def seeded(self, sizes=None, staging=0x2f0000):
        store = StorePool(self.harness, self.codec, sizes, staging)
        for slot, kind in enumerate((0, 1, 0)):
            raw = bytes([31 + slot]) * (0x20000 + slot * 71)
            packed = zlib.compress(raw) if kind else encode_quick(raw)
            assert store.put(slot, raw, packed, 101 + slot * 127, kind)
        return store

    def test_immediate_restore_preserves_filters_and_rejects_before_writes(self):
        store = StorePool(self.harness, self.codec, [0x60000] * 4)
        for slot, kind in enumerate((0, 1, 0)):
            raw = random.Random(610 + slot).randbytes(0x40111)
            packed = zlib.compress(raw) if kind else encode_quick(raw)
            self.assertTrue(store.put(slot, raw, packed, 100 + slot, kind))
        for slot in range(3):
            raw, _ = store.roots[slot]
            info = store.identities[slot]
            destination = Guarded(len(raw))
            before = destination.data()
            spans = (Span * 1)(Span(destination.ptr, len(raw)))
            policy = DirectPolicy()
            policy.first = destination.ptr + 0x20017
            policy.last = policy.first + 39
            expected = bytearray(raw)
            expected[0x20017:0x20017 + 39] = before[0x20017:0x20017 + 39]
            args = [slot, C.byref(info), self.codec.work.ptr, self.codec.work.size,
                    spans, 1, C.byref(policy)]
            self.assertEqual(store.call('sl', *args), 0)
            self.assertEqual(destination.data(), expected)
            self.assertTrue(destination.guards())
            self.assertTrue(store.begin(slot))
            self.assertTrue(store.call('sa'))

            # Existing payload corruption must fail before either write policy runs.
            chunk = store.pool.directory.chunks[store.pool.directory.slots[slot].ids[0] - 1]
            offset = chunk.offset
            for base, size in zip(store.pool.memory.banks, store.pool.memory.sizes):
                if offset < size:
                    address = base + offset + chunk.size - 1
                    break
                offset -= size
            byte = C.c_ubyte.from_address(address)
            byte.value ^= 1
            saved_output = destination.data()
            policy.copies = policy.queries = 0
            self.assertNotEqual(store.call('sl', *args), 0)
            self.assertEqual(destination.data(), saved_output)
            self.assertEqual((policy.copies, policy.queries), (0, 0))
            byte.value ^= 1

            stale = Identity.from_buffer_copy(bytes(info))
            stale.generation += 1
            args[1] = C.byref(stale)
            self.assertNotEqual(store.call('sl', *args), 0)
            self.assertEqual(destination.data(), saved_output)
            args[1] = C.byref(info)
            spans[0].data = self.codec.work.ptr
            self.assertNotEqual(store.call('sl', *args), 0)
            spans[0].data = destination.ptr
            self.assertEqual(store.call('sl', *args), 0)
            store.guards()

    def test_experimental_quick_load_keeps_bounds_identity_and_copy_policy(self):
        store = StorePool(self.harness, self.codec, [0x60000] * 4)
        raw = random.Random(912).randbytes(0x40111)
        self.assertTrue(store.put(0, raw, encode_quick(raw), 101, 0))
        info = store.identities[0]
        target = Guarded(len(raw))
        spans = (Span * 1)(Span(target.ptr, len(raw)))
        policy = DirectPolicy()
        policy.first, policy.last = target.ptr + 71, target.ptr + 99
        expected = bytearray(raw); expected[71:99] = target.data()[71:99]
        args = [0, C.byref(info), self.codec.work.ptr, self.codec.work.size, spans, 1, C.byref(policy)]
        self.assertEqual(store.call('sle', *args), 0)
        self.assertEqual(target.data(), expected)
        seq = store.call('sp', 0, C.byref(info))
        self.assertTrue(seq)
        self.assertNotEqual(store.call('sle', *args), 0)
        self.assertTrue(store.call('su', seq))
        self.assertTrue(store.begin(0))
        self.assertNotEqual(store.call('sle', *args), 0)
        self.assertTrue(store.call('sa'))
        stale = Identity.from_buffer_copy(bytes(info)); stale.generation += 1
        args[1] = C.byref(stale)
        self.assertNotEqual(store.call('sle', *args), 0)
        args[1] = C.byref(info)
        for address, size in ((self.codec.work.ptr, len(raw)), (target.ptr, len(raw) - 1)):
            spans[0] = Span(address, size)
            self.assertNotEqual(store.call('sle', *args), 0)
        self.assertEqual(target.data(), expected)
        spans[0] = Span(target.ptr, len(raw))
        root = store.pool.directory.slots[0]
        old_count = root.count; root.count = 257
        self.assertNotEqual(store.call('sle', *args), 0)
        root.count = old_count
        chunk = store.pool.directory.chunks[root.ids[0] - 1]
        old_size = chunk.size; chunk.size = 0xffffffff
        self.assertNotEqual(store.call('sle', *args), 0)
        chunk.size = old_size
        self.assertEqual(target.data(), expected)
        self.assertTrue(target.guards()); store.guards()

    def test_experimental_skip_is_explicit_and_deflate_stays_checked(self):
        for kind in (0, 1):
            store = StorePool(self.harness, self.codec, [0x60000] * 4)
            raw = random.Random(731).randbytes(4096)
            encoded = zlib.compress(raw) if kind else encode_quick(raw)
            self.assertTrue(store.put(0, raw, encoded, 101, kind))
            info = store.identities[0]
            chunk = store.pool.directory.chunks[store.pool.directory.slots[0].ids[0] - 1]
            byte = C.c_ubyte.from_address(store.pool.memory.banks[0] + chunk.offset + chunk.size - 1)
            byte.value ^= 1
            target = Guarded(len(raw)); before = target.data()
            spans = (Span * 1)(Span(target.ptr, len(raw))); policy = DirectPolicy()
            args = [0, C.byref(info), self.codec.work.ptr, self.codec.work.size, spans, 1, C.byref(policy)]
            self.assertNotEqual(store.call('sl', *args), 0)
            self.assertEqual(target.data(), before)
            status = store.call('sle', *args)
            if kind:
                self.assertNotEqual(status, 0); self.assertEqual(target.data(), before)
            else:
                self.assertEqual(status, 0)
                changed = raw[:-1] + bytes([raw[-1] ^ 1])
                self.assertEqual(target.data(), changed)
                self.assertNotEqual(zlib.adler32(changed), info.adler)
            self.assertTrue(target.guards())
            byte.value ^= 1
            self.assertTrue(store.begin(0)); self.assertTrue(store.call('sa')); store.guards()

    def test_mixed_roots_and_external_generations_survive_replacement(self):
        store = self.seeded()
        for slot in range(3): store.decode(slot, True)
        old = bytes(store.identities[1])
        raw = random.Random(331).randbytes(0x40111); encoded = zlib.compress(raw)
        self.assertTrue(store.put(1, raw, encoded, 9843, 1))
        self.assertFalse(store.begin(1, Identity.from_buffer_copy(old)))
        for slot in range(3): store.decode(slot, True)
        self.assertEqual(store.pool.stage('stGeneration', 1), 3)
        self.assertEqual(store.identities[1].generation, 9843)
        self.assertTrue(store.call('sd', 1, C.byref(store.identities[1]), 9911))
        store.identities[1] = Identity(9911)
        self.assertTrue(store.begin(1)); self.assertTrue(store.call('sa')); store.guards()

    def test_each_opaque_append_abort_preserves_all_roots(self):
        store = self.seeded()
        raw = random.Random(13).randbytes(0x60021); encoded = zlib.compress(raw)
        for stop in range((len(encoded) + 0x1ffff) // 0x20000 + 1):
            self.assertTrue(store.begin(1)); self.assertFalse(store.append(encoded, 1, stop))
            self.assertTrue(store.call('sa'))
            for slot in range(3): store.decode(slot)

    def test_opaque_corruption_kind_and_checksum_refuse_commit(self):
        store = self.seeded()
        raw = b'hello legacy' * 11000; encoded = zlib.compress(raw)
        for packed, kind, checksum in ((encoded[:-1] + bytes([encoded[-1] ^ 1]), 1, None),
                                       (encoded, 0, None), (encoded, 1, 1),
                                       (encode_quick(raw), 1, None)):
            self.assertTrue(store.begin(1)); self.assertTrue(store.append(packed, 1))
            info = identity(raw, packed, 8871, kind)
            if checksum is not None: info.checksum = checksum
            self.assertFalse(store.seal(info)); self.assertFalse(store.call('sc', C.byref(info)))
            self.assertTrue(store.call('sa'))
        for slot in range(3): store.decode(slot)

    def test_pool_full_reserve_refuses_without_releasing_old_roots(self):
        store = self.seeded([0x28000, 0x20000], 0x20000)
        self.assertTrue(store.begin(0))
        spans = (Span * 6)()
        self.assertEqual(store.call('sr', 0x90000, spans), 0)
        self.assertTrue(store.call('sa'))
        for slot in range(3): store.decode(slot)

    def test_final_capacity_and_sealed_payload_mutation_refuse_commit(self):
        store = self.seeded([0x28000, 0x20000], 0x80000)
        raw = random.Random(141).randbytes(0x50000); encoded = zlib.compress(raw)
        info = identity(raw, encoded, 123456, 1)
        self.assertTrue(store.begin(1)); self.assertTrue(store.append(encoded, 1)); self.assertTrue(store.seal(info))
        self.assertFalse(store.call('sc', C.byref(info))); self.assertTrue(store.call('sa'))
        for slot in range(3): store.decode(slot)
        raw = b'changed after seal' * 13000; encoded = zlib.compress(raw)
        info = identity(raw, encoded, 123457, 1)
        self.assertTrue(store.begin(1)); self.assertTrue(store.append(encoded, 1)); self.assertTrue(store.seal(info))
        index = store.pool.directory.slots[3].ids[0] - 1
        chunk = store.pool.directory.chunks[index]
        offset = chunk.offset
        for base, size in zip(store.pool.memory.banks, store.pool.memory.sizes):
            if offset < size: address = base + offset; break
            offset -= size
        else: address = store.pool.stage_memory.staging + offset
        C.c_ubyte.from_address(address + 2).value ^= 1
        self.assertFalse(store.call('sc', C.byref(info))); self.assertTrue(store.call('sa'))
        for slot in range(3): store.decode(slot)

    def test_pin_blocks_mutations_and_rejects_aliases_or_stale_identity(self):
        store = self.seeded()
        seq, _ = store.borrowed(1); info = store.identities[1]
        self.assertFalse(store.begin(0)); self.assertFalse(store.call('sa'))
        stale = Identity.from_buffer_copy(bytes(info)); stale.generation += 1
        self.assertFalse(store.call('sk', seq, C.byref(stale)))
        policy = DirectPolicy(); output = (Span * 1)(Span(store.pool.memory.banks[1], info.raw))
        self.assertEqual(store.call('sx', seq, C.byref(info), self.codec.work.ptr, self.codec.work.size,
                                    output, 1, C.byref(policy), 1), 1)
        self.assertTrue(store.call('su', seq)); self.assertFalse(store.call('su', seq))
        self.assertTrue(store.begin(0))
        self.assertFalse(store.call('so', store.pool.stage_memory.staging, 32))
        self.assertFalse(store.call('so', store.storage.ptr, 32))
        self.assertTrue(store.call('sa')); store.guards()

    def test_reserved_deflate_output_and_retained_repack_need_no_full_buffer(self):
        store = self.seeded()
        slot = 0; old = store.identities[slot]
        raw, encoded = store.roots[slot]
        second = Guarded(self.codec.work.size)
        self.assertTrue(store.begin(slot))
        seq, source = store.borrowed(slot)
        result = Result()
        args = [self.codec.work.ptr, self.codec.work.size, second.ptr, second.size,
                source, len(source)]
        self.codec.lib.zrepack(*args, None, 0, old.raw, old.adler, C.byref(result))
        self.assertEqual(result.status, 0)
        measured = (result.compressed, result.raw, result.adler)
        self.assertTrue(store.call('su', seq))
        output = (Span * 6)(); count = store.call('sr', measured[0], output)
        self.assertGreater(count, 0)
        seq, source = store.borrowed(slot)
        args[-2:] = [source, len(source)]
        self.codec.lib.zrepack(*args, output, count, old.raw, old.adler, C.byref(result))
        self.assertEqual(result.status, 0)
        self.assertEqual((result.compressed, result.raw, result.adler), measured)
        packed = b''.join(C.string_at(s.data, s.size) for s in output[:count])
        self.assertEqual(zlib.decompress(packed), raw)
        self.assertTrue(store.call('sk', seq, C.byref(old)))
        self.assertTrue(store.call('su', seq))
        info = identity(raw, packed, old.generation, 1)
        self.assertTrue(store.seal(info)); store.commit(slot, raw, packed, info)
        for slot in range(3): store.decode(slot, True)
        self.assertTrue(second.guards())

    def test_producer_and_validated_quick_export_plan_keep_root_pinned(self):
        store = self.seeded()
        raw = random.Random(9).randbytes(0x40211); src = Guarded(len(raw))
        C.memmove(src.ptr, raw, len(raw)); source = (Span * 1)(Span(src.ptr, len(raw)))
        self.assertTrue(store.begin(2)); result = Result()
        self.codec.lib.sz(store.storage.ptr, self.codec.work.ptr, self.codec.work.size, source, 1, C.byref(result))
        self.assertEqual(result.status, 0)
        root = store.pool.directory.slots[3]
        encoded = b'MSL4\x00\x02\x00\x00' + b''.join(store.pool.block(i - 1) for i in root.ids[:root.count])
        info = identity(raw, encoded, 99117, 0)
        self.assertTrue(store.seal(info)); store.commit(2, raw, encoded, info)
        seq, _ = store.borrowed(2)
        plan = Guarded(2080)
        self.assertTrue(store.call('se', seq, C.byref(info), 123, plan.ptr))
        values = struct.unpack('<520I', plan.data())
        reconstructed = b'MSL4\x00\x02\x00\x00'
        for index in range(values[2]):
            offset, length = values[8 + index*2:10 + index*2]
            # Find the matching retained descriptor instead of assuming physical bank order.
            descriptor = next(c for c in store.pool.directory.chunks if c.refs and c.offset == offset)
            self.assertEqual(descriptor.size, length)
            for n, c in enumerate(store.pool.directory.chunks):
                if c.refs and c.offset == offset: reconstructed += store.pool.block(n); break
        self.assertEqual(reconstructed, encoded)
        self.assertFalse(store.begin(0)); self.assertTrue(store.call('su', seq))
        store.decode(2, True); self.assertTrue(plan.guards() and src.guards())

    def test_opaque_export_omits_prefix_and_short_split_header_validates(self):
        store = self.seeded()
        raw = b'legacy header split across spans' * 20000; encoded = zlib.compress(raw)
        info = identity(raw, encoded, 87623, 1)
        self.assertTrue(store.begin(1))
        for part in (encoded[:1], encoded[1:2], encoded[2:]):
            buf = C.create_string_buffer(part)
            self.assertTrue(store.call('so', buf, len(part)))
        self.assertTrue(store.seal(info)); store.commit(1, raw, encoded, info)
        seq, _ = store.borrowed(1); plan = Guarded(2080)
        self.assertTrue(store.call('se', seq, C.byref(info), 773, plan.ptr))
        words = struct.unpack('<520I', plan.data())
        self.assertEqual((words[1], words[2], words[7]), (2, 3, 1))
        self.assertEqual(sum(words[9+2*n] for n in range(words[2])), len(encoded))
        self.assertTrue(store.call('su', seq)); store.decode(1, True)
        self.assertTrue(plan.guards())

    def test_changed_retained_kind_or_bytes_cannot_admit_another_candidate(self):
        store = self.seeded()
        index = store.pool.directory.slots[0].ids[0] - 1
        chunk = store.pool.directory.chunks[index]
        chunk.reserved = 1
        self.assertFalse(store.begin(1))
        chunk.reserved = 0
        address = store.pool.memory.banks[0] + chunk.offset + 8
        C.c_ubyte.from_address(address).value ^= 1
        self.assertFalse(store.begin(1))
        C.c_ubyte.from_address(address).value ^= 1
        self.assertTrue(store.begin(1)); self.assertTrue(store.call('sa'))
        for slot in range(3): store.decode(slot)


if __name__ == '__main__': unittest.main()
