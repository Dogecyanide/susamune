import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ppc_multiple_words as words

ROOT = pathlib.Path(__file__).resolve().parents[1]


def function(name, body, section=None):
    section = section or ".text." + name
    return (f'\t.section\t{section},"ax",@progbits\n\t.type\t{name},@function\n{name}:\n'
            + "".join("\t" + line + "\n" if not line.endswith(":") else line + "\n" for line in body)
            + f"\t.size\t{name}, .Lfunc_end-{name}\n")


FULL = ["mflr 0", "stw 0, 4(1)", "stwu 1, -32(1)",
        "stw 28, 16(1)", "stw 29, 20(1)", "mr\t29, 3", "stw 30, 24(1)", "stw 31, 28(1)",
        "bl callee", "lwz 31, 28(1)", "lwz 30, 24(1)", "lwz 29, 20(1)", "lwz 28, 16(1)",
        "lwz 0, 36(1)", "addi 1, 1, 32", "mtlr 0", "blr"]


class FoldTests(unittest.TestCase):
    def fold(self, body, name="f", section=None):
        return words.rewrite(function(name, body, section))

    def test_full_run_becomes_stmw_and_lmw(self):
        text, saved = self.fold(FULL)
        self.assertEqual(saved, 6)
        self.assertIn("\tstmw 28, 16(1)\n\tmr\t29, 3\n", text)
        self.assertIn("\tlmw 28, 16(1)\n\tlwz 0, 36(1)\n", text)
        self.assertNotRegex(text, r"\tstw (2[89]|3[01]),")
        self.assertNotRegex(text, r"\tlwz (2[89]|3[01]),")

    def test_partial_run_keeps_r31_entry_value_in_its_unused_slot(self):
        body = ["mflr 0", "stw 0, 4(1)", "stwu 1, -32(1)", "stw 29, 20(1)", "stw 30, 24(1)",
                "bl callee", "lwz 30, 24(1)", "lwz 29, 20(1)", "lwz 0, 36(1)",
                "addi 1, 1, 32", "mtlr 0", "blr"]
        text, saved = self.fold(body)
        self.assertEqual(saved, 2)
        self.assertIn("\tstmw 29, 20(1)\n", text)
        self.assertIn("\tlmw 29, 20(1)\n", text)

    def test_partial_run_is_left_alone_when_r31_slot_or_register_is_used(self):
        used_slot = FULL[:3] + ["stw 29, 20(1)", "stw 30, 24(1)", "stw 3, 28(1)", "bl callee",
                                "lwz 30, 24(1)", "lwz 29, 20(1)", "addi 1, 1, 32", "blr"]
        self.assertEqual(self.fold(used_slot)[1], 0)
        writes_r31 = FULL[:3] + ["stw 29, 20(1)", "stw 30, 24(1)", "li 31, 0", "bl callee",
                                 "lwz 30, 24(1)", "lwz 29, 20(1)", "addi 1, 1, 32", "blr"]
        self.assertEqual(self.fold(writes_r31)[1], 0)

    def test_prologue_with_early_write_is_not_folded(self):
        body = list(FULL)
        body.insert(3, "mr\t30, 4")
        text, _ = self.fold(body)
        self.assertNotIn("stmw", text)
        self.assertIn("\tstw 28, 16(1)\n", text)

    def test_restore_block_that_reads_a_restored_register_stays_single_word(self):
        body = FULL[:9] + ["lwz 31, 28(1)", "mr\t3, 31", "lwz 30, 24(1)", "lwz 29, 20(1)",
                           "lwz 28, 16(1)", "addi 1, 1, 32", "blr"]
        text, _ = self.fold(body)
        self.assertIn("stmw", text)
        self.assertNotIn("lmw", text)

    def test_incomplete_restore_block_is_not_folded(self):
        body = FULL[:9] + ["lwz 31, 28(1)", "lwz 30, 24(1)", "addi 1, 1, 32", "blr"]
        text, _ = self.fold(body)
        self.assertNotIn("lmw", text)

    def test_every_return_block_is_folded(self):
        body = FULL[:9] + ["cmpwi 3, 0", "beq 0, .LBB0_2",
                           "lwz 28, 16(1)", "lwz 29, 20(1)", "lwz 30, 24(1)", "lwz 31, 28(1)",
                           "addi 1, 1, 32", "blr", ".LBB0_2:",
                           "lwz 28, 16(1)", "lwz 29, 20(1)", "lwz 30, 24(1)", "lwz 31, 28(1)",
                           "addi 1, 1, 32", "b tail"]
        text, saved = self.fold(body)
        self.assertEqual(text.count("\tlmw 28, 16(1)"), 2)
        self.assertEqual(saved, 3 + 3 + 3)

    def test_shared_frozen_sections_and_protected_functions_are_untouched(self):
        self.assertEqual(self.fold(FULL, section=".foxtrot.text")[1], 0)
        self.assertEqual(self.fold(FULL, name="paused__15PracticeSessionFv")[1], 0)

    def test_quoted_branch_targets_become_expressions(self):
        text = '\tbl "point<f>"\n\tb\t"x<y>"\n\tlis 3, "q"@ha\n'
        self.assertEqual(words.quote_branch_targets(text),
                         '\tbl ("point<f>")\n\tb\t("x<y>")\n\tlis 3, "q"@ha\n')


COMPILER = ROOT / "toolchain" / ("clang++.exe" if sys.platform == "win32" else "clang++")


@unittest.skipUnless(COMPILER.exists(), "Kuribo toolchain not present")
class ToolchainTests(unittest.TestCase):
    def test_wrapper_emits_stmw_and_lmw(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            source = folder / "sample.cpp"
            source.write_text("extern int g(int);\nint f(int a,int b,int c,int d,int e){"
                              "int x=g(a);int y=g(b+x);int z=g(c+y);int w=g(d+z);"
                              "return g(e+w)+x+y+z+w+a+b+c+d+e;}\n")
            obj = folder / "sample.o"
            flags = ["--target=powerpc-gecko-ibm-kuribo-eabi", "-Oz", "-ffunction-sections", "-fno-unwind-tables"]
            subprocess.check_call([sys.executable, str(ROOT / "scripts/ppc_multiple_words.py"),
                                   str(COMPILER), *flags, "-o", str(obj), "-c", str(source)])
            listing = subprocess.check_output([str(COMPILER), *flags, "-S", "-o", "-",
                                               str(source)], text=True)
            data = obj.read_bytes()
            stmw = sum(1 for i in range(0, len(data) - 3, 4) if data[i] >> 2 == 47)
            lmw = sum(1 for i in range(0, len(data) - 3, 4) if data[i] >> 2 == 46)
            self.assertIn("stw 30,", listing)
            self.assertGreaterEqual(stmw, 1)
            self.assertGreaterEqual(lmw, 1)


if __name__ == "__main__":
    unittest.main()
