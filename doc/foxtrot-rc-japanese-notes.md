# Japanese translation reference for FOXTROT RC

Inspected September 9, 2026. The user subsequently approved implementation;
the current implementation is described below. The source research remains
useful for attribution and future translation review.

## Current implementation

`data/japanese_ui.tsv` retains the 1,022-entry Task Edition catalogue and adds
FOXTROT navigation and practice/SD workflows. The supplied Language Amendment
Proposal's 26 wording changes are applied to presentation strings only. Stable
setting/bind IDs, INI keys, PB identities and achievement conditions are unchanged.
The first asset contains 1,340 entries and 763 glyphs in 86,176 bytes; the generator
reports current measurements when the catalogue changes.

The JP game renderer uses a four-shade, 16-pixel subset of the Apache-licensed
Droid Japanese font shipped with Dolphin. An 8 KiB MEM1 texture cache expands
glyphs for GX; a completed-GX barrier protects each cache wrap. The original
1.18 MiB IPL-font retention code is not reused. US/PAL compile out the renderer.
Missing translations use the English string. Some new diagnostic and dynamically
composed text remains English and needs later language review.

On Wii, `ja_ui.bin` occupies immutable staging offsets `[0x84000,0x9F000)`
(`0x91EC3000..0x91EDE000`). The JP file packer and loader enforce the lower
`0x84000` mod-file ceiling before loading it. The loader invalidates the asset
header on every boot, then validates the complete header, CRC, tables and bounds.
The kernel only reads the staged mod prefix and writes the model vault at
`+0x9F000` onward. Warm reset preserves both prefixes. No state slot, codec
workspace, attachment heap or timer scratch is borrowed.

On Dolphin, the JP BPS stores an additional raw 108 KiB disc extent at `0x004AA8C0`,
immediately following the existing 640 KiB DOL extent. This lies inside a retail
file already relocated in full. No new DOL section or FST entry is needed. The
renderer reads bounded chunks through retail `DVDReadPrio` into its existing
8 KiB cache before using that cache for glyphs, then scalar-copies into
`0x71C00000..0x71C1B000`. Validation failures retain English rendering. This
immutable fake-memory range is outside the three-state pool and other assigned
windows. The supported translated emulator package is the JP BPS/ISO; an extracted
DOL alone lacks the raw disc asset.

The independent private DVD proof read a 32-byte marker at this exact disc offset
after `initialize()`, copied it through MEM1 into fake memory, and verified PPC
readback. Native tests exercise all catalogue lookups, corrupt and malformed
assets, English fallback, glyph expansion and cache barriers. Final game and
launcher screenshots and Wii testing are separate release checks.

## Located source

The requested **V2.0.3 Task Edition** is in the local worktree
`C:/Users/Dogec/.codex/worktrees/13fa/susamune`, on
`codex/v2.0.3-task-edition`. The branch itself still points to the ordinary
V2.0.3 commit `9cf2f94`; the translation is in **uncommitted files** in that
worktree. Checking out the branch elsewhere will therefore miss it.

Useful files there:

- `data/task_jp_ui.tsv`: 1,022 English/Japanese entries.
- `scripts/gen_task_jp_ui.py`: validates format arguments, Shift-JIS glyphs,
  duplicate keys and hash collisions, then generates a compact lookup table.
- `src/task_jp_text.cpp`: text lookup with English fallback.
- `src/task_jp_font.cpp`: keeps the game's decoded Japanese IPL font alive.
- `launcher/loader/data/font_task_ja.zip` and `OFL-NotoSansCJK.txt`: the launcher
  font subset and its license.
- `scripts/check_task_jp_font.py`: checks launcher font coverage.
- `README_TASK_EDITION_JA.md` and `doc/v2.0.3-task-edition-*-ja.md`: Japanese
  documentation and the intended hardware checks.

The old catalog successfully regenerates: 16,558 bytes of deduplicated text
plus 8,176 bytes of eight-byte lookup records. The launcher font contains a
198,896-byte `font.ttf` (165,812 compressed bytes). Its checker passes the 42
Japanese characters used by the old launcher and metadata. This is a source
validation result, not evidence that all menus passed a hardware test.

The public [upstream releases](https://github.com/panther03/susamune/releases)
list ordinary V2.0.3 “Ghosts of Delfino.” A public Task Edition release or branch
was not verified; the local worktree above is the concrete translation source.

## Original reuse assessment

Use the catalog and font checks as a starting point after the English UI,
splits and achievements settle. Compare current English strings against the
old catalog, keep useful translations, and have new terminology reviewed by
a Japanese-speaking runner. Keep persistent setting/bind IDs and file formats
independent of the displayed language.

Do not merge the old implementation wholesale. It is **GMSJ01 only** and its
font preservation reserves `0x120F00` bytes (1,183,488 bytes) immediately below
the configuration block. That placement overlaps FOXTROT's current state pool
and codec workspace. Decide the supported disc regions and give any persistent
font an explicitly audited location before porting the renderer. A glyph subset
was selected to reduce this cost, as described above. The launcher font and the
game font remain separate systems.

The source worktree includes the project's GPLv3 license. Its launcher subset
is identified as Noto Sans Mono CJK JP under SIL Open Font License 1.1; retain
its font notices and license when packaging it. Noto's primary
[font license](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)
documents those terms. The game font is loaded from the user's console/game
environment; the old source does not supply it as a distributable font asset.

Check Japanese glyphs, line wrapping, controller symbols, save-name editing,
the launcher guide, and font survival across stage changes/reset/state loads
on the final RC. The old font checker explicitly leaves Homebrew Channel's
own metadata font to Wii testing.
