# PR17 JP size pass

PR17 with the STUN probe built a 560,640-byte console `mod_jp.bin`. The JP
reset-safe ceiling is 548,864 bytes (`SUSAMUNE_JP_UI_OFFSET` 0x86000), so it was
11,776 bytes over. US and PAL were well under their 651,264-byte ceiling. This
pass gets JP under the ceiling without dropping features, adding a JP-only cut,
changing text, growing a reservation or changing a format.

## Where the bytes were

Breakdown of the 560,640-byte JP container before the pass:

| Part | Bytes | Stored as |
| --- | ---: | --- |
| Two hot MEM1 segments | 336,106 | LZ4 quick (about 0.6 of raw) |
| Cold XIP image at 0x91E3F0C0 | 211,744 | raw: every cold byte costs one container byte |
| Menu-code extension, writes, header | about 12,790 | quick |

Before the pass, JP MEM1 had only 483 bytes free, so there was no room to pull
cold code back into compressed MEM1. A duplicate-body scan of the cold image
found only about 1.5 KB that could be merged, excluding the gates. Help text
in MEM1 compresses to roughly half its size. Reaching the target with
shortened text alone would have meant rewriting most of the menu help.

The biggest fixed cost was in the function frames. LLVM's PowerPC backend
saves and restores r14-r31 one `stw`/`lwz` at a time. A large menu function
spends 18 words on the prologue and another 18 on each return block.
CodeWarrior, which built the game, uses `stmw`/`lmw` for the same slots, and
Broadway runs them natively in big-endian mode.

## Technique 1: fold callee-saved saves into stmw/lmw

`scripts/ppc_multiple_words.py` is the compile rule for the mod objects
(`CMAKE_CXX_COMPILE_OBJECT` in `CMakeLists.txt`). It works in four steps:

1. Run the same clang command with `-S` instead of `-c`.
2. In each eligible function, replace the entry-block run of callee-saved
   `stw rK, frame-4*(32-K)(1)` with a single `stmw rLow, base(1)`, placed where
   the first of those stores was.
3. Replace each complete matching `lwz` restore set before a `blr` or tail
   branch with a single `lmw`, placed where the last of those loads was.
4. Assemble the result with the same compiler and target.

The registers, stack slots, frame size, calling convention and code order are
all unchanged. Only the instruction count changes. The rewrite stays
conservative:

- **Which functions it touches:** only a function that sits alone in its own
  `.text.<name>` section. Functions in the shared frozen `.foxtrot.text`
  sections are left alone, because shrinking one of them would move its pinned
  neighbours, including timer dependency anchors.
- **Protected code:** `qft_timer.cpp`, the -O2 `state_codec.cpp` and
  `state_crc.cpp`, and the seven code anchors of the timer baseline keep the
  compiler's own output.
- **Saves:** the save is folded only if no saved register is written before
  that point.
- **Restores:** a restore block is folded only if it reloads the complete run
  from the same slots and the frame is still allocated. Nothing between those
  loads may read a register that has already been restored, write a saved
  register or r1, or branch.
- **Partial runs:** some functions save a run that stops below r31, such as
  r23-r30. `stmw`/`lmw` always continue to r31. These functions are folded only
  when r31 is never written in the function, its fixed slot is otherwise
  unused, and the prologue was folded too. In that case r31 stores and
  reloads its own entry value.
- **Mixing:** a block that fails the checks keeps its single-word `lwz`s. Those
  read the same slots that `stmw` wrote, so folded and unfolded blocks mix
  safely.
- **Quoted names:** quoted branch targets, such as names containing `<f>`, are
  wrapped as `("name")` so the PowerPC assembler parser accepts them.

Validation:

- With folding off (`SUSAMUNE_PPC_MULTIPLE=0`), all 94 JP objects built through
  assembly match the direct `-c` objects. Sections, bytes, relocations and
  symbols are identical.
- `scripts/test_ppc_multiple_words.py` covers the fold and all of its refusal
  cases. It also compiles a sample through the real toolchain and checks for
  `stmw` and `lmw`.
- All six pinned links (console and emulator, JP/US/PAL) still report 96 timer
  symbols, 5 string atoms, 9 anchors and 34 hook writes identical, and
  "source, 96 symbols and fixed scratch unchanged".
- About 630 functions in the JP image now use `stmw`/`lmw`, 174 of them in the
  cold image.

| JP console | Before | After folding |
| --- | ---: | ---: |
| Container | 560,640 | 549,856 (-10,784) |
| Cold image | 211,744 | 206,560 (-5,184) |
| Menu-code extension | 15,680 | 14,720 (-960) |
| MEM1 free | 483 | 16,415 |

Most of the MEM1 gain comes from suffix recovery. Shrunk own-section rows give
their tails back to the pinned allocator.

## Technique 2: use the recovered MEM1 the PR16 way

Cold bytes are stored raw, while MEM1 bytes compress. PR16 kept new code in
recovered MEM1 holes for the same reason. The following functions return to
`RETAIN_MEM1_CONSOLE_FUNCTIONS`:

| Functions | JP container |
| --- | ---: |
| `OnlineTab::draw` (on cold since a13246e) | -928 |
| Menu search: `searchEntry`, `drawSearch`, `MenuSearch::matches`, `MenuSearch::contains` | -1,376 |

`OnlineTab::update` stays cold. Its cold selector is audited under
`state_quick_replay.cpp`, and retaining it fails the inventory check.

## Result

| Console | Container | Ceiling | Headroom | MEM1 free |
| --- | ---: | ---: | ---: | ---: |
| JP | 547,552 | 548,864 | 1,312 | 6,843 |
| US | 544,000 | 651,264 | 107,264 | 20,630 |
| PAL | 543,456 | 651,264 | 107,808 | 20,737 |

| Emulator | mod | MEM1 free |
| --- | ---: | ---: |
| JP | 527,616 | 28,082 |
| US | 524,224 | 42,237 |
| PAL | 524,160 | 42,232 |

No user-visible text changed. Nothing was removed.

## Options not taken

- **Shorten menu help text:** about 21 KB of 40-80 character help strings live
  in MEM1. Halving them would save roughly 5 KB, but it is a large UX change
  and is no longer needed.
- **Retain more cold functions in JP MEM1:** this would give more JP headroom,
  but it uses MEM1 that the Online redesign may need.
- **Fold frames inside `.foxtrot.text`:** this would need the pinned link to
  move whole owner partitions and re-prove the anchors. Not attempted.
