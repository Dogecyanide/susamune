"""Shared-directory CRC wiring: exact wire coverage and unchanged pool bounds."""
import ctypes as C
import tempfile
import unittest
import zlib

from test_timewarp_chunk_pool import DIRECTORY, Harness, Pool, plain
from timewarp_state_measure import FRAME


EXTRA = r'''
#include "susamune/state_root_reader.h"
extern "C" {
__declspec(dllexport) int crcAttach(TWBankMemory*p,void*s,unsigned n) {
 TWStageMemory m={p,(unsigned char*)s,n};return TWSAttach(&m,73);
}
__declspec(dllexport) unsigned crcRoot(TWBankMemory*p,void*s,unsigned n,unsigned slot) {
 TWStageMemory m={p,(unsigned char*)s,n};return TWSChecksum(&m,&TWChunkDirectory(p)->slots[slot]);
}
__declspec(dllexport) unsigned crcLayout(unsigned i) {
 const unsigned a[]={TWS_CRC_OFFSET,TWS_CONTROL_OFFSET,TWR_CONTROL_OFFSET,TWR_CONTROL_BYTES,
  TW_CHUNK_DIRECTORY_BYTES,TW_CRC_WORKSPACE_BYTES,sizeof(TWStageControl)};return a[i];
}
__declspec(dllexport) unsigned crcUpdate(TWBankMemory*p,unsigned crc,const void*d,unsigned n) {
 return TWCrcSharedUpdate(p->banks[0]+TWS_CRC_OFFSET,crc,d,n);
}
}
'''


class SharedCrcTests(unittest.TestCase):
    def test_wire_identity_and_directory_bounds(self):
        with tempfile.TemporaryDirectory(prefix='shared-state-crc-') as folder:
            h = Harness(folder, EXTRA)
            try:
                ptr, u = C.c_void_p, C.c_uint
                h.lib.crcAttach.argtypes = [ptr, ptr, u]
                h.lib.crcRoot.argtypes = [ptr, ptr, u, u]
                h.lib.crcUpdate.argtypes = [ptr, u, ptr, u]
                h.lib.crcRoot.restype = h.lib.crcUpdate.restype = u
                offset, control, reader, reader_bytes, charged, table_bytes, control_bytes = [
                    h.lib.crcLayout(i) for i in range(7)]
                self.assertEqual((offset, control, reader, reader_bytes, charged, table_bytes),
                                 (26784, 30880, 30976, 128, DIRECTORY, 4096))
                self.assertEqual(charged - reader - reader_bytes, 1664)
                pool = Pool(h, sizes=(DIRECTORY + 64, 256))
                stage_owner = C.create_string_buffer(b'\xbd' * 256)
                stage = (C.addressof(stage_owner) + 63) & ~31
                memory = C.byref(pool.memory)
                before = C.string_at(pool.memory.banks[0], DIRECTORY)
                self.assertTrue(h.lib.crcAttach(memory, stage, 128))
                after = C.string_at(pool.memory.banks[0], DIRECTORY)
                self.assertEqual(before[:offset], after[:offset])
                self.assertEqual(before[control + control_bytes:], after[control + control_bytes:])
                table = after[offset:control]
                self.assertEqual(len(table), 4096)

                payloads = [b'A', b'123', bytes(range(17))]
                capacity = sum(pool.memory.sizes)
                offsets = [DIRECTORY, DIRECTORY + 96, capacity + 32]
                addresses = [pool.memory.banks[0] + DIRECTORY, pool.memory.banks[1] + 32, stage + 32]
                root = pool.directory.slots[3]
                self.assertEqual(h.lib.crcRoot(memory, stage, 128, 3), 0)
                for kind in (0, 1):
                    blocks = payloads if kind else [plain(p) for p in payloads]
                    root.count = len(blocks)
                    for i, (block, location, address) in enumerate(zip(blocks, offsets, addresses)):
                        C.memmove(address, block, len(block))
                        chunk = pool.directory.chunks[i]
                        chunk.offset, chunk.size, chunk.refs, chunk.reserved = location, len(block), 1, kind
                        root.ids[i] = i + 1
                    wire = (b'' if kind else FRAME) + b''.join(blocks)
                    self.assertEqual(h.lib.crcRoot(memory, stage, 128, 3), zlib.crc32(wire))
                    C.c_ubyte.from_address(addresses[-1] + len(blocks[-1]) - 1).value ^= 0x80
                    changed = wire[:-1] + bytes([wire[-1] ^ 0x80])
                    self.assertEqual(h.lib.crcRoot(memory, stage, 128, 3), zlib.crc32(changed))

                data = bytes(range(255)) + b'tail'
                for alignment in range(4):
                    owner = C.create_string_buffer(b'!' * alignment + data)
                    for seed in (0, 0xffffffff, 0x12345678):
                        crc = seed
                        for start, end in ((0, 1), (1, 4), (4, 255), (255, len(data))):
                            crc = h.lib.crcUpdate(memory, crc, C.addressof(owner) + alignment + start, end - start)
                        self.assertEqual(crc, (~zlib.crc32(data, (~seed) & 0xffffffff)) & 0xffffffff)
                        self.assertEqual(h.lib.crcUpdate(memory, crc, None, 0), crc)
                self.assertEqual(C.string_at(pool.memory.banks[0] + offset, table_bytes), table)
                pool.canaries()
                self.assertEqual(C.string_at(stage, 32), b'\xbd' * 32)
                self.assertEqual(C.string_at(stage + 64, 64), b'\xbd' * 64)
            finally:
                h.close()


if __name__ == '__main__':
    unittest.main()
