# Working on Moonshine

Start with [the subsystem map](doc/architecture.md), then the relevant header.
`AGENTS.md` contains additional porting and hardware constraints. Older PR notes
are investigation history; current source and shared headers define the contract.

## Get a build working

1. Install Git LFS and obtain the repository's toolchain/LFS assets.
2. Run `python setup_venv.py`. Use that virtualenv's Python for all scripts below.
3. Run `python scripts/developer_check.py`. It reports missing build dependencies
   without modifying the checkout or downloading anything.
4. Build all three regions, for both environments. From PR27 onward there is one
   release command; do not copy another `package_prNN.py`.

```text
python scripts/release_prerelease.py configure --prototype 27
python scripts/release_prerelease.py build --prototype 27 --target all
python scripts/release_prerelease.py package --prototype 27 --summary "Safe race starts and draft prompts"
```

Use `--cmake /path/to/cmake` if CMake is not on PATH, and `--jobs N` to choose
parallelism. Trees are `build/pr27-console` and `build/pr27-emu`; package output
is create-only. The packager requires `doc/pr27-testing.txt` and
`doc/pr27-next-steps.txt`. Future prototype numbers use the same command.
Previous numbered packagers remain archived for reproducing their releases.

Build receipts hash current sources and verify all protected timer symbols,
strings, dependencies and hook writes. Any edit after a build invalidates its
receipt: rebuild before packaging. Never copy an old mod binary to make a
package pass. Dolphin BPS export is still a separate existing pipeline in
`scripts/package_timewarp_dolphin.py`; this command packages the Wii release.

Clean regional disc dumps are required for Dolphin export/runtime validation,
not supplied by this repository. Configure `SMS_ISO` for the region being
exported. Ship source-free patches, never game ISOs or extracted retail assets.

## Make a change

* Find the owning subsystem below before editing `main.cpp` or `menu.cpp`.
  Keep game effects in the feature owner and presentation in the menu.
* State the invariant in a short header comment: who owns the data, when it is
  valid, and what invalidates it. Explain hardware footguns, not obvious syntax.
* Keep numeric setting/bind IDs append-only. Check actual capacity first; a
  spare enum number does not imply spare persistent storage.
* Use the shared wire/file headers on both sides of a mailbox. Validate external
  lengths, versions, required features and checksums before publishing data.
* Do not expand a memory reservation to solve a link failure. Read
  `include/susamune/mem2_map.h` and the pinned-link receipt. New cold functions
  require explicit ownership in `scripts/pinned_cold_extensions.py`.
* Never update the protected timer baseline just to make a build pass. Any
  intended timing change needs a separate decision and regional evidence.
* For game struct offsets, consult the SMS decomp and all three regional maps.
  An address or struct layout that works on JP does not establish PAL safety.

## Test the affected contract

Run from the repository root with `scripts` on `PYTHONPATH`. On Windows:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'scripts'
python -m unittest scripts.test_live_race_match scripts.test_live_group scripts.test_online_menu_routes
```

The subsystem map names focused suites. Several native fixtures use the bundled
Windows host compiler and load generated DLLs; they are not portable Linux tests.
Use a writable TEMP directory. Socket tests need real loopback access. Do not
describe a skipped compiler/socket test as passing.

Evidence has three distinct levels:

| Evidence | Establishes | Does not establish |
|---|---|---|
| Host regression | Protocol, formats, ownership, state transitions | Wii timing or GPU behavior |
| Patched Dolphin runtime | Boot, real rendering, hooked game paths | Wii network smoothness or capture-card behavior |
| Wii test | Actual hardware behavior for the tested setup | Untested regions/player counts |

For a release, retain the build/source receipts, ZIP readback, Dolphin export
checks and SD readback. Use the verified ZIP for installation, preserve unrelated
SD files, and back up replaced files. See `AGENTS.md` for the required SD layout.

## Report a bug so someone else can reproduce it

Include prototype number, JP/US/PAL, Wii or Dolphin version, stage/episode and
practice profile, exact steps, relevant settings/binds, expected/actual behavior,
and any crash log. For online add player count, host device, which side has the
problem, same-network versus internet, and the connection diagnostics. Include
the build receipt when available. Report a rare issue as unconfirmed until it
has been reproduced; preserve the last known working package.
