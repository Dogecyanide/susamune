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

## Open: JP container ceiling (needs a decision)

The console `mod_jp.bin` is 560,640 bytes with the STUN probe and 558,176
without it. The reset-safe JP ceiling is 548,864 (`SUSAMUNE_JP_UI_OFFSET`).
PR16's JP container was 548,832. PR17's new menu features, mostly cold code,
added about 9.3 KB. US and PAL have roughly 94 KB of headroom. Options are
smaller JP feature code, JP-only exclusions or a new JP storage layout. Each
changes the product or the memory design, so none was picked here. The
emulator build is unaffected.

## Not verified

- No Wii run, and no Dolphin run of this branch.
- In builds without `TIMEWARP_LIVE_RACING`, `menuInit()` stays in
  `.foxtrot.text`; the search-reset move was linked only with online on.
- `test_mod_boot_cache.py` and 22 other unittest modules fail identically at
  `c83fadd` (for example, the boot-cache test's PPC model lacks `mr`).
