"""Retained CPU functions keep the same new-input audit and own no frozen range."""
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest

from elftools.elf.elffile import ELFFile

import pinned_cold_extensions as extensions


def fixture(owner="live_race.cpp", name=None):
    name = name or sorted(extensions.NEW_MODULES[owner])[0]
    function = dict(name=name, owner=owner, old_address=0x80520000, size=280)
    row = dict(name=".text." + name, group="", live=True, cold=False, moved=True,
               flags=6, type="SHT_PROGBITS", owners=[owner], bytes=280, sha256="current",
               analysis_address=function["old_address"],
               definitions=[dict(name=name, type="STT_FUNC", value=0, size=280)])
    return [row], [function], dict(sections=[])


class Mem1RetentionTests(unittest.TestCase):
    def test_console_whitelist_is_new_exclusive_and_leaves_emulator_policy_unchanged(self):
        self.assertEqual(len(extensions.RETAIN_MEM1_CONSOLE_FUNCTIONS), 51)
        for name in extensions.RETAIN_MEM1_CONSOLE_FUNCTIONS:
            owners = [owner for owner, names in extensions.NEW_MODULES.items() if name in names]
            self.assertEqual(len(owners), 1, name)
            self.assertNotIn(owners[0], extensions.RETAIN_MEM1_MODULES)
            for target in ("console", "emu"):
                rows, functions, baseline = fixture(owners[0], name)
                extensions.mark_inputs(rows, functions, baseline, target=target)
                self.assertEqual(bool(rows[0].get("retained_mem1_cpu")), target == "console")
                self.assertEqual(bool(functions[0].get("retained_mem1")), target == "console")
                self.assertEqual(bool(rows[0].get("cold_new")), target == "emu")

    def test_only_audited_new_module_inputs_remain_in_mem1(self):
        self.assertEqual(extensions.RETAIN_MEM1_MODULES,
                         {"live_race.cpp", "live_race_session.cpp", "live_relay.cpp"})
        for owner in extensions.RETAIN_MEM1_MODULES:
            rows, functions, baseline = fixture(owner)
            extensions.mark_inputs(rows, functions, baseline)
            self.assertTrue(rows[0]["retained_mem1_cpu"])
            self.assertTrue(functions[0]["retained_mem1"])
            self.assertTrue(rows[0]["moved"])
            self.assertFalse(rows[0]["cold"])
            self.assertNotIn("cold_new", rows[0])
        rows, functions, baseline = fixture("live_transport.cpp")
        extensions.mark_inputs(rows, functions, baseline)
        self.assertTrue(rows[0]["cold_new"])
        self.assertNotIn("retained_mem1", functions[0])

    def test_frozen_mutable_shared_partial_or_protected_inputs_still_fail(self):
        for change in ("frozen", "mutable", "shared", "partial", "protected", "unknown"):
            rows, functions, baseline = fixture()
            protected = []
            if change == "frozen": baseline["sections"] = deepcopy(rows)
            elif change == "mutable": rows[0]["flags"] = 7
            elif change == "shared": rows[0]["owners"].append("other.cpp")
            elif change == "partial": rows[0]["definitions"][0]["size"] -= 4
            elif change == "protected": protected = [dict(address=0x80520000, size=4)]
            else:
                functions[0]["name"] += "_unreviewed"
                rows[0]["definitions"][0]["name"] = functions[0]["name"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                extensions.mark_inputs(rows, functions, baseline, protected)

    def test_new_icon_comdat_must_have_one_owner_and_no_frozen_predecessor(self):
        rows, functions, baseline = fixture("menu_native_icon.cpp")
        rows[0].update(group=functions[0]["name"], flags=0x206)
        functions[0]["exclusive_comdat"] = True
        extensions.mark_inputs(rows, functions, baseline, target="console")
        self.assertTrue(rows[0]["cold_new"])
        for change in ("frozen", "shared", "wrong_group", "no_proof", "wrong_module"):
            trial_rows, trial_functions, trial_baseline = deepcopy((rows, functions, baseline))
            trial_rows[0].update(cold=False, moved=True)
            if change == "frozen":
                trial_baseline["sections"] = deepcopy(trial_rows)
            elif change == "shared":
                trial_rows[0]["owners"].append("other.cpp")
            elif change == "wrong_group":
                trial_rows[0]["group"] += "_alias"
            elif change == "no_proof":
                trial_functions[0].pop("exclusive_comdat")
            else:
                trial_functions[0]["owner"] = "unreviewed.cpp"
                trial_rows[0]["owners"] = ["unreviewed.cpp"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                extensions.mark_inputs(trial_rows, trial_functions, trial_baseline, target="console")

    def test_real_new_comdat_rejects_extra_storage_and_nonweak_binding(self):
        folder = Path(__file__).resolve().parents[1] / "build/pr17-icon-comdat-proof"
        folder.mkdir(parents=True, exist_ok=True)
        compiler = folder.parents[1] / "toolchain/clang.exe"
        for variant in ("valid", "extra", "global"):
            assembly = folder / (variant + ".s")
            text = '''
.section .text.fixture,"axG",@progbits,fixture,comdat
.balign 4
.weak fixture
.type fixture,@function
fixture:
blr
.size fixture,.-fixture
'''
            if variant == "extra":
                text += '.section .rodata.fixture,"aG",@progbits,fixture,comdat\n.long 1\n'
            elif variant == "global":
                text = text.replace(".weak", ".global")
            assembly.write_text(text)
            target = assembly.with_suffix(".o")
            subprocess.run([str(compiler), "--target=powerpc-gecko-ibm-kuribo-eabi",
                            "-c", str(assembly), "-o", str(target)], check=True, capture_output=True)
            with target.open("rb") as stream:
                elf = ELFFile(stream)
                index = next(i for i, s in enumerate(elf.iter_sections()) if s.name == ".text.fixture")
                if variant == "valid":
                    extensions.verify_new_comdat(elf, index, "fixture")
                else:
                    with self.subTest(variant=variant), self.assertRaises(ValueError):
                        extensions.verify_new_comdat(elf, index, "fixture")


if __name__ == "__main__":
    unittest.main()
