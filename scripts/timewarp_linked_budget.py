"""Attribute live ELF ranges once and inspect linked timer dependencies.

Object files identify owners and relocations; only surviving final-ELF bytes
enter the budget. Shared/merged symbols and uncovered bytes stay separate.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from elftools.elf.enums import ENUM_RELOC_TYPE_PPC
import timewarp_timer_guard as timer_guard

ROOT = Path(__file__).resolve().parents[1]
RELOCATION_NAMES = {v: k for k, v in ENUM_RELOC_TYPE_PPC.items() if isinstance(v, int)}

MENU_HOT = ("drawText__4Menu", "drawChar__4Menu", "fillBox__4Menu", "fillPoly__4Menu",
            "strokePoly__4Menu", "drawPolygon__", "draw__4Menu", "update__4Menu",
            "fontSafeText__", "bgmStatsDraw__", "drawAchievementBanner__", "updateAchievementChime__")
EXTRA_COLD = ("adopt", "stage", "resetDefaults", "menuRow", "adjustMenuRow", "beginColorEditor",
              "beginOverlayEditor", "beginWordEditor", "beginKeyboard", "beginRecentIlEditor",
              "beginSavestateFeedbackEditor", "beginWallkickEditor", "beginRolloutEditor",
              "beginDustEditor", "beginPracticeDisplayEditor", "beginAchievementBannerEditor",
              "beginToastEditor", "beginPbBannerEditor", "beginFailureBannerEditor",
              "beginStageSessionEditor", "updateEditor", "updateKeyboard", "drawEditor", "drawKeyboard",
              "drawCreationKeyboard", "updateCreationKeyboard", "clampStyle", "clampWord", "copyRgb")
RECORD_COLD = ("achievement__", "achievementCount", "category", "tier", "worldName",
               "worldPBSummary", "formatCentis", "currentRegionScope", "unlockedCount", "resetProgress")
IL_COLD = ("label__", "shortLabel", "plazaStateName", "pbProfileName", "setPbProfileName",
           "copyProfileName", "cyclePbProfile", "menu", "jump", "beginsMenuGroup",
           "canChooseEpisode", "selectedEpisode", "setEpisode", "adoptEpisodes", "stageEpisodes",
           "resetEpisodeChoices", "choosesPlazaState")
LOADER_COLD = ("appendQueue", "removeQueue", "moveQueue", "clearQueue", "queueEntry", "queueCount",
               "builtinPlaylistName", "loadBuiltinPlaylist", "loadCustomPlaylist", "saveCustomPlaylist",
               "customPlaylistEntryCount", "publishPlaylistSave", "builtinContentHash", "reconcileBuiltinHashes")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def kind(section):
    if section["sh_type"] == "SHT_NOBITS":
        return "bss"
    if section["sh_flags"] & 4:
        return "code"
    return "data" if section["sh_flags"] & 1 else "rodata"


def record(symbol, module=None):
    return {"name": symbol.name, "address": symbol["st_value"], "size": symbol["st_size"],
            "section": symbol["st_shndx"], "type": symbol["st_info"]["type"],
            "binding": symbol["st_info"]["bind"], "module": module}


def object_inputs(build, region):
    objects, owners = {}, defaultdict(set)
    for path in sorted((build / f"CMakeFiles/susamune_obj_{region}.dir/src").glob("*.cpp.obj")):
        module = path.name[:-4]
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            table = elf.get_section_by_name(".symtab")
            symbols = [record(s, module) for s in table.iter_symbols()]
            definitions = defaultdict(list)
            for sym in symbols:
                if isinstance(sym["section"], int) and sym["size"]:
                    definitions[sym["section"]].append(sym)
                    if sym["binding"] != "STB_LOCAL":
                        owners[sym["name"]].add(module)
            relocations = []
            sections = {i: section.name for i, section in enumerate(elf.iter_sections())}
            for section in elf.iter_sections():
                if section["sh_type"] == "SHT_RELA":
                    relocations.extend({"section": section["sh_info"], "offset": r["r_offset"],
                                        "type": r["r_info_type"], "symbol": r["r_info_sym"],
                                        "addend": r["r_addend"]} for r in section.iter_relocations())
        objects[module] = {"sha256": sha(path.read_bytes()), "symbols": symbols, "sections": sections,
                           "definitions": definitions, "relocations": relocations}
    if not objects:
        raise ValueError("No compiled source objects")
    return objects, owners


class LinkedImage:
    def __init__(self, path, owners):
        self.symbols, self.sections, self.locals, self.globals = [], {}, {}, defaultdict(list)
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            if elf["e_machine"] != "EM_PPC" or elf["e_type"] != "ET_EXEC":
                raise ValueError("Expected final PowerPC ELF")
            for index, sec in enumerate(elf.iter_sections()):
                if sec["sh_flags"] & 2 and sec["sh_size"]:
                    self.sections[index] = {"name": sec.name, "address": sec["sh_addr"],
                                            "size": sec["sh_size"], "kind": kind(sec),
                                            "span": "upper" if sec.name.startswith(".foxtrot") else "low",
                                            "bytes": sec.data() if sec["sh_type"] != "SHT_NOBITS" else None}
            module = None
            for sym in elf.get_section_by_name(".symtab").iter_symbols():
                if sym["st_info"]["type"] == "STT_FILE":
                    module = sym.name
                row = record(sym, module if sym["st_info"]["bind"] == "STB_LOCAL" else None)
                if row["binding"] != "STB_LOCAL":
                    self.globals[row["name"]].append(row)
                elif row["size"]:
                    self.locals[(module, row["name"])] = row
                if row["size"] and row["section"] in self.sections:
                    row["owners"] = ([module] if row["binding"] == "STB_LOCAL" and module in owners["__modules__"]
                                     else sorted(owners.get(row["name"], ())))
                    sec = self.sections[row["section"]]
                    if not sec["address"] <= row["address"] < row["address"] + row["size"] <= sec["address"] + sec["size"]:
                        raise ValueError("Final symbol is outside its section")
                    self.symbols.append(row)
        self.intervals = self.partition()
        self.starts = [r["begin"] for r in self.intervals]

    def partition(self):
        result = []
        for index, section in self.sections.items():
            events = defaultdict(list)
            events[section["address"]]
            events[section["address"] + section["size"]]
            rows = [s for s in self.symbols if s["section"] == index]
            for number, row in enumerate(rows):
                events[row["address"]].append((number, True))
                events[row["address"] + row["size"]].append((number, False))
            active = set()
            points = sorted(events)
            for begin, end in zip(points, points[1:]):
                for number, add in events[begin]:
                    if add:
                        active.add(number)
                    else:
                        active.remove(number)
                candidates = [rows[n] for n in sorted(active)]
                owners = sorted({owner for row in candidates for owner in row["owners"]})
                unknown = not candidates or any(not row["owners"] for row in candidates)
                result.append({"begin": begin, "end": end, "bytes": end - begin,
                               "section": section["name"], "span": section["span"],
                               "kind": section["kind"], "owners": owners,
                               "attribution": "unknown" if unknown else "exclusive" if len(owners) == 1 else "shared",
                               "symbols": sorted({row["name"] for row in candidates})})
        return sorted(result, key=lambda row: row["begin"])

    def at(self, address):
        index = bisect_right(self.starts, address) - 1
        if index >= 0 and address < self.intervals[index]["end"]:
            return self.intervals[index]
        return None

    def resolve(self, row):
        if row["binding"] == "STB_LOCAL":
            candidate = self.locals.get((row["module"], row["name"]))
            return [candidate] if candidate else []
        return self.globals.get(row["name"], [])

    def target(self, address):
        interval = self.at(address)
        if interval:
            return {key: interval[key] for key in ("owners", "symbols", "kind", "span", "attribution")}
        names = sorted({s["name"] for rows in self.globals.values() for s in rows if s["address"] == address})
        return {"owners": [], "symbols": names, "kind": "external-retail-or-unresolved",
                "span": None, "attribution": "external"}


def module_budget(image):
    rows = defaultdict(lambda: defaultdict(int))
    for interval in image.intervals:
        owner = interval["owners"][0] if interval["attribution"] == "exclusive" else "<" + interval["attribution"] + ">"
        rows[owner][interval["span"] + "_" + interval["kind"]] += interval["bytes"]
    return {name: dict(sorted(row.items())) for name, row in sorted(rows.items())}


def linked_branches(image):
    branches, seen = [], set()
    for sym in image.symbols:
        sec = image.sections[sym["section"]]
        if sym["type"] != "STT_FUNC" or sec["kind"] != "code":
            continue
        offset = sym["address"] - sec["address"]
        for position in range(0, sym["size"] - 3, 4):
            pc = sym["address"] + position
            if pc in seen:
                continue
            seen.add(pc)
            word = struct.unpack_from(">I", sec["bytes"], offset + position)[0]
            opcode = word >> 26
            if opcode not in (16, 18):
                continue
            mask, sign = (0x03FFFFFC, 0x02000000) if opcode == 18 else (0xFFFC, 0x8000)
            displacement = (word & mask) - (sign * 2 if word & sign else 0)
            target = (displacement if word & 2 else pc + displacement) & 0xFFFFFFFF
            source = image.at(pc)
            destination = image.target(target)
            branches.append({"site": pc, "target": target, "link": bool(word & 1),
                             "conditional": opcode == 16,
                             "caller": source["symbols"], "source_owners": source["owners"],
                             "destination": destination})
    return branches


def relocation_dependencies(image, objects):
    rows, seen, unmapped = [], set(), defaultdict(int)
    for module, obj in objects.items():
        for relocation in obj["relocations"]:
            source_defs = [s for s in obj["definitions"][relocation["section"]]
                           if s["address"] <= relocation["offset"] < s["address"] + s["size"]]
            sources = [(old, linked) for old in source_defs for linked in image.resolve(old)
                       if linked["section"] in image.sections and linked["size"] == old["size"]]
            if not sources:
                unmapped[module] += 1
                continue
            target = obj["symbols"][relocation["symbol"]]
            target_defs = [target]
            if target["type"] == "STT_SECTION":
                point = target["address"] + relocation["addend"]
                target_defs = [s for s in obj["definitions"][target["section"]]
                               if s["address"] <= point < s["address"] + s["size"]]
            destinations = [linked for old in target_defs for linked in image.resolve(old)]
            destination_owners = sorted({owner for linked in destinations
                                        for owner in image.target(linked["address"])["owners"]})
            names = sorted({r["name"] for r in target_defs if r["name"]}) or [target["name"]]
            for original, linked in sources:
                site = linked["address"] + relocation["offset"] - original["address"]
                key = (site, relocation["type"], tuple(names))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"site": site, "caller": linked["name"], "source_module": module,
                             "relocation": RELOCATION_NAMES.get(relocation["type"], str(relocation["type"])),
                             "targets": names, "target_owners": destination_owners,
                             "target_addresses": sorted({r["address"] for r in destinations}),
                             "target_resolved": bool(destinations)})
    return rows, dict(sorted(unmapped.items()))


def candidate_reason(module, name, data_kind):
    if data_kind not in ("code", "rodata"):
        return None
    if module == "card_encoding.cpp":
        return "CARD encoding pilot"
    if module == "menu.cpp" and not name.startswith(MENU_HOT):
        return "Menu pages/configuration; keep primitives, font objects and live banners"
    if module == "creation.cpp" and not name.startswith("drawTextLine__8Creation"):
        return "Creation editor; keep the shared live text renderer"
    if module == "creation_extras.cpp":
        if data_kind == "code" and name.startswith(EXTRA_COLD):
            return "Editor/configuration functions; keep live HUD/restore/timer presentation"
        if data_kind == "rodata" and name.startswith(("gCreationLetters", "gCreationSymbols", "kMenuText", "targets__", "titles__")):
            return "CPU-only editor labels"
    if module == "layout_profiles.cpp":
        return "Layout profile configuration/persistence"
    if module == "settings.cpp" and not name.startswith(("gSettings", "set__", "pollSave", "affectsIlPb", "invalidatesIlAttempt", "blocksIlPb", "ilPbBlockerCount", "ilPbSafeValue", "ilPbSettingIndex")):
        return "Settings labels/configuration; keep timer-addressed owner and live rule helpers"
    if module == "records.cpp" and (data_kind == "rodata" or name.startswith(RECORD_COLD)):
        return "Achievement catalog/UI and immutable CPU tables; keep live event tracking"
    if module == "records_persistence.cpp" and not name.startswith(("update", "absorbRecords")):
        return "Record persistence management; keep idle update path"
    if module == "ghost_storage.cpp" and not name.startswith(("update", "onSavestateLoaded", "observeLoadedPlayback", "pollResponse")):
        return "Ghost file/catalog management; keep live polling and restore entry"
    if module == "tas_project.cpp" and not name.startswith(("update", "afterDraw", "onSavestateLoaded")):
        return "TAS project file/configuration helpers; keep live driver entries"
    if module == "iling.cpp":
        if data_kind == "code" and name.startswith(IL_COLD):
            return "IL picker/profile configuration; keep attempt/event logic"
        if data_kind == "rodata" and name.startswith(("kLiteral", "kFullReds", "kRegularLabel", "kRegularShort", "kGroupFirst", "kMenuGroup", "names__Q25ILing14plazaStateName")):
            return "CPU-only IL picker labels"
    if module == "stage_loader.cpp" and data_kind == "code" and name.startswith(LOADER_COLD):
        return "Playlist editing; keep live route and stage departure logic"
    return None


def relocation_candidates(image, branches, relocs):
    fixed_targets = {r["target"] for r in branches if r["source_owners"] == ["qft_timer.cpp"]}
    fixed_targets.update(address for row in relocs if row["source_module"] == "qft_timer.cpp"
                         for address in row["target_addresses"])
    fixed = [s for s in image.symbols if any(s["address"] <= a < s["address"] + s["size"] for a in fixed_targets)]
    selected = []
    for interval in image.intervals:
        if interval["attribution"] != "exclusive" or len(interval["owners"]) != 1:
            continue
        if any(interval["begin"] < s["address"] + s["size"] and s["address"] < interval["end"] for s in fixed):
            continue
        reasons = [candidate_reason(interval["owners"][0], name, interval["kind"]) for name in interval["symbols"]]
        if not reasons or not all(reasons):
            continue
        row = dict(interval)
        row["reason"] = reasons[0]
        row["phase"] = ("cpu-page-layout" if interval["kind"] == "code" and
                        any(name.startswith("draw") for name in interval["symbols"]) else "configuration-and-catalogs")
        selected.append(row)
    starts = [r["begin"] for r in selected]

    def is_selected(address):
        index = bisect_right(starts, address) - 1
        return index >= 0 and address < selected[index]["end"]

    incoming = [r for r in branches if is_selected(r["target"]) and not is_selected(r["site"])]
    outgoing = [r for r in branches if is_selected(r["site"]) and not is_selected(r["target"])]
    totals = defaultdict(lambda: defaultdict(int))
    phases = defaultdict(int)
    for row in selected:
        totals[row["owners"][0]][row["span"] + "_" + row["kind"]] += row["bytes"]
        phases[row["phase"]] += row["bytes"]
    holes = []
    for row in selected:
        if holes and holes[-1]["end"] == row["begin"]:
            holes[-1]["end"] = row["end"]
            holes[-1]["bytes"] += row["bytes"]
        else:
            holes.append({k: row[k] for k in ("begin", "end", "bytes", "span")})
    return {"scope": "Source-guided plausible candidates, not approved relocation or achieved savings. CPU page layout calls retained MEM1 rendering primitives; its latency/render-state gate is separate. All mutable data/BSS, unknown/shared bytes, hot codec/checksum/restore/hook/timer modules and directly timer-addressed symbols are excluded. Indirect calls and pointer lifetimes need further validation.",
            "gross_bytes": sum(row["bytes"] for row in selected),
            "by_phase": dict(phases), "by_module": {k: dict(v) for k, v in totals.items()},
            "intervals": selected,
            "candidate_holes": sorted(holes, key=lambda row: -row["bytes"]),
            "timer_fixed_target_symbols": [{k: v for k, v in s.items() if k not in ("section", "binding", "module")} for s in fixed],
            "incoming_direct_branch_sites": len(incoming),
            "incoming_distinct_targets": len({r["target"] for r in incoming}),
            "outgoing_direct_branch_sites": len(outgoing),
            "outgoing_distinct_targets": len({r["target"] for r in outgoing}),
            "incoming_direct_branches": incoming, "outgoing_direct_branches": outgoing,
            "gateway_scope": "Counts cover decoded direct unconditional/conditional branches, including same-module split calls. They are not a complete gateway budget: indirect dispatch, address materialization and ABI/reset constraints also matter."}


def input_section_candidates(image, objects, candidates):
    selected = {(r["begin"], r["end"]) for r in candidates["intervals"]}
    rows = []
    for module, obj in objects.items():
        for index, definitions in obj["definitions"].items():
            intervals = set()
            for old in definitions:
                for linked in image.resolve(old):
                    if linked["section"] not in image.sections:
                        continue
                    for n, interval in enumerate(image.intervals):
                        if (interval["owners"] == [module] and
                                linked["address"] < interval["end"] and
                                interval["begin"] < linked["address"] + linked["size"]):
                            intervals.add(n)
            live = [image.intervals[n] for n in sorted(intervals)]
            cold = [r for r in live if (r["begin"], r["end"]) in selected]
            if not cold:
                continue
            rows.append({"module": module, "section_index": index,
                         "input_section": obj["sections"][index],
                         "exclusive_live_bytes": sum(r["bytes"] for r in live),
                         "selected_bytes": sum(r["bytes"] for r in cold),
                         "requires_section_split": len(live) != len(cold)})
    return {"scope": "Feasibility evidence only; do not sum these rows as savings. A shared/global definition can associate multiple input sections with the same linked range.",
            "sections": rows}


def analyze(build, region):
    path = build / f"susamune_{region}.o"
    objects, owners = object_inputs(build, region)
    owners["__modules__"] = set(objects)
    image = LinkedImage(path, owners)
    branches = linked_branches(image)
    relocs, unmapped = relocation_dependencies(image, objects)
    sections = [{k: v for k, v in row.items() if k != "bytes"} for row in image.sections.values()]
    budget = module_budget(image)
    if sum(sum(row.values()) for row in budget.values()) != sum(row["size"] for row in sections):
        raise ValueError("Budget does not cover each allocated byte exactly once")
    edges = defaultdict(lambda: {"direct_branches": 0, "object_relocations": 0})
    for branch in branches:
        key = (tuple(branch["source_owners"]), tuple(branch["destination"]["owners"]))
        if key[0] != key[1]:
            edges[key]["direct_branches"] += 1
    for row in relocs:
        if row["target_owners"] != [row["source_module"]]:
            edges[((row["source_module"],), tuple(row["target_owners"]))]["object_relocations"] += 1
    timer_branches = [r for r in branches if r["source_owners"] == ["qft_timer.cpp"] and r["destination"]["owners"] != ["qft_timer.cpp"]]
    timer_relocs = [r for r in relocs if r["source_module"] == "qft_timer.cpp" and r["target_owners"] != ["qft_timer.cpp"]]
    timer = [r for r in image.symbols if r["owners"] == ["qft_timer.cpp"]]
    candidates = relocation_candidates(image, branches, relocs)
    return {"region": region, "elf": str(path.resolve()), "elf_sha256": sha(path.read_bytes()),
            "object_sha256": {name: obj["sha256"] for name, obj in objects.items()},
            "sections": sections, "module_exclusive_bytes": budget,
            "relocation_candidates": candidates,
            "candidate_input_sections": input_section_candidates(image, objects, candidates),
            "retained_transport": {"mod_bin_bytes": (build / f"mod_{region}.bin").stat().st_size,
                                   "jp_immutable_prefix_limit": 0x86000,
                                   "headroom_to_jp_prefix_limit": 0x86000 - (build / f"mod_{region}.bin").stat().st_size,
                                   "scope": "Moving an initialized byte from MEM1 to uncompressed retained cold code does not reduce serialized image size. New gateways/descriptors still consume transport capacity; the JP prefix limit applies to JP with its translation staging."},
            "shared_groups": [r for r in image.intervals if r["attribution"] == "shared"],
            "intervals": image.intervals,
            "dependency_edges": [{"sources": list(key[0]), "targets": list(key[1]), **value} for key, value in sorted(edges.items())],
            "timer_dependencies": {"direct_branches": timer_branches, "object_relocations": timer_relocs,
                                   "last_protected_symbol_end": max(s["address"] + s["size"] for s in timer),
                                   "protected_symbols": [{k: v for k, v in s.items() if k not in ("section", "binding", "module")} for s in timer]},
            "unmapped_object_relocations": unmapped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=ROOT / "build/baseline-console")
    parser.add_argument("--regions", nargs="+", choices=("jp", "us", "pal"), default=("jp", "us", "pal"))
    parser.add_argument("--target", choices=("console", "emu"), default="console")
    parser.add_argument("--output", type=Path, default=ROOT / "build/timewarp-linked-budget/receipt.json")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / "build").resolve()):
        parser.error("Receipts must remain in the current checkout's ignored build directory")
    baseline = timer_guard.BASELINE
    timer_guard.verify(json.loads(baseline.read_text()), args.build, args.target, args.regions)
    receipt = {"scope": "Final linked allocated bytes counted exactly once. Shared/merged ownership and gaps are not assigned as module savings. Object relocations identify dependencies but discarded/unmapped sites are excluded from linked counts. Indirect runtime calls/data flows still require source audit.",
               "timer_guard": {"baseline_sha256": sha(baseline.read_bytes()), "target": args.target,
                               "regions": args.regions, "source_symbols_scratch_unchanged": True},
               "script_sha256": sha(Path(__file__).read_bytes()), "regions": []}
    for region in args.regions:
        row = analyze(args.build, region)
        receipt["regions"].append(row)
        print(json.dumps({"region": region, "allocated_bytes": sum(s["size"] for s in row["sections"]),
                          "candidate_gross_bytes": row["relocation_candidates"]["gross_bytes"],
                          "candidate_phases": row["relocation_candidates"]["by_phase"],
                          "exclusive_code_rodata": sorted(((name, sum(n for field, n in sizes.items() if field.endswith(("_code", "_rodata"))))
                                                           for name, sizes in row["module_exclusive_bytes"].items()), key=lambda item: -item[1])[:18]}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Receipt: {args.output.resolve()}")


if __name__ == "__main__":
    main()
