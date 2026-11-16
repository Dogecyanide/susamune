"""Run the compiled no-stack retail spin observer and its installation guards."""
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
SHIM, TABLE, GLOBAL = 0x804e5800, 0x804e6000, 0x8060f000
QUEUE, STACK, OUT = 0x91004000, 0x81700000, 0x81700070
ENTRIES = {'jp': 0x80130758, 'us': 0x80251304, 'pal': 0x80249090}
CALLERS = {
    'jp': (0x8012b864, 0x80132cfc, 0x801330a4, 0x80133384, 0x80134c24, 0x80139384, 0x8013998c, 0x80139bf0, 0x8013c138),
    'us': (0x8024c3fc, 0x8025390c, 0x80253cb4, 0x80253f94, 0x80255834, 0x80259f94, 0x8025a530, 0x8025a794, 0x8025ccf4),
    'pal': (0x80244188, 0x8024b698, 0x8024ba40, 0x8024bd20, 0x8024d5c0, 0x80251d20, 0x802522bc, 0x80252520, 0x80254a80),
}
RETAIL = {'jp': '9421ffd0390000003920000088a305343cc04330c8c29c503405ffffc0829cccc0629cd038a00000c0429cd47c0903a6c0229cd8408100d8800305307ce02a14a80700006c0080009001002490c10020c80100209001002cec00302890c10028c8a10028fc002040eca530284180000cfc0518404081000c3800000190010010fc0428404c40138240820018fc0510404c4013824082000c3800000190010014fc02284040800014fc0508404080000c3800000190010018fc0128404c40138240820018fc0518404c4013824082000c380000019001001ca80700026c0080009001002490c10020c8010020ec003028fc0500404080000c39080001480000083929000138a500024200ff3080010010386000002c0000014082000838600001800100142c0000014082000838630001800100182c00000140820008386300018001001c2c00000140820008386300012c030004418000287c0848004081001038000002900400004800000c38000003900400003860000148000010380000049004000038600000382100304e800020', 'us': '9421ffd0390000003920000088a305343cc04330c8c2f0183405ffffc082f094c062f09838a00000c042f09c7c0903a6c022f0a0408100d8800305307ce02a14a80700006c0080009001002490c10020c80100209001002cec00302890c10028c8a10028fc002040eca530284180000cfc0518404081000c3800000190010010fc0428404c40138240820018fc0510404c4013824082000c3800000190010014fc02284040800014fc0508404080000c3800000190010018fc0128404c40138240820018fc0518404c4013824082000c380000019001001ca80700026c0080009001002490c10020c8010020ec003028fc0500404080000c39080001480000083929000138a500024200ff3080010010386000002c0000014082000838600001800100142c0000014082000838630001800100182c00000140820008386300018001001c2c00000140820008386300012c030004418000287c0848004081001038000002900400004800000c38000003900400003860000148000010380000049004000038600000382100304e800020', 'pal': '9421ffd0390000003920000088a305343cc04330c8c2ee903405ffffc082ef0cc062ef1038a00000c042ef147c0903a6c022ef18408100d8800305307ce02a14a80700006c0080009001002490c10020c80100209001002cec00302890c10028c8a10028fc002040eca530284180000cfc0518404081000c3800000190010010fc0428404c40138240820018fc0510404c4013824082000c3800000190010014fc02284040800014fc0508404080000c3800000190010018fc0128404c40138240820018fc0518404c4013824082000c380000019001001ca80700026c0080009001002490c10020c8010020ec003028fc0500404080000c39080001480000083929000138a500024200ff3080010010386000002c0000014082000838600001800100142c0000014082000838630001800100182c00000140820008386300018001001c2c00000140820008386300012c030004418000287c0848004081001038000002900400004800000c38000003900400003860000148000010380000049004000038600000382100304e800020'}


def signed(value, bits):
    return value-(1 << bits) if value & (1 << (bits-1)) else value


