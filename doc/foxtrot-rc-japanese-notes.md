# Japanese translation reference for FOXTROT RC

Inspected September 9, 2026. Research only; no Japanese runtime or launcher
translation has been enabled in FOXTROT.

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

## Reuse at RC

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
is worth investigating to reduce this cost; it has not been implemented or
measured here. The launcher font and the game font are separate systems.

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
