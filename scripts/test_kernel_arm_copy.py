"""Execute the shipped ARM instructions, including the kernel's own memcpy.

Requires pyelftools and unicorn. Run with KERNEL_ELF set to the release kernel.
Host C fixtures cannot catch ABI errors in the assembly copy routine.
"""
import os
from pathlib import Path
import unittest

from elftools.elf.elffile import ELFFile
try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_MODE_BIG_ENDIAN
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR
except ImportError:
    if os.environ.get('KERNEL_ELF'):
        raise
    Uc = None


@unittest.skipUnless(Uc, 'Install unicorn to execute the ARM regression tests')
class KernelCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('KERNEL_ELF')
        if not path:
            raise unittest.SkipTest('Set KERNEL_ELF to the compiled launcher kernel')
        with Path(path).open('rb') as stream:
            elf = ELFFile(stream)
            cls.sections = [(s['sh_addr'], s.data()) for s in elf.iter_sections()
                            if s['sh_flags'] & 2 and s['sh_type'] != 'SHT_NOBITS']
            cls.symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}

    def setUp(self):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM | UC_MODE_BIG_ENDIAN)
        for address, size in ((0x12F00000, 0x100000), (0x13000000, 0x10000), (0x100000, 0x10000)):
            self.cpu.mem_map(address, size)
        for address, data in self.sections:
            self.cpu.mem_write(address, data)

    def call(self, name, *args):
        stack, stop = 0x1300F000, 0x13000000
        self.cpu.reg_write(UC_ARM_REG_SP, stack)
        self.cpu.reg_write(UC_ARM_REG_LR, stop)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            self.cpu.reg_write(reg, value)
        for i, value in enumerate(args[4:]):
            self.cpu.mem_write(stack + 4 * i, value.to_bytes(4, 'big'))
        self.cpu.emu_start(self.symbols[name], stop, count=100000)
        self.assertEqual(self.cpu.reg_read(UC_ARM_REG_SP), stack)
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def test_copy_returns_original_destination_and_preserves_boundaries(self):
        for base in (0x100000, 0x13001000):
            for align in range(4):
                for length in (0, 1, 3, 4, 15, 16, 31, 32, 33, 80, 272):
                    with self.subTest(base=base, align=align, length=length):
                        destination, source = base + 32 + align, 0x13003000 + align
                        data = bytes(i % 251 for i in range(length))
                        self.cpu.mem_write(base, b'\xa5' * 512)
                        self.cpu.mem_write(source, data or b'\0')
                        self.assertEqual(self.call('memcpy', destination, source, length), destination)
                        self.assertEqual(bytes(self.cpu.mem_read(destination, length)), data)
                        self.assertEqual(bytes(self.cpu.mem_read(destination - 1, 1)), b'\xa5')
                        self.assertEqual(bytes(self.cpu.mem_read(destination + length, 1)), b'\xa5')

    def test_three_movement_streams_reach_consumer_without_overwriting_output(self):
        slots, cursor, output = 0x13005000, 0x13006000, 0x13007000
        endpoint, payload = 0x13001000, 0x13002000
        for sequence in (1, 2):
            for peer in range(3):
                self.cpu.mem_write(endpoint, bytes((192, 168, 1, peer + 1, 0xBC, 0x5E, 0, 0)))
                self.cpu.mem_write(payload, bytes((peer, sequence)) * 40)
                self.assertEqual(self.call('latestSet', slots, 17, endpoint, payload, 80), 1)
        seen = set()
        for _ in range(3):
            self.cpu.mem_write(output - 32, b'\xa5' * (272 * 4))
            self.assertEqual(self.call('latestTake', slots, cursor, 17, output), 1)
            packet = bytes(self.cpu.mem_read(output, 272))
            seen.add(packet[3])
            self.assertEqual(int.from_bytes(packet[8:12], 'big'), 17)
            self.assertEqual(int.from_bytes(packet[12:16], 'big'), 80)
            self.assertEqual(packet[16:96], bytes((packet[3] - 1, 2)) * 40)
            self.assertEqual(bytes(self.cpu.mem_read(output - 32, 32)), b'\xa5' * 32)
            self.assertEqual(bytes(self.cpu.mem_read(output + 272, 272 * 2)), b'\xa5' * (272 * 2))
        self.assertEqual(seen, {1, 2, 3})
        self.assertEqual(self.call('latestTake', slots, cursor, 17, output), 0)


if __name__ == '__main__':
    unittest.main()
