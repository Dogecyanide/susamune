"""Check the compiled regional entry repair's write and register boundaries."""
from pathlib import Path
import struct, subprocess, tempfile, unittest
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
SHIM, APP = 0x81F00000, 0x803E6000
BOSS, ACTOR, MODEL, MATRICES = 0x81000000, 0x81001000, 0x81002000, 0x81003000

class KingBooEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="king-boo-entry-", dir=ROOT / "build")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.objects = {}
        for region in ("jp", "us", "pal"):
            obj = cls.folder / (region + ".o")
            subprocess.run([str(ROOT / "toolchain/clang++.exe"),
                "--target=powerpc-gecko-ibm-kuribo-eabi", "-Oz", "-std=c++17",
                "-fsigned-char", "-fno-exceptions", "-fno-rtti", "-ffunction-sections",
                "-fdata-sections", "-Werror", "-DIS_EMULATOR=1",
                "-DSUSAMUNE_VERSION_" + region.upper() + "=1",
                "-I", str(ROOT / "include"), "-I", str(ROOT / "include/JSystem"),
                "-c", str(ROOT / "src/king_boo_entry.cpp"), "-o", str(obj)],
                check=True, capture_output=True)
            cls.objects[region] = obj
        cls.codes = {}; cls.apps = {}
        import re
        for region in ("jp", "us", "pal"):
            cls.apps[region] = int(re.search(r'^gpApplication = (0x[0-9a-f]+);', (ROOT / f"maps/{region}.ld").read_text(), re.M).group(1), 16)
            layout=cls.folder/(region+'.ld');linked=cls.folder/(region+'.elf')
            layout.write_text('INCLUDE "'+(ROOT/f"maps/{region}.ld").as_posix()+'"\nENTRY(susamuneKingBooLoadAfter)\nSECTIONS { . = 0x81F00000; .shim : { *(.text.susamuneKingBooLoadAfter) } /DISCARD/ : { *(.text.init*) *(.comment) *(.llvm_addrsig) *(.eh_frame) } }\n')
            subprocess.run([str(ROOT/'toolchain/ld.lld.exe'),'-T',str(layout),'-o',str(linked),str(cls.objects[region])],check=True,capture_output=True)
            with linked.open('rb') as f:cls.codes[region]=ELFFile(f).get_section_by_name('.shim').data()
        cls.code=cls.codes['jp']

    def execute(self, scene, initial, region="jp"):
        APP=self.apps[region];code=self.codes[region]
        memory = {}; writes = []; reads = []
        def put(p, v, size=4):
            for i, b in enumerate(v.to_bytes(size, "big")):memory[p+i] = b
        def get(p, size=4):
            reads.append((p, size))
            return int.from_bytes(bytes(memory[p+i] for i in range(size)), "big")
        put(APP + 14, scene, 2)
        put(BOSS + 116, ACTOR); put(ACTOR + 4, MODEL); put(MODEL + 88, MATRICES)
        for i, word in enumerate(initial): put(MATRICES + i*4, word)
        before = dict(memory)
        regs = [0x12340000 + i for i in range(32)]; regs[3] = BOSS
        old_regs = list(regs); eq = False; returned = False
        for off in range(0, len(code), 4):
            word, = struct.unpack_from(">I", code, off)
            op, rt, ra = word >> 26, (word >> 21) & 31, (word >> 16) & 31
            imm = word & 0xffff; simm = imm - 65536 if imm & 32768 else imm
            if op in (14,15):regs[rt] = ((regs[ra] if ra else 0) + simm*(65536 if op==15 else 1)) & 0xffffffff
            elif op in (32,40):regs[rt] = get(regs[ra] + simm, 2 if op==40 else 4)
            elif op==11:eq = regs[ra] == simm
            elif op==36:
                address=regs[ra]+simm; put(address,regs[rt]); writes.append((address,4))
            elif word==0x4c820020:
                if not eq:returned=True;break
            elif word==0x4e800020:returned=True;break
            else:raise AssertionError("Unexpected instruction %08x" % word)
        self.assertTrue(returned)
        for i in set(range(32)) - {0,4}:self.assertEqual(regs[i],old_regs[i])
        return memory,before,writes,reads

    def test_only_the_two_initial_translation_words_change(self):
        for filler in (0,0xffffffff,0x7fc00001,0xf000000f):
            initial=[filler ^ i for i in range(64)]
            memory,before,writes,_=self.execute(0x3800,initial)
            self.assertEqual(writes,[(MATRICES+60,4),(MATRICES+92,4)])
            expected=dict(before)
            for address in (MATRICES+60,MATRICES+92):
                for i in range(4):expected[address+i]=0
            self.assertEqual(memory,expected)

    def test_other_scenes_do_not_read_the_actor_or_write_anything(self):
        for scene in (0,0x0604,0x0702,0x0e01,0x3801,0x3900,0xffff):
            memory,before,writes,reads=self.execute(scene,[0xdeadbeef]*64)
            self.assertEqual(memory,before);self.assertEqual(writes,[])
            self.assertEqual(reads,[(APP+14,2)])

    def test_all_regions_preserve_only_the_two_initial_words(self):
        for region in ("jp","us","pal"):
            memory,before,writes,_=self.execute(0x3800,[0xf000000f]*64,region)
            self.assertEqual(writes,[(MATRICES+60,4),(MATRICES+92,4)])
            memory,before,writes,reads=self.execute(0x700,[0xf000000f]*64,region)
            self.assertEqual(memory,before);self.assertEqual(writes,[]);self.assertEqual(reads,[(self.apps[region]+14,2)])
    def test_no_writable_storage_is_added(self):
        for region,obj in self.objects.items():
            with obj.open("rb") as f:
                for section in ELFFile(f).iter_sections():
                    if section["sh_size"]:self.assertNotEqual(section["sh_flags"]&3,3)

if __name__ == "__main__": unittest.main()
