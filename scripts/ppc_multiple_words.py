"""Compile one mod source through assembly and fold callee-saved GPR saves.

LLVM's PowerPC backend saves r14-r31 one word at a time.  CodeWarrior, which
built the game, uses stmw/lmw for the same frame slots.  This wrapper runs the
compiler with -S, replaces the contiguous callee-saved run in the entry block
with stmw and each complete restore before a return with lmw, then assembles
the result.  Registers, slots and frame size are unchanged; only the number of
instructions differs.  Protected timer inputs and their byte-pinned anchors
are assembled from unmodified compiler output.

usage: ppc_multiple_words.py <clang++> <compiler args...> -o <obj> -c <src>
"""
import os
import re
import subprocess
import sys

# Timer source and dependency anchors are byte-compared by the pinned link.
# The -O2 gameplay codecs keep their scheduled single-word frames.
SKIP_SOURCES = {"qft_timer.cpp", "state_codec.cpp", "state_crc.cpp"}
SKIP_FUNCTIONS = {
    "drawText__4MenuFPCciiiiQ28JUtility6TColor",
    "fillBox__4MenuFiiiiQ28JUtility6TColor",
    "branchWord__FUlUl",
    "writeGameCode__FUlUl",
    "draw__10QftDisplayCFP4MenuPCc",
    "freezeRequested__15PracticeSessionFv",
    "paused__15PracticeSessionFv",
}

INSN = re.compile(r"^\t([a-z][a-z0-9.+-]*)(?:\s+(.*?))?\s*(?:#.*)?$")
MEMORY = re.compile(r"^(\d+),\s*(-?\d+)\(1\)$")
LABEL = re.compile(r'^("[^"]+"|[A-Za-z_.$][\w.$<>@]*):')
REG = re.compile(r"(?<![\w.@])(\d+)(?![\w(])")

# Instructions whose first operand is not a GPR they write.
NO_GPR_WRITE = re.compile(r"^(st\w*|cmp\w*|b\w*|mt\w*|dcb\w*|icbi|sync|isync|eieio|tw\w*|nop|crxor|creqv|cror|crclr|crset|fcmp\w*|ps_cmp\w*|psq_st\w*|stf\w*)$")


def parse(line):
    m = INSN.match(line)
    return (m.group(1), (m.group(2) or "").strip()) if m else (None, None)


def written_gpr(op, args):
    """GPR written by an instruction, -1 if unknown, None if it writes none."""
    if op is None:
        return None
    if op.startswith(("stw", "sth", "stb", "stf", "psq_st")) and "u" in op[3:]:
        m = re.search(r"\((\d+)\)", args) or re.match(r"\d+,\s*(\d+)", args)
        return int(m.group(1)) if m else -1
    if NO_GPR_WRITE.match(op):
        return None
    if op.startswith(("lf", "psq_l")):
        if "u" in op[3:]:
            m = re.search(r"\((\d+)\)", args) or re.match(r"\d+,\s*(\d+)", args)
            return int(m.group(1)) if m else -1
        return None
    if op.startswith(("f", "ps_")) and not op.startswith("fctiw"):
        return None
    m = re.match(r"(\d+)", args)
    return int(m.group(1)) if m else -1


def read_gprs(op, args):
    if op in ("mtcrf", "mtcr"):
        return {int(args.split(",")[-1])}
    if op in ("li", "lis"):
        return set()
    return {int(x) for x in REG.findall(args)}


def is_label(line):
    text = line.strip()
    return bool(text) and not text.startswith("#") and bool(LABEL.match(text))


