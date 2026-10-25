"""Extract checked ghost model masters from the user's own clean disc."""
import mmap
import re
import struct
import zlib

from inspect_rarc_asset import disc_files, decode_yaz0, rarc_files
from mod_transport import ROOT, shared_define


def asset(name):
    return shared_define("SUSAMUNE_GHOST_" + name, "ghost_model_asset.h")


def memory(name):
    return shared_define("SUSAMUNE_" + name, "mem2_map.h")


def copy_spans():
    # Reuse the two former fake-VMEM model heaps, never snapshot/tape storage.
    result = []
    layout = (ROOT / "include/susamune/mem2_map.h").read_text().replace("\\\n", " ")
    for kind, heap in (("SHADOW", "MODEL"), ("PIANTA", "SECONDARY")):
        size = asset(kind + "_ASSET_BUFFER_SIZE")
        if size > memory("GHOST_" + heap + "_HEAP_SIZE"):
            raise ValueError("Ghost master exceeds its existing heap span")
        definition = re.search(r"^#define SUSAMUNE_GHOST_" + heap +
                               r"_HEAP_PPC_BASE\s+\(SUSAMUNE_(GHOST_\w+_PPC_BASE)\s*\+\s*"
                               r"SUSAMUNE_(GHOST_\w+_OFFSET)\)", layout, re.M)
        if not definition:
            raise ValueError("Unrecognized model heap mapping: " + heap)
        bank, offset = definition.groups()
        result.append((memory("DOLPHIN_" + bank) + memory(offset), size))
    return result


def checked(data, kind, suffix):
    if len(data) != asset(kind + "_" + suffix + "_SIZE") or zlib.crc32(data) != asset(kind + "_" + suffix + "_CRC32"):
        raise ValueError("Unexpected retail ghost resource: " + kind + " " + suffix)
    return data


def extract(iso):
    output = bytearray()
    with iso.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        files = disc_files(disc)
        for kind, archive, bmd_path in (("SHADOW", "mare6", "kagemario/default.bmd"),
                                       ("PIANTA", "mare4", "map/map/pad/monteman_model.bmd")):
            offset, size = files["data/scene/" + archive + ".szs"]
            resources = rarc_files(decode_yaz0(disc[offset:offset + size]))
            bmd = checked(resources[bmd_path], kind, "BMD")
            payload = bmd
            if kind == "SHADOW":
                payload += checked(resources["kagemario/kagemario_scroll.btk"], kind, "BTK")
            header_size = asset("MODEL_ASSET_HEADER_SIZE")
            header = struct.pack(">IHH6I", asset(kind + "_ASSET_MAGIC"), asset("MODEL_ASSET_VERSION"),
                                 header_size, 1, header_size + len(payload), header_size,
                                 len(bmd), zlib.crc32(payload), 0)
            output.extend((header + payload).ljust(asset(kind + "_ASSET_BUFFER_SIZE"), b"\0"))
    if len(output) != sum(size for _, size in copy_spans()):
        raise ValueError("Ghost master payload size differs")
    return bytes(output)