class Leaf:
    def __init__(self, sections, caller, result, direction, count=0, error=0, sequence=0):
        self.regs = [0x12340000+i for i in range(32)]
        self.regs[0], self.regs[1], self.regs[3], self.regs[4] = direction, STACK, result, OUT
        self.cr, self.lr, self.ctr, self.xer = 0xa531986c, caller, 0xabcdf001, 0xf1234567
        self.fpr = [(0x0102030405060708+i, 0x8877665544332200+i) for i in range(32)]
        self.fpscr = 0x12345678
        self.memory, self.writes = {}, []
        for address, data in sections:
            for i, byte in enumerate(data):
                self.memory[address+i] = byte
        for i in range(0x300):
            self.memory[STACK-0x100+i] = (i*37+13) & 255
        for i in range(496):
            self.memory[QUEUE+i] = 0
        self.put(GLOBAL, QUEUE)
        self.put(OUT, direction)
        self.put(QUEUE+16, count)
        self.put(QUEUE+20, error)
        self.put(QUEUE+24, sequence)
        self.put(QUEUE+348, 1)
        self.writes.clear()
        self.before_memory = dict(self.memory)
        self.before_regs = list(self.regs)
        self.before_special = (self.cr, self.lr, self.ctr, self.xer, list(self.fpr), self.fpscr)
        self.pc = SHIM

    def get(self, address):
        return int.from_bytes(bytes(self.memory[address+i] for i in range(4)), 'big')

    def put(self, address, value):
        for i, byte in enumerate((value & 0xffffffff).to_bytes(4, 'big')):
            self.memory[address+i] = byte
        self.writes.append(address)

    def compare(self, a, b, logical):
        if not logical:
            a, b = signed(a, 32), signed(b, 32)
        field = (8 if a < b else 4 if a > b else 2) | ((self.xer >> 31) & 1)
        self.cr = (self.cr & 0x0fffffff) | (field << 28)

    def run(self):
        for _ in range(400):
            word = self.get(self.pc)
            op, rt, ra, rb = word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
            immediate, next_pc = word & 0xffff, self.pc+4
            if op in (14, 15):
                self.regs[rt] = ((self.regs[ra] if ra else 0) + signed(immediate, 16)*(0x10000 if op == 15 else 1)) & 0xffffffff
            elif op == 24:
                self.regs[ra] = self.regs[rt] | immediate
            elif op == 7:
                self.regs[rt] = self.regs[ra] * signed(immediate, 16) & 0xffffffff
            elif op == 32:
                self.regs[rt] = self.get((self.regs[ra] if ra else 0)+signed(immediate, 16))
            elif op == 36:
                self.put((self.regs[ra] if ra else 0)+signed(immediate, 16), self.regs[rt])
            elif op in (10, 11):
                self.compare(self.regs[ra], immediate if op == 10 else signed(immediate, 16) & 0xffffffff, op == 10)
            elif op == 21:
                sh, mb, me = rb, (word >> 6) & 31, (word >> 1) & 31
                value = ((self.regs[rt] << sh) | (self.regs[rt] >> ((32-sh) & 31))) & 0xffffffff
                mask = sum(1 << (31-i) for i in range(32) if (mb <= i <= me if mb <= me else i >= mb or i <= me))
                if word & 1:
                    raise AssertionError('Observer must not modify XER or record arithmetic condition bits')
                self.regs[ra] = value & mask
            elif op == 31:
                xo = (word >> 1) & 1023
                if xo == 23:
                    self.regs[rt] = self.get((self.regs[ra] if ra else 0)+self.regs[rb])
                elif xo == 151:
                    self.put((self.regs[ra] if ra else 0)+self.regs[rb], self.regs[rt])
                elif xo == 444:
                    self.regs[ra] = self.regs[rt] | self.regs[rb]
                elif xo == 19:
                    self.regs[rt] = self.cr
                elif xo == 144:
                    if (word >> 12) & 255 != 255:
                        raise AssertionError('Expected complete CR restore')
                    self.cr = self.regs[rt]
                elif xo == 32:
                    self.compare(self.regs[ra], self.regs[rb], True)
                elif xo == 40:
                    self.regs[rt] = (self.regs[rb]-self.regs[ra]) & 0xffffffff
                elif xo == 266:
                    self.regs[rt] = (self.regs[ra]+self.regs[rb]) & 0xffffffff
                elif xo == 339:
                    spr = ((word >> 16) & 31) | ((word >> 6) & 0x3e0)
                    if spr != 8:
                        raise AssertionError('Observer must only read LR')
                    self.regs[rt] = self.lr
                else:
                    raise AssertionError(f'Unsupported observer instruction {word:08x}')
            elif op == 16:
                bo, bi = rt, ra
                if bo not in (4, 12) or word & 3:
                    raise AssertionError('Observer must not alter CTR or LR')
                bit = bool(self.cr & (1 << (31-bi)))
                if bit == (bo == 12):
                    next_pc = self.pc+signed(word & 0xfffc, 16)
            elif op == 18:
                if word & 3:
                    raise AssertionError('Observer must not call or replace LR')
                next_pc = self.pc+signed(word & 0x03fffffc, 26)
            elif word == 0x4e800020:
                self.pc = self.lr
                return self
            else:
                raise AssertionError(f'Unsupported observer instruction {word:08x}')
            self.pc = next_pc
        raise AssertionError('Observer did not return')


class SpinObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / 'toolchain/clang++.exe').exists():
            raise unittest.SkipTest('Bundled PPC compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='spin-observer-', dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        cls.sections, cls.objects, cls.hosts = {}, {}, {}
        cls.kernel32 = C.windll.kernel32
        cls.kernel32.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, C.c_ulong, C.c_ulong]
        cls.kernel32.VirtualAlloc.restype = C.c_void_p
        cls.kernel32.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, C.c_ulong]
        mapped = cls.kernel32.VirtualAlloc(C.c_void_p(0x80000000), 0x400000, 0x3000, 4)
        if mapped != 0x80000000:
            raise AssertionError('Cannot map isolated retail byte-proof fixture')
        cls.addClassCleanup(lambda: cls.kernel32.VirtualFree(C.c_void_p(mapped), 0, 0x8000))
        for index, region in enumerate(ENTRIES):
            obj = cls.work / f'{region}.o'
            subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=powerpc-gecko-ibm-kuribo-eabi',
                '-Oz', '-std=c++17', '-fsigned-char', '-fno-exceptions', '-fno-rtti', '-ffunction-sections',
                '-fdata-sections', '-Werror', '-DMOONSHINE_GHOST_TRACE=1', f'-DSUSAMUNE_VERSION_{region.upper()}=1',
                '-I', str(ROOT / 'include'), '-I', str(ROOT / 'include/JSystem'),
                '-c', str(ROOT / 'src/ghost_spin_observation.cpp'), '-o', str(obj)], check=True, capture_output=True)
            cls.objects[region] = obj
            script = cls.work / f'{region}.ld'
            script.write_text(f'ENTRY(ghostSpinObservationReturn)\nSECTIONS {{ . = {SHIM:#x}; '
                '.shim : { *(.text.ghostSpinObservationReturn) } '
                f'. = {TABLE:#x}; .table : {{ *(.rodata.ghostSpinCallers) }} '
                f'. = {GLOBAL:#x}; .pointer : {{ *(.bss.gGhostSpinObservationQueue) }} '
                '/DISCARD/ : { *(.text*) *(.rodata*) *(.data*) *(.bss*) *(.comment) *(.llvm_addrsig) *(.eh_frame) } }')
            elf_path = cls.work / f'{region}.elf'
            subprocess.run([str(ROOT / 'toolchain/ld.lld.exe'), '-T', str(script), '-o', str(elf_path), str(obj)], check=True, capture_output=True)
            with elf_path.open('rb') as stream:
                elf = ELFFile(stream)
                cls.sections[region] = [(s['sh_addr'], s.data()) for s in elf.iter_sections() if s['sh_flags'] & 2 and s['sh_size']]
            cls.hosts[region] = cls.host_library(region, index)

    @classmethod
    def host_library(cls, region, index):
        source = (ROOT / 'src/ghost_spin_observation.cpp').read_text(encoding='utf-8-sig')
        start = source.index('asm(\n')
        end = source.index('\nnamespace GhostSpinObservation {', start)
        source = source[:start] + source[end:]
        source += r'''
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){unsigned char*a=(unsigned char*)d;const unsigned char*b=(const unsigned char*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int v,__SIZE_TYPE__ n){unsigned char*p=(unsigned char*)d;while(n--)*p++=(unsigned char)v;return d;}
static unsigned writes;
void writeGameCode(u32 address,u32 word){*reinterpret_cast<volatile unsigned*>(static_cast<__UINTPTR_TYPE__>(address))=word;++writes;}
extern "C" void ghostSpinObservationReturn() {}
static GhostSpinObservation::Queue queues[2];
#define API extern "C" __declspec(dllexport)
API int installQueue(unsigned n){return GhostSpinObservation::install(queues[n&1]);}
API int uninstallQueue(){return GhostSpinObservation::uninstall();}
API int installPlaybackQueue(){queues[0].count=1;queues[0].read=0;queues[0].error=0;queues[0].sequence=9;return GhostSpinObservation::install(queues[0],GhostSpinObservation::PLAYBACK);}
API int uninstallOwner(unsigned mode){return GhostSpinObservation::uninstall(static_cast<GhostSpinObservation::Mode>(mode));}
API unsigned queueState(unsigned field){return field?queues[0].sequence:queues[0].count;}
API unsigned patchWord(){return GhostSpinObservation::hookWord();}
API unsigned patchWrites(){return writes;}
API unsigned ownerPresent(){return gGhostSpinObservationQueue!=nullptr;}
API void resetOwner(){gGhostSpinObservationQueue=nullptr;queues[0]={};queues[1]={};writes=0;}
'''
        file = cls.work / f'{region}-host.cpp'
        file.write_text(source, encoding='utf-8')
        dll = file.with_suffix('.dll')
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-U_WIN32', '-std=c++17', '-shared', '-nostdlib', '-fno-builtin', '-fno-exceptions', '-fno-rtti',
            '-O2', '-fuse-ld=lld', '-Wl,/noentry', '-Wl,/dynamicbase:no', f'-Wl,/base:{0x80700000+index*0x100000:#x}',
            '-DMOONSHINE_GHOST_TRACE=1', f'-DSUSAMUNE_VERSION_{region.upper()}=1',
            '-I', str(ROOT / 'include'), '-I', str(ROOT / 'include/JSystem'), str(file), '-o', str(dll)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout+result.stderr)
        lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
        lib.patchWord.restype = C.c_uint
        return lib

    def assert_preserved(self, trial, result=None, direction=None):
        expected = list(trial.before_regs)
        expected[1] += 48
        if result is not None:expected[3]=result
        self.assertEqual(trial.regs, expected)
        self.assertEqual((trial.cr, trial.lr, trial.ctr, trial.xer, trial.fpr, trial.fpscr), trial.before_special)
        self.assertEqual(trial.pc, trial.lr)
        self.assertTrue(all(QUEUE <= address <= QUEUE+492 or (direction is not None and address==OUT) for address in trial.writes))
        for address, byte in trial.before_memory.items():
            if not QUEUE <= address < QUEUE+496 and not (direction is not None and OUT<=address<OUT+4):
                self.assertEqual(trial.memory[address], byte, hex(address))

    def test_all_regional_callers_keep_registers_and_every_stack_byte(self):
        for region, callers in CALLERS.items():
            for ordinal, caller in enumerate(callers, 1):
                for result, direction in ((0, 4), (1, 2), (1, 3)):
                    with self.subTest(region=region, caller=ordinal, result=result, direction=direction):
                        trial = Leaf(self.sections[region], caller, result, direction, sequence=120).run()
                        self.assert_preserved(trial)
                        self.assertEqual([trial.get(QUEUE+i*4) for i in (4, 5, 6)], [1, 0, 121])
                        self.assertEqual([trial.get(QUEUE+28+i*4) for i in range(5)], [121, ordinal, result, direction, 1])

    def test_queue_keeps_call_order_without_overwriting_prior_events(self):
        for region, callers in CALLERS.items():
            trial = Leaf(self.sections[region], callers[0], 1, 2, count=15, sequence=20).run()
            self.assert_preserved(trial)
            self.assertEqual(trial.get(QUEUE+16), 16)
            self.assertEqual([trial.get(QUEUE+28+15*20+i*4) for i in range(5)], [21, 1, 1, 2, 1])
            self.assertEqual(bytes(trial.memory[QUEUE+28+i] for i in range(15*20)), bytes(15*20))

    def test_overflow_preserves_native_result_and_reports_clean_capture_error(self):
        for region, callers in CALLERS.items():
            trial = Leaf(self.sections[region], callers[4], 0, 4, count=16, error=2, sequence=25).run()
            self.assert_preserved(trial)
            self.assertEqual([trial.get(QUEUE+i*4) for i in (4, 5, 6)], [16, 3, 25])

    def test_unknown_retail_caller_errors_and_metadata_caller_is_skipped(self):
        for region in ENTRIES:
            for caller, error in ((ENTRIES[region]+4, 2), (0x804e2000, 0), (0x91080000, 0)):
                trial = Leaf(self.sections[region], caller, 0, 4).run()
                self.assert_preserved(trial)
                self.assertEqual([trial.get(QUEUE+i*4) for i in (4, 5, 6)], [0, error, 0])

    def test_malformed_native_tuple_flags_error_without_altering_game(self):
        for region, callers in CALLERS.items():
            for result, direction in ((2, 4), (0, 2), (1, 4), (1, 1), (1, 5)):
                trial = Leaf(self.sections[region], callers[2], result, direction).run()
                self.assert_preserved(trial)
                self.assertEqual([trial.get(QUEUE+i*4) for i in (4, 5, 6)], [0, 4, 0])

    def playback(self, region, caller=1, *, frame=7, tick=25, sequence=40, event_sequence=41,
                 event_frame=7, event_tick=25, result=1, direction=2, valid=1, native_caller=1):
        trial=Leaf(self.sections[region], CALLERS[region][native_caller-1], 0, 4, count=1, sequence=sequence)
        for offset,value in ((348,2),(352,0),(356,frame),(360,tick),(364,event_frame),(428,event_tick)):
            trial.put(QUEUE+offset,value)
        for i,value in enumerate((event_sequence,caller,result,direction,valid)):
            trial.put(QUEUE+28+4*i,value)
        trial.writes.clear()
        return trial

    def test_playback_applies_only_the_checked_return_and_direction(self):
        for region in ENTRIES:
            for caller in range(1,10):
                for result,direction in ((0,4),(1,2),(1,3)):
                    trial=self.playback(region,caller=caller,native_caller=caller,result=result,direction=direction).run()
                    self.assert_preserved(trial,result=result,direction=direction)
                    self.assertEqual(trial.get(OUT),direction)
                    self.assertEqual((trial.get(QUEUE+352),trial.get(QUEUE+24),trial.get(QUEUE+20)),(1,41,0))

    def test_playback_skips_observational_mod_calls_without_consuming_literals(self):
        for region in ENTRIES:
            trial=self.playback(region)
            trial.lr=0x804e2000
            before=list(trial.before_special);before[1]=trial.lr;trial.before_special=tuple(before)
            trial.run()
            self.assert_preserved(trial)
            self.assertEqual((trial.get(QUEUE+352),trial.get(QUEUE+20)),(0,0))

    def test_playback_rejects_caller_sequence_time_and_tuple_mismatches(self):
        for region in ENTRIES:
            for options,error in (({'caller':2},8),({'event_sequence':42},16),({'event_frame':8},64),
                                  ({'event_tick':26},64),({'result':1,'direction':4},4),({'valid':0},4)):
                trial=self.playback(region,**options).run()
                self.assert_preserved(trial)
                self.assertEqual((trial.get(QUEUE+352),trial.get(QUEUE+24),trial.get(QUEUE+20)),(0,40,error))

    def test_playback_underrun_is_clean_and_prior_error_stops_overrides(self):
        for region in ENTRIES:
            trial=self.playback(region)
            trial.put(QUEUE+16,0);trial.writes.clear();trial.run()
            self.assert_preserved(trial)
            self.assertEqual(trial.get(QUEUE+20),32)
            trial=self.playback(region)
            trial.put(QUEUE+20,8);trial.writes.clear();trial.run()
            self.assert_preserved(trial)
            self.assertEqual((trial.get(QUEUE+352),trial.get(QUEUE+20)),(0,8))

    def prepare_retail(self, region):
        lib = self.hosts[region]
        lib.resetOwner()
        words = struct.unpack('>100I', bytes.fromhex(RETAIL[region]))
        C.memmove(ENTRIES[region], struct.pack('<100I', *words), 400)
        return lib, C.c_uint.from_address(ENTRIES[region]+0x188)

    def test_install_uninstall_validate_complete_retail_bytes_and_owner(self):
        for region in ENTRIES:
            with self.subTest(region=region):
                lib, site = self.prepare_retail(region)
                self.assertEqual(site.value, 0x38210030)
                self.assertEqual(lib.installQueue(0), 1)
                self.assertEqual((site.value, lib.patchWrites(), lib.ownerPresent()), (lib.patchWord(), 1, 1))
                self.assertEqual(lib.installQueue(0), 1)
                self.assertEqual(lib.installQueue(1), 0)
                self.assertEqual(lib.patchWrites(), 1)
                self.assertEqual(lib.uninstallQueue(), 1)
                self.assertEqual((site.value, lib.patchWrites(), lib.ownerPresent()), (0x38210030, 2, 0))
                self.assertEqual(lib.uninstallQueue(), 1)
                self.assertEqual(lib.patchWrites(), 2)

    def test_foreign_or_changed_retail_code_is_never_overwritten(self):
        for region in ENTRIES:
            for offset in (0, 0x20, 0x184, 0x188, 0x18c):
                with self.subTest(region=region, offset=offset):
                    lib, site = self.prepare_retail(region)
                    word = C.c_uint.from_address(ENTRIES[region]+offset)
                    word.value ^= 1
                    changed = word.value
                    self.assertEqual(lib.installQueue(0), 0)
                    self.assertEqual(lib.patchWrites(), 0)
                    self.assertEqual(lib.ownerPresent(), 0)
                    self.assertEqual(word.value, changed)

    def test_failed_uninstall_retains_queue_until_foreign_change_is_resolved(self):
        for region in ENTRIES:
            lib, site = self.prepare_retail(region)
            self.assertEqual(lib.installQueue(0), 1)
            word = C.c_uint.from_address(ENTRIES[region]+0x20)
            word.value ^= 1
            self.assertEqual(lib.uninstallQueue(), 0)
            self.assertEqual((lib.patchWrites(), lib.ownerPresent()), (1, 1))
            word.value ^= 1
            self.assertEqual(lib.uninstallQueue(), 1)

    def test_playback_install_preserves_prefilled_literals_and_mode_ownership(self):
        for region in ENTRIES:
            lib,site=self.prepare_retail(region)
            self.assertEqual(lib.installPlaybackQueue(),1)
            self.assertEqual((lib.queueState(0),lib.queueState(1)),(1,9))
            self.assertEqual(lib.installQueue(0),0)
            self.assertEqual(lib.uninstallOwner(1),1)
            self.assertEqual((site.value,lib.ownerPresent(),lib.patchWrites()),(lib.patchWord(),1,1))
            self.assertEqual(lib.uninstallOwner(2),1)
            self.assertEqual((site.value,lib.ownerPresent(),lib.patchWrites()),(0x38210030,0,2))

    def test_unowned_foreign_code_is_a_noop_on_uninstall(self):
        for region in ENTRIES:
            lib,site=self.prepare_retail(region)
            site.value=0x60000000
            self.assertEqual(lib.uninstallQueue(),1)
            self.assertEqual((site.value,lib.ownerPresent(),lib.patchWrites()),(0x60000000,0,0))

    def test_only_one_pointer_of_persistent_mem1_storage(self):
        for region, path in self.objects.items():
            with path.open('rb') as stream:
                elf = ELFFile(stream)
                writable = sum(s['sh_size'] for s in elf.iter_sections() if s['sh_flags'] & 3 == 3)
                self.assertEqual(writable, 4, region)


if __name__ == '__main__':
    unittest.main()