def fold_function(body):
    """Fold one function's r<n>..r31 saves/restores.  Returns (lines, words saved)."""
    ops = [parse(l) for l in body]
    alloc = None
    for i, (op, args) in enumerate(ops):
        if op is None:
            if body[i].startswith(".LBB"):
                break
            continue
        m = re.match(r"^1,\s*-(\d+)\(1\)$", args) if op == "stwu" else None
        if m:
            alloc = (i, int(m.group(1)))
            break
        if op.startswith("b") and op != "bl":
            break
    if not alloc:
        return body, 0
    start, size = alloc
    stores = {}
    for i in range(start + 1, len(body)):
        op, args = ops[i]
        if op is None:
            if is_label(body[i]):
                break
            continue
        if op.startswith("b"):
            break
        m = MEMORY.match(args) if op == "stw" else None
        if m and int(m.group(1)) >= 14:
            reg = int(m.group(1))
            if reg in stores:
                break
            stores[reg] = (i, int(m.group(2)))
    # Callee-saved GPRs live in fixed slots: r<k> at frame - 4 * (32 - k).
    saved = {r for r, (_, off) in stores.items() if off == size - 4 * (32 - r)}
    if len(saved) < 2:
        return body, 0
    high = max(saved)
    low = high
    while low - 1 in saved:
        low -= 1
    if high - low < 1:
        return body, 0
    # stmw/lmw always run to r31.  Registers above the saved run are never
    # written here, so they store and reload their entry value, and their
    # fixed slots must be otherwise unused.
    for reg in range(high + 1, 32):
        slot = "%d(1)" % (size - 4 * (32 - reg))
        if any(written_gpr(*ops[i]) == reg for i in range(len(body))) or \
                any(o and slot in a for o, a in ops) or reg in stores:
            return body, 0
    if any(o == "stwu" and a.startswith("1,") for o, a in ops[start + 1:]) or \
            any(o and o.startswith(("stmw", "lmw")) for o, a in ops):
        return body, 0
    group = set(range(low, high + 1))
    base = stores[low][1]
    remove, replace = set(), {}
    first = min(stores[r][0] for r in group)
    if all(written_gpr(*ops[i]) not in group and written_gpr(*ops[i]) != -1
           for i in range(first)):
        remove.update(stores[r][0] for r in group)
        replace[first] = "\tstmw %d, %d(1)\n" % (low, base)
    elif high < 31:
        # lmw would reload r<high+1>..r31 from slots only stmw writes.
        return body, 0
    # Each return block: the full lwz low..31 set from the same slots.
    block = []
    for i in range(start + 1, len(body)):
        op, args = ops[i]
        if op is None:
            if is_label(body[i]):
                block = []
            continue
        block.append(i)
        ret = op == "blr" or (op == "b" and not args.startswith(".L"))
        if not ret:
            if op.startswith("b") and op != "bl":
                block = []
            continue
        loads = {}
        for j in block:
            o, a = ops[j]
            m = MEMORY.match(a) if o == "lwz" else None
            if m and int(m.group(1)) in group:
                reg = int(m.group(1))
                if reg in loads or int(m.group(2)) != base + 4 * (reg - low):
                    loads = None
                    break
                loads[reg] = j
        block_ok = loads is not None and set(loads) == group
        if block_ok:
            last, lo = max(loads.values()), min(loads.values())
            restored = set()
            for j in block:
                if j > last:
                    break
                if j in loads.values():
                    restored.add(int(ops[j][1].split(",")[0]))
                    continue
                if j < lo:
                    continue
                o, a = ops[j]
                w = written_gpr(o, a)
                if w == -1 or w == 1 or w in group or read_gprs(o, a) & restored or \
                        o.startswith("b"):
                    block_ok = False
                    break
            # The frame must stay allocated until the folded load.
            if block_ok and any(ops[j][0] in ("addi", "lwz") and ops[j][1].startswith("1,")
                                for j in block if j < last):
                block_ok = False
        if block_ok:
            remove.update(loads.values())
            replace[last] = "\tlmw %d, %d(1)\n" % (low, base)
        block = []
    if not replace:
        return body, 0
    out = [replace[i] if i in replace else line for i, line in enumerate(body)
           if i in replace or i not in remove]
    return out, len(remove) - len(replace)


def rewrite(text):
    """Fold every eligible function.  Only functions alone in their own
    -ffunction-sections section are touched: shrinking one function inside a
    shared frozen section (.foxtrot.text) would move its pinned neighbours."""
    lines = text.splitlines(keepends=True)
    out = []
    saved = 0
    section = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        sec = re.match(r'^\t\.section\t("[^"]+"|[^,\s]+)', line)
        if sec:
            section = sec.group(1).strip('"')
        elif re.match(r"^\t\.(text|data|bss)\b", line):
            section = line.split()[0]
        m = re.match(r'^\t\.type\t("[^"]+"|[^,]+),@function', line)
        if not m:
            out.append(line)
            i += 1
            continue
        name = m.group(1).strip('"')
        j = i + 1
        while j < len(lines) and not lines[j].startswith("\t.size"):
            j += 1
        body = lines[i:j]
        if section == ".text." + name and name not in SKIP_FUNCTIONS:
            body, n = fold_function(body)
            saved += n
        out.extend(body)
        i = j
    return "".join(out), saved


def quote_branch_targets(text):
    # The PowerPC operand parser takes quoted symbol names only as expressions.
    return re.sub(r'(?m)^(\t[a-z][a-z0-9.+-]*[ \t]+)("[^"\n]+")([ \t]*(?:#.*)?)$', r"\1(\2)\3", text)


def main(argv):
    compiler, args = argv[1], argv[2:]
    obj = args[args.index("-o") + 1]
    src = args[args.index("-c") + 1]
    asm = obj + ".s"
    sargs = list(args)
    sargs[sargs.index("-o") + 1] = asm
    sargs[sargs.index("-c")] = "-S"
    subprocess.check_call([compiler] + sargs)
    with open(asm, encoding="utf-8", newline="") as f:
        text = f.read()
    saved = 0
    if os.path.basename(src) not in SKIP_SOURCES and os.environ.get("SUSAMUNE_PPC_MULTIPLE", "1") != "0":
        text, saved = rewrite(text)
    text = quote_branch_targets(text)
    with open(asm, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    target = [a for a in args if a.startswith("--target=")]
    subprocess.check_call([compiler] + target + ["-c", asm, "-o", obj])
    os.remove(asm)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
