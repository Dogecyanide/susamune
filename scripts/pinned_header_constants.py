"""Keep the new shared-header defaults local to their emitting source objects."""
from collections import Counter


NAME = ".rodata.rgb__27SusamuneFinishBreakdownInit"
SYMBOL = "rgb__27SusamuneFinishBreakdownInit"
OWNERS = {"emulator_persistence.cpp", "finish_breakdown.cpp"}
PAYLOAD = bytes((155, 220, 255, 235, 240, 250, 140, 245, 165))


def validate(elf, module, known_sections):
    sections = list(elf.iter_sections())
    matches = [(i, s) for i, s in enumerate(sections) if s.name == NAME]
    if not matches:
        return set()
    if len(matches) != 1 or module not in OWNERS or known_sections is None or NAME in known_sections:
        raise ValueError("Header constant is not a new source-local input: " + module)
    index, section = matches[0]
    if (section["sh_type"] != "SHT_PROGBITS" or section["sh_flags"] != 2
            or section["sh_addralign"] != 1 or section["sh_entsize"] != 0
            or section["sh_size"] != len(PAYLOAD) or section.data() != PAYLOAD):
        raise ValueError("Header constant immutable payload changed: " + module)
    symtab = elf.get_section_by_name(".symtab")
    definitions = [s for s in symtab.iter_symbols() if s["st_shndx"] == index
                   and s["st_info"]["type"] != "STT_SECTION"]
    if len(definitions) != 1:
        raise ValueError("Header constant has aliases: " + module)
    symbol = definitions[0]
    if (symbol.name != SYMBOL or symbol["st_value"] != 0 or symbol["st_size"] != len(PAYLOAD)
            or symbol["st_info"]["bind"] != "STB_LOCAL" or symbol["st_info"]["type"] != "STT_OBJECT"
            or symbol["st_other"]["visibility"] != "STV_DEFAULT"):
        raise ValueError("Header constant definition changed: " + module)
    incoming = {}
    for relocations in sections:
        if relocations["sh_type"] not in ("SHT_RELA", "SHT_REL"):
            continue
        if relocations["sh_info"] == index and relocations.num_relocations():
            raise ValueError("Header constant has outgoing relocations: " + module)
        symbols = elf.get_section(relocations["sh_link"])
        for relocation in relocations.iter_relocations():
            target = symbols.get_symbol(relocation["r_info_sym"])
            if target["st_shndx"] != index:
                continue
            reader = sections[relocations["sh_info"]]
            if (relocations["sh_type"] != "SHT_RELA" or relocation["r_info_type"] not in (4, 6)
                    or reader["sh_type"] != "SHT_PROGBITS" or reader["sh_flags"] not in (6, 0x206)
                    or target["st_info"]["bind"] != "STB_LOCAL"
                    or target["st_info"]["type"] not in ("STT_SECTION", "STT_OBJECT")):
                raise ValueError("Header constant has unsupported incoming reference: " + module)
            site = relocation["r_offset"]
            if site < 2 or site % 4 != 2 or site + 2 > reader["sh_size"]:
                raise ValueError("Header constant relocation site is not a code immediate: " + module)
            offset = target["st_value"] + relocation["r_addend"]
            if not 0 <= offset < len(PAYLOAD):
                raise ValueError("Header constant reference is not interior: " + module)
            key = (relocations["sh_info"], offset)
            incoming.setdefault(key, Counter())[relocation["r_info_type"]] += 1
    if not incoming or any(counts[4] != counts[6] for counts in incoming.values()):
        raise ValueError("Header constant references lack complete HA/LO targets: " + module)
    return {index}
