"""Owned PAL IS_EMULATOR cold-menu execution pilot; no ARM/Wii claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import struct
import time

from elftools.elf.elffile import ELFFile

from timewarp_cold_cluster import ROOT, align, sha, run
from timewarp_cross_level_measure import Capture, digest
import timewarp_timer_guard as guard


class Dol:
    def __init__(self, data):
        self.data = bytearray(data)

    def sections(self):
        return [(i, *(struct.unpack_from(">I", self.data, b + 4 * i)[0] for b in (0, 0x48, 0x90)))
                for i in range(18) if struct.unpack_from(">I", self.data, 0x90 + 4 * i)[0]]

    def offset(self, address, size=4):
        matches = [off + address - base for _, off, base, length in self.sections()
                   if base <= address and address + size <= base + length]
        if len(matches) != 1:
            raise ValueError("DOL address not in exactly one loaded section")
        return matches[0]

    def add(self, address, payload, text):
        for _, _, base, size in self.sections():
            if address < base + size and base < address + len(payload):
                raise ValueError("Private DOL section overlaps existing storage")
        slots = range(7) if text else range(7, 18)
        used = {i for i, _, _, _ in self.sections()}
        index = next(i for i in slots if i not in used)
        self.data.extend(bytes(align(len(self.data)) - len(self.data)))
        offset = len(self.data)
        self.data.extend(payload)
        for start, value in ((0, offset), (0x48, address), (0x90, len(payload))):
            struct.pack_into(">I", self.data, start + 4 * index, value)


def branch(site, target, link=True):
    displacement = target - site
    if displacement & 3 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("Private hook is outside REL24 range")
    return 0x48000000 | displacement & 0x03FFFFFC | int(link)


def prepare(folder, artifacts, fixture, retail, pinned_build=None):
    if pinned_build:
        from gen_mod_bin import build_mod_bin, verified_artifact
        manifest_path = pinned_build / "susamune_manifest_pal.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("transport_environment") != "dolphin" or manifest.get("target") != "emu":
            raise ValueError("Runtime requires an explicit IS_EMULATOR source build")
        container = build_mod_bin(manifest, format_version=4, base_dir=pinned_build)
        if container != (pinned_build / "mod_pal.bin").read_bytes():
            raise ValueError("Source manifest no longer matches its packed container")
        cold = verified_artifact(manifest["cold_image"], pinned_build, "cold image")
        cold_base = manifest["cold_image"]["vma"]
        retained_elf = pinned_build / "susamune_pal.o"
        proof = json.loads(verified_artifact(manifest["pinned_link_receipt"], pinned_build, "pinned link receipt"))
        if digest(retained_elf) != proof.get("elf_sha256"):
            raise ValueError("Source-linked ELF no longer matches its receipt")
        guard.verify(json.loads(guard.BASELINE.read_text()), pinned_build, "emu", ["pal"])
        input_evidence = {"input_kind": "source-linked", "manifest_sha256": digest(manifest_path),
                          "pinned_link_receipt_sha256": manifest["pinned_link_receipt"]["sha256"],
                          "container_sha256": sha(container)}
        spans = [(manifest["base_addr"] + span["offset"], span["memory_size"],
                  bytes.fromhex(span["code"])) for span in manifest["segments"]]
    else:
        receipt = json.loads((artifacts / "receipt.json").read_text())
        if receipt.get("input_target") != "emu" or not receipt.get("consolidate"):
            raise ValueError("Runtime requires consolidated IS_EMULATOR input")
        row = next(r for r in receipt["regions"] if r["region"] == "pal")
        variant = row["variants"]["dolphin-vma"]
        region = artifacts / "pal"
        cold = (region / "cold-dolphin-vma.bin").read_bytes()
        if sha(cold) != variant["cold"]["payload_sha256"]:
            raise ValueError("Cold payload changed")
        cold_base = variant["cold"]["vma"]
        retained_elf = region / "retained-dolphin-vma.elf"
        manifest_path = ROOT / "build/baseline-emu/susamune_manifest_pal.json"
        manifest = json.loads(manifest_path.read_text())
        input_evidence = {"input_kind": "postlink-prototype", "manifest_sha256": digest(manifest_path),
                          "cold_artifacts_receipt_sha256": digest(artifacts / "receipt.json")}
        spans = []
        for span in variant["retained"]["initialized_spans"]:
            data = Path(span["path"]).read_bytes()
            if sha(data) != span["sha256"]:
                raise ValueError("Hot span changed")
            spans.append((span["address"], span["runtime_bytes"], data))
    base = 0x80420D60
    stage = base + 0x58000 if len(cold) <= 0x20000 else 0x81000000
    stub, box = base + 0xBF000, base + 0xBFF00
    pad_stub, control = stub + 0x400, box + 0x80
    symbols = {}
    with retained_elf.open("rb") as stream:
        elf = ELFFile(stream)
        for symbol in elf.get_section_by_name(".symtab").iter_symbols():
            if symbol.name and symbol["st_shndx"] != "SHN_UNDEF":
                symbols[symbol.name] = symbol["st_value"]
    protected = json.loads(guard.BASELINE.read_text())["builds"]["emu-pal"]
    protected_ranges = list(protected["symbols"].values()) + [{"address": base + 0x7FFC0, "size": 64}]
    dol = Dol(retail.read_bytes())
    retail_ranges = [(address, size) for _, _, address, size in dol.sections()]
    retail_ranges.append(struct.unpack_from(">II", dol.data, 0xD8))
    for start, size in ((stage, len(cold)), (stub, 0x1000)):
        if any(start < address + length and address < start + size for address, length in retail_ranges):
            raise ValueError("Staging/shim overlaps retail DOL storage")
        if any(start < s["address"] + s["size"] and s["address"] < start + size for s in protected_ranges):
            raise ValueError("Staging/shim overlaps protected timer storage")
    if len(cold) > 0x100000:
        raise ValueError("Cold staging exceeds the bounded private boot window")
    hot = {}
    for address, runtime_bytes, data in spans:
        capacity = 0x40000 if address == base + 0x80000 else align(runtime_bytes)
        if address == base + 0x80000 and address + runtime_bytes > stub:
            raise ValueError("No unused upper tail for the private shim")
        hot[address] = bytearray(data + bytes(capacity - len(data)))
    startup = struct.unpack_from(">I", dol.data, 0xE0)[0]
    if startup != symbols["__start"]:
        raise ValueError("Unexpected retail startup entry")
    if struct.unpack_from(">I", dol.data, dol.offset(startup))[0] != branch(startup, symbols["__init_registers"]):
        raise ValueError("Retail startup does not initialize registers first")
    boot_site = startup + 4
    if struct.unpack_from(">I", dol.data, dol.offset(boot_site))[0] != branch(boot_site, symbols["__init_hardware"]):
        raise ValueError("Early hardware call differs from the audited startup")
    asm = folder / "adapters.S"
    load = lambda reg, value: f"lis {reg},{value >> 16}\nori {reg},{reg},{value & 0xffff}\n"
    asm.write_text(".section .text.boot,\"ax\"\n.global bootShim\nbootShim:\n"
        "stwu 1,-160(1)\nstw 0,4(1)\nstmw 2,8(1)\nmflr 0\nstw 0,164(1)\n"
        "mfcr 0\nstw 0,132(1)\nmfctr 0\nstw 0,136(1)\nmfxer 0\nstw 0,140(1)\n" +
        load(3, 0x80000038) + "lwz 6,0(3)\nlwz 7,4(3)\n" + load(3, box) +
        "stw 6,52(3)\nstw 7,56(3)\n" + load(4, stage + len(cold)) +
        "cmplw 4,6\nble 8f\nadd 6,6,7\n" + load(4, stage) +
        "cmplw 4,6\nbge 8f\n9:\nb 9b\n8:\n" +
        load(3, stage) + load(4, cold_base) + load(5, len(cold) // 4) + "mtctr 5\nli 7,0\n"
        "1:\nlwz 6,0(3)\nstw 6,0(4)\nstw 7,0(3)\naddi 3,3,4\naddi 4,4,4\nbdnz 1b\n" +
        load(3, cold_base) + load(5, len(cold) // 32) + "mtctr 5\n"
        "2:\ndcbf 0,3\naddi 3,3,32\nbdnz 2b\nsync\n" + load(3, cold_base) +
        load(5, len(cold) // 32) + "mtctr 5\n3:\nicbi 0,3\naddi 3,3,32\nbdnz 3b\nsync\nisync\n" +
        load(3, stage) + load(5, len(cold) // 4) + "mtctr 5\nli 7,0\n"
        "4:\nlwz 6,0(3)\nor 7,7,6\naddi 3,3,4\nbdnz 4b\n" +
        load(3, box) + "stw 7,40(3)\n" + load(4, len(cold) // 4) + "stw 4,44(3)\n" +
        load(4, 0x54434D31) + "stw 4,32(3)\n" + load(4, len(cold)) +
        "stw 4,36(3)\ndcbf 0,3\nsync\nlwz 0,140(1)\nmtxer 0\nlwz 0,136(1)\nmtctr 0\n"
        "lwz 0,132(1)\nmtcr 0\nlwz 0,164(1)\nmtlr 0\nlmw 2,8(1)\nlwz 0,4(1)\naddi 1,1,160\nb hardware\n"
        ".section .text.pad,\"ax\"\n.global padShim\npadShim:\n"
        "mflr 0\nstw 0,4(1)\nstwu 1,-32(1)\nstw 31,28(1)\nmr 31,3\n" + load(4, box) +
        "lwz 12,0(4)\ncmpwi 12,0\nbeq 5f\nlwz 3,4(4)\nlwz 5,12(4)\nlwz 4,8(4)\n"
        "mtctr 12\nbctrl\n" + load(4, box) + "stw 3,16(4)\nli 0,0\nstw 0,0(4)\n"
        "5:\nlwz 5,48(4)\naddi 5,5,1\nstw 5,48(4)\nmr 3,31\n" + load(4, control) +
        "li 5,12\nmtctr 5\n6:\nlwz 5,0(4)\nstw 5,0(3)\naddi 4,4,4\naddi 3,3,4\nbdnz 6b\n"
        "li 3,0\nlwz 31,28(1)\nlwz 0,36(1)\naddi 1,1,32\nmtlr 0\nblr\n")
    layout = folder / "adapters.ld"
    layout.write_text(f"hardware = {symbols['__init_hardware']:#x}; SECTIONS {{ . = {stub:#x}; .boot : {{ *(.text.boot) }} . = {pad_stub:#x}; .pad : {{ *(.text.pad) }} }}\n")
    obj, output = folder / "adapters.o", folder / "adapters.elf"
    run([ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi", "-c", asm, "-o", obj], folder)
    run([ROOT / "toolchain/ld.lld.exe", "-T", layout, "-o", output, obj], folder)
    with output.open("rb") as stream:
        elf = ELFFile(stream)
        for section in elf.iter_sections():
            if section["sh_flags"] & 2 and section["sh_size"]:
                address = section["sh_addr"]
                if not stub <= address < address + section["sh_size"] <= box:
                    raise ValueError("Private adapter exceeds its unused tail")
                offset = address - base - 0x80000
                hot[base + 0x80000][offset:offset + section["sh_size"]] = section.data()
    sample = bytearray(48)
    for pad in range(1, 4):
        sample[pad * 12 + 10] = 255
    off = control - base - 0x80000
    hot[base + 0x80000][off:off + 48] = sample
    writes = []
    for address, word in manifest["writes"]:
        offset = dol.offset(address)
        writes.append({"address": address, "before": struct.unpack_from(">I", dol.data, offset)[0], "after": word})
        struct.pack_into(">I", dol.data, offset, word)
    pad_site = symbols["read__10JUTGamePadFv"] + 0x1C
    if struct.unpack_from(">I", dol.data, dol.offset(pad_site))[0] != branch(pad_site, symbols["PADRead"]):
        raise ValueError("Retail PADRead call differs")
    struct.pack_into(">I", dol.data, dol.offset(pad_site), branch(pad_site, pad_stub))
    struct.pack_into(">I", dol.data, dol.offset(boot_site), branch(boot_site, stub))
    for address, data in sorted(hot.items()):
        dol.add(address, data, True)
    dol.add(stage, cold, False)
    for name, symbol in protected["symbols"].items():
        if symbol.get("sha256"):
            data = dol.data[dol.offset(symbol["address"], symbol["size"]):][:symbol["size"]]
            if sha(data) != symbol["sha256"]:
                raise ValueError("Private DOL changed timer bytes: " + name)
    source_iso, image = fixture / "input.iso", folder / "input.iso"
    if image.exists():
        raise ValueError("Use a fresh output folder for every runtime launch")
    shutil.copyfile(source_iso, image)
    with image.open("r+b") as stream:
        if stream.read(6) != b"GMSP01":
            raise ValueError("Expected PAL disc assets")
        stream.seek(0x420)
        dol_offset, fst = struct.unpack(">II", stream.read(8))
        if dol_offset + len(dol.data) > fst:
            raise ValueError("Private DOL exceeds reserved file space before FST")
        stream.seek(dol_offset)
        stream.write(dol.data)
    (folder / "input.dol").write_bytes(dol.data)
    (folder / "symbols.txt").write_text("\n".join(f"{address:08x} T {name}" for name, address in sorted(symbols.items())) + "\n")
    layout_source = folder / "menu-layout.cpp"
    layout_source.write_text('#define private public\n#include "susamune/menu.hxx"\n#include "susamune/settings.hxx"\nextern "C" const unsigned int menuLayout[] = {sizeof(Menu), __builtin_offsetof(Menu,mShown), __builtin_offsetof(Menu,mCurTab), __builtin_offsetof(Menu,mNumTabs), __builtin_offsetof(Menu,mTabs), __builtin_offsetof(Menu,mToastBuf), __builtin_offsetof(Settings,mValues), SETTING_SAVE_RNG_STATE};\n')
    layout_obj = folder / "menu-layout.o"
    run([ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi", "-std=c++17", "-fno-exceptions", "-fno-rtti", "-DIS_EMULATOR=1", "-DSUSAMUNE_VERSION_PAL=1", "-I", ROOT / "include", "-I", ROOT / "include/JSystem", "-c", layout_source, "-o", layout_obj], folder)
    with layout_obj.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = next(s for s in elf.get_section_by_name(".symtab").iter_symbols() if s.name == "menuLayout")
        offsets = struct.unpack_from(">8I", elf.get_section(symbol["st_shndx"]).data(), symbol["st_value"])
    creation_source = folder / "creation-layout.cpp"
    creation_source.write_text('#define private public\n#include "susamune/creation_extras.hxx"\n#include "susamune/input_display.hxx"\n#include "susamune/metadata_display.hxx"\nextern "C" const unsigned int creationLayout[] = {__builtin_offsetof(CreationExtras,mColors), sizeof(CreationExtras::mColors), __builtin_offsetof(CreationExtras,mWallkickStyle), sizeof(CreationExtras::mWallkickStyle), __builtin_offsetof(CreationExtras,mWords), sizeof(CreationExtras::mWords), __builtin_offsetof(CreationExtras,mKeyboard), __builtin_offsetof(CreationExtras,mEditMode), __builtin_offsetof(InputDisplay,mStyle), sizeof(InputDisplay::mStyle), __builtin_offsetof(MetadataDisplay,mStyle), sizeof(MetadataDisplay::mStyle)};\n')
    creation_obj = folder / "creation-layout.o"
    run([ROOT / "toolchain/clang++.exe", "--target=powerpc-gecko-ibm-kuribo-eabi", "-std=c++17", "-fno-exceptions", "-fno-rtti", "-DIS_EMULATOR=1", "-DSUSAMUNE_VERSION_PAL=1", "-I", ROOT / "include", "-I", ROOT / "include/JSystem", "-c", creation_source, "-o", creation_obj], folder)
    with creation_obj.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = next(s for s in elf.get_section_by_name(".symtab").iter_symbols() if s.name == "creationLayout")
        creation_offsets = struct.unpack_from(">12I", elf.get_section(symbol["st_shndx"]).data(), symbol["st_value"])
    result = {"cold_base": cold_base, "cold_bytes": len(cold), "cold_sha256": sha(cold),
              "stage": stage, "stub": stub, "pad_stub": pad_stub, "box": box, "control": control,
              "pad_site": pad_site, "pad_word": branch(pad_site, pad_stub), "boot_site": boot_site,
              "original_hardware_target": symbols["__init_hardware"], "menu_layout": list(offsets[:6]),
              "settings_layout": list(offsets[6:]),
              "creation_layout": list(creation_offsets),
              "retail_dol_sha256": digest(retail), "private_dol_sha256": sha(dol.data),
              **input_evidence, "retained_elf_sha256": digest(retained_elf),
              "source_iso": str(source_iso), "source_iso_sha256": digest(source_iso),
              "manifest_hook_writes": writes, "timer_symbols_verified": len(protected["symbols"])}
    (folder / "fixture.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


class Runtime(Capture):
    symbol_file, image_file = "symbols.txt", "input.iso"

    def __init__(self, dolphin, folder, receipt):
        super().__init__(dolphin, folder, folder)
        self.info = receipt
        self.pad_address = receipt["control"]
        self.callbox = receipt["box"]
        self.calls = []
        self.flows = []

    def matches_mem1(self, base):
        return self.host_read(base + self.info["pad_site"] - 0x80000000, 4, False) == struct.pack(">I", self.info["pad_word"])

    def validate_fixture(self):
        deadline = time.monotonic() + 20
        while self.read(self.callbox + 32, 4) != b"TCM1":
            self.alive(deadline)
            time.sleep(0.05)
        for base, size in self.regions():
            if size >= 0x2000000:
                offset = self.info["cold_base"] - 0x70000000
                data = self.host_read(base + offset, self.info["cold_bytes"], False)
                if data and sha(data) == self.info["cold_sha256"]:
                    self.fake = base
                    break
        if self.fake is None:
            raise ValueError("Full cold payload not found after early CPU copy")
        if self.u32(self.callbox + 40) or self.u32(self.callbox + 44) != self.info["cold_bytes"] // 4:
            raise ValueError("Early CPU readback did not verify cleared attachment staging")
        fst, fst_size = self.u32(self.callbox + 52), self.u32(self.callbox + 56)
        stage = self.info["stage"]
        if stage < fst + fst_size and fst < stage + self.info["cold_bytes"]:
            raise ValueError("Private boot staging overlaps the live FST")
        self.evidence["boot_fst_span"] = [fst, fst_size]
        self.evidence["staging_fst_disjoint"] = True
        self.evidence["cold_payload_verified_after_copy"] = True
        self.evidence["attachment_staging_cleared"] = True
        self.evidence["staging_clear_verified_before_hardware_init"] = True
        self.evidence["attachment_reused_before_host_check"] = any(self.read(self.info["stage"], self.info["cold_bytes"]))

    def state(self):
        app = self.read(self.symbols["gpApplication"], 0x48)
        director = self.u32(self.symbols["gpMarDirector"])
        return {"context": app[8], "scene": app[14] << 8 | app[15],
                "state": self.read(director + 0x64, 1)[0] if director else 0,
                "flags": 0, "stage_setup": self.read(director + 0x260, 1)[0] if director else 0,
                "frames": self.u32(self.callbox + 48)}

    def frozen(self):
        pass

    def u32(self, address):
        return struct.unpack(">I", self.read(address, 4))[0]

    def text(self, address):
        return self.read(address, 160).split(b"\0", 1)[0].decode("ascii", errors="replace")

    def call(self, name, *args):
        if name not in ("start__5ILingFiUl", "grabsInput__11CreationTabCFv") and not name.startswith(("title__", "current__13NestedMenuTab")):
            raise ValueError("Call outside bounded menu observation/entry APIs")
        if self.u32(self.callbox) or len(args) > 3:
            raise ValueError("Private callbox busy")
        address = self.symbols[name]
        self.write(self.callbox + 4, struct.pack(">4I", *(list(args) + [0] * (3 - len(args)) + [0xFFFFFFFF])))
        self.write(self.callbox, struct.pack(">I", address))
        deadline = time.monotonic() + 8
        while self.u32(self.callbox):
            self.alive(deadline)
            time.sleep(0.02)
        value = self.u32(self.callbox + 16)
        self.calls.append({"symbol": name, "address": address, "result": value,
                           "executed_in_cold_range": self.info["cold_base"] <= address < self.info["cold_base"] + self.info["cold_bytes"]})
        return value

    def feed(self, buttons=0, x=0, y=0, duration=0.10, cx=0, cy=0):
        data = struct.pack(">HbbbbBBBBbB", buttons, x, y, cx, cy, 0, 0, 0, 0, 0, 0)
        self.write(self.pad_address, data)
        time.sleep(duration)
        self.write(self.pad_address, bytes(12))
        time.sleep(0.25)

    def menu(self):
        menu = self.u32(self.symbols["gMenu"])
        if not menu:
            raise ValueError("Menu not constructed")
        _, shown, current, count, tabs, toast = self.info["menu_layout"]
        selected = self.u32(menu + current)
        return {"address": menu, "shown": bool(self.read(menu + shown, 1)[0]),
                "tab": selected, "count": self.u32(menu + count),
                "tab_object": self.u32(menu + tabs + 4 * selected), "toast": self.text(menu + toast)}

    def tab_title(self, obj):
        pointer = self.u32(obj)
        candidates = [(name, address) for name, address in self.symbols.items()
                      if name.startswith("__vt__") and address == pointer]
        if len(candidates) != 1:
            raise ValueError("Runtime tab vtable is not one named retained table: " + hex(pointer))
        class_name = candidates[0][0][len("__vt__"):]
        name = "title__" + class_name + "CFv"
        if name not in self.symbols:
            raise ValueError("Named tab title method is absent")
        return self.text(self.call(name, obj))


def exercise_creation(game):
    while game.menu()["tab"] != 5:
        game.feed(0x20)
    hub = game.menu()["tab_object"]
    if game.tab_title(hub) != "Display":
        raise ValueError("Display hub was not selected")
    game.feed(0x100)
    child = game.call("current__13NestedMenuTabCFv", hub)
    if game.tab_title(child) != "Layout editor":
        raise ValueError("Creation child was not selected")
    extras = game.u32(game.symbols["gCreationExtras"])
    colors, color_bytes, wallkick, wallkick_bytes, words, word_bytes, keyboard, mode = game.info["creation_layout"][:8]
    active = lambda: bool(game.call("grabsInput__11CreationTabCFv", child))
    # Enter each screen through the ordinary menu, then discard actual changes.
    page = 0
    for target, title, symbol, pair in ((1, "Controller inputs", "gInputDisplay", 8),
                                       (2, "Metadata", "gMetadataDisplay", 10)):
        while page != target:
            game.feed(cy=-100)
            page += 1
        game.feed(0x100)
        address = game.u32(game.symbols[symbol])
        offset, count = game.info["creation_layout"][pair:pair + 2]
        before = game.read(address + offset, count)
        game.feed(0x100)
        if not active():
            raise ValueError(title + " did not enter its editor")
        game.feed(2)
        if game.read(address + offset, count) == before:
            raise ValueError(title + " did not move its live layout")
        game.feed(0x200)
        game.feed(0x100)
        if active() or game.read(address + offset, count) != before:
            raise ValueError(title + " did not cancel and restore its layout")
        game.flows.append({"kind": "Creation editor", "title": title, "changed": True,
                           "cancel_restored": True, "frames": game.state()["frames"]})
        print(json.dumps(game.flows[-1]), flush=True)
        game.feed(0x200)
    while page != 3:
        game.feed(cy=-100)
        page += 1
    for target, title, offset, count in ((3, "Native HUD colours", colors, color_bytes),
                                        (5, "Practice feedback", wallkick, wallkick_bytes),
                                        (4, "Custom text", words, word_bytes)):
        while page != target:
            direction = 1 if target > page else -1
            game.feed(cy=-100 * direction)
            page += direction
        game.feed(0x100)
        before = game.read(extras + offset, count)
        game.feed(0x100)
        if not active():
            raise ValueError(title + " did not enter its editor")
        if target == 4:
            if not game.read(extras + keyboard, 1)[0]:
                raise ValueError("Custom text did not enter the keyboard")
            game.feed(0x100)
            game.feed(0x1400)
        else:
            game.feed(cx=100) if target == 3 else game.feed(2)
            game.feed(0x200)
        changed = game.read(extras + offset, count)
        if changed == before:
            raise ValueError(title + " editor did not change its live value")
        game.feed(0x100)
        if active() or game.read(extras + offset, count) != before:
            raise ValueError(title + " did not cancel and restore its value")
        game.flows.append({"kind": "Creation editor", "title": title, "changed": True,
                           "cancel_restored": True, "frames": game.state()["frames"]})
        print(json.dumps(game.flows[-1]), flush=True)
        game.feed(0x200)
    game.feed(0x200)
    if game.call("current__13NestedMenuTabCFv", hub):
        raise ValueError("Creation Back did not return to Display hub")


def exercise(game, creation_editors=False):
    rows = game.flows
    deadline = time.monotonic() + 75
    while game.state()["scene"] != 0xF00 or game.state()["state"] != 4:
        game.alive(deadline)
        game.feed(0x1000)
    time.sleep(2)
    game.call("start__5ILingFiUl", 132, 0)
    deadline = time.monotonic() + 180
    last = None
    while True:
        game.alive(deadline)
        state = game.state()
        phase = state["context"], state["scene"], state["state"], state["stage_setup"]
        if phase != last:
            print(json.dumps({"state": state}), flush=True)
            last = phase
        if state["scene"] == 0x102 and state["state"] == 4:
            break
        if state["context"] == 6 or state["state"] == 1:
            game.feed(0x1000)
            game.feed(0x100)
        time.sleep(0.1)
    game.feed(0x1800)
    if not game.menu()["shown"]:
        raise ValueError("Ordinary menu toggle did not open")
    for index in range(game.menu()["count"]):
        state = game.menu()
        if state["tab"] != index:
            raise ValueError("Normal shoulder navigation skipped a tab")
        title = game.tab_title(state["tab_object"])
        rows.append({"kind": "top-level", "index": index, "title": title, "frames": game.state()["frames"]})
        print(json.dumps(rows[-1]), flush=True)
        game.feed(0x20)
    game.feed(0x20)
    hub = game.menu()["tab_object"]
    if game.tab_title(hub) != "Practice":
        raise ValueError("Practice hub was not selected")
    for index, title in enumerate(("TAS projects", "Free camera", "Savestates")):
        game.feed(0x100)
        child = game.call("current__13NestedMenuTabCFv", hub)
        actual = game.tab_title(child)
        if actual != title:
            raise ValueError(f"Nested page mismatch: {actual!r} != {title!r}")
        rows.append({"kind": "nested", "index": index, "title": actual, "frames": game.state()["frames"]})
        print(json.dumps(rows[-1]), flush=True)
        if title == "Savestates":
            for label, symbol in (("Save to", "sActiveSlot__0"), ("Load from", "sLoadSlot__0")):
                original = game.u32(game.symbols[symbol])
                selected = []
                for step in range(1, 4):
                    game.feed(0x100)
                    value = game.u32(game.symbols[symbol])
                    if value != (original + step) % 3:
                        raise ValueError("Savestate selector did not follow the menu input")
                    selected.append(value)
                rows.append({"kind": "selector", "label": label, "values": selected, "restored": True})
                game.feed(cy=-100)
            game.feed(cy=-100)
            offset, setting = game.info["settings_layout"]
            address = game.u32(game.symbols["gSettings"]) + offset + setting
            original = game.read(address, 1)
            game.feed(0x100)
            changed = game.read(address, 1)
            if changed == original:
                raise ValueError("Save RNG menu setting did not change")
            game.feed(0x100)
            if game.read(address, 1) != original:
                raise ValueError("Save RNG menu setting did not restore")
            rows.append({"kind": "setting", "label": "Save RNG state", "before": original[0], "changed": changed[0], "restored": True})
        game.feed(0x200)
        if game.call("current__13NestedMenuTabCFv", hub):
            raise ValueError("Nested Back did not return to hub")
        game.feed(cy=-100)
    if creation_editors:
        exercise_creation(game)
    game.feed(0x1800)
    if game.menu()["shown"]:
        raise ValueError("Ordinary menu toggle did not close")
    frames = game.state()["frames"]
    time.sleep(1)
    if game.state()["frames"] <= frames:
        raise ValueError("Gameplay did not continue after menus")
    time.sleep(1)
    position_address = game.u32(game.symbols["gpMarioPos"])
    position = lambda: struct.unpack(">3f", game.read(position_address, 12))
    original = position()
    checksum_address = game.symbols["sPackedChecksums__0"]
    if game.u32(checksum_address):
        raise ValueError("Fresh runtime unexpectedly already has a saved state")
    game.feed(1)
    deadline = time.monotonic() + 30
    while not game.u32(checksum_address):
        game.alive(deadline)
        time.sleep(0.05)
    game.feed(x=100, duration=1.0)
    moved = position()
    distance = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
    if distance(original, moved) < 50:
        raise ValueError("Ordinary movement did not separate saved and live positions")
    game.feed(2)
    deadline = time.monotonic() + 30
    while distance(original, position()) > 5:
        game.alive(deadline)
        time.sleep(0.05)
    rows.append({"kind": "RAM save/load", "saved_position": original, "moved_position": moved,
                 "restored_position": position(), "packed_checksum": game.u32(checksum_address),
                 "scope": "One ordinary save/load and Mario position check; not whole-state byte equality or speed measurement."})
    print(json.dumps(rows[-1]), flush=True)
    if sha(game.read(game.info["cold_base"], game.info["cold_bytes"])) != game.info["cold_sha256"]:
        raise ValueError("Cold image changed during menu/save/load flows")
    game.evidence["cold_payload_verified_after_flows"] = True
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--retail-dol", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "build/timewarp-cold-cluster/emu-consolidated")
    parser.add_argument("--pinned-build", type=Path, help="Use a checked source-linked build instead of postlink artifacts")
    parser.add_argument("--creation-editors", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-cold-runtime/run1")
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to((ROOT / "build").resolve()) or folder.is_relative_to(args.fixture.resolve()):
        parser.error("Use a new private build directory")
    if folder.exists() and any(folder.iterdir()):
        parser.error("Runtime output directory must be fresh and empty")
    folder.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).read_bytes()
    (folder / "runtime-source.py").write_bytes(source)
    receipt = {"scope": "Actual IS_EMULATOR PAL menu execution after an early PPC word-copy. This does not exercise ARM V4 installation, Wii caches/BATs or hardware performance.", "script_sha256": sha(Path(__file__).read_bytes())}
    timer_before = digest(ROOT / "src/qft_timer.cpp")
    info = prepare(folder, args.artifacts.resolve(), args.fixture.resolve(), args.retail_dol.resolve(),
                   args.pinned_build.resolve() if args.pinned_build else None)
    receipt["fixture"] = info
    game = Runtime(args.dolphin, folder, info)
    receipt["runtime"] = game.evidence
    try:
        with game:
            receipt["flows"] = exercise(game, args.creation_editors)
            receipt["completed"] = True
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        receipt["flows"] = game.flows
        receipt["calls"] = game.calls
        receipt["timer_source_unchanged"] = digest(ROOT / "src/qft_timer.cpp") == timer_before
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
