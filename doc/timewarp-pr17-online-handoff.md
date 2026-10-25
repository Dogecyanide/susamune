# PR17 online branch handoff

Branch `grok/v3.0.0-pr17-online` starts at `c83fadd`.

## Fixed so the pinned console link completes in all regions

- New inline-function tables in `menu.cpp`/`tas_menu.inc` get their own
  `.foxtrot.rodata.<name>` sections. They previously joined the frozen mixed
  `.foxtrot.rodata` input, which ownership cannot split.
- `GradientMotion::phase` no longer needs libgcc's `__umoddi3`.
- The menu-search reset moved from `Menu::Menu()` to `menuInit()`, so the
  protected QFT draw calls keep their targets.
- `searchActive()` is always inlined; it left the cold inventory.
- `OnlineTab::draw` returned to the console cold set, as the Online update
  method did earlier. JP needed 4,254 more MEM1 bytes than were available.
- `link_mod.mem2_hex_define` is importable by the pinned linker again.

The timer, string-atom, anchor and hook protections (96/5/9/34) hold in every
console and emulator receipt.

## JP container ceiling (resolved)

The reset-safe JP ceiling is 548,864 bytes (`SUSAMUNE_JP_UI_OFFSET`). The JP
size pass (`032fe86`, `979567f`) folds callee-saved register runs into
`stmw`/`lmw` and keeps the Online draw and menu search in console MEM1. See
`timewarp-pr17-size-pass.md`.

## Online is peer-to-peer

The relay client is gone. Players swap 16-character room codes and connect
directly by UDP hole punching. See `timewarp-pr17-p2p-online.md` for the tab,
the code format, the punching design, the one-code findings and the remaining
four-player work.

Current containers (console / emulator), all with 96/5/9/34:

| | JP | US | PAL |
| --- | --- | --- | --- |
| Console | 547,072 | 543,232 | 542,720 |
| Console MEM1 bytes free | 7,308 | 21,092 | 21,199 |
| Emulator | 527,872 | 523,328 | 522,944 |

JP has 1,792 bytes of container headroom left.

## Not verified

- No Wii run, and no Dolphin run of this branch. Direct play has been
  exercised only by host-side models and the Dolphin companion on loopback.
- In builds without `TIMEWARP_LIVE_RACING`, `menuInit()` stays in
  `.foxtrot.text`; the search-reset move was linked only with online on.
- `test_mod_boot_cache.py` and 22 other unittest modules fail identically at
  `c83fadd` (for example, the boot-cache test's PPC model lacks `mr`).
