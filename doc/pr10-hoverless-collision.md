# PR10 Hoverless and collision viewer

Hoverless is a fifth IL profile (UI ID 4), with immutable rule ID 1: an
accepted retail Hover-nozzle emission disqualifies the attempt. Equipping
Hover, holding R with an empty tank, and rejected emission requests do not.
The existing retail emission observer latches Hover independently of its
preferred burst visual. Its fixed wrapper and the retail return value remain
unchanged. The latch resets before each retail director frame, while attempt
ineligibility lasts until the existing attempt reset. Changing profiles during
an attempt also revokes record eligibility.

The original four PB profiles, names, live mirror and V2 SD files keep their
layout. New capability `0x04000000` advertises the independent rule mailbox at
config `+0x1A20..+0x1C80` (608 bytes). Its PPC-only live PB array occupies
`+0x1C80..+0x1EA0` (544 bytes), below progress at `+0x2000` and after the
settings tail ending at `+0x1A20`. Request, response and values have separate
32-byte cache lines. Dolphin mirrors start at `0x71900140` and `0x719003A0`.
All MEM1/MEM2 reservations, state banks and recording limits remain unchanged.

SD alternates `moonshine_hoverless_v1_<region>_{a,b}.bin` in the existing data
directory. The checked 576-byte payload includes game, rule, version and
generation. Writes verify the new copy before advancing the active generation.
Unreadable or future files disable writes. A short write retains the previous
valid copy. Dolphin CARD V13 appends the same 576-byte payload inside its
unchanged 8 KiB sector; V12 and earlier records migrate with unset Hoverless
PBs and an inherit-selection marker. The persistence State still fits its
unchanged `0x1800` window. New writes alternate sectors as before.

Ghost wire profile 5 means Hoverless rule 1; wire profile 4 remains the
imported-library sentinel. Existing personal profiles 0–3 stay unchanged.
Personal and share files use their own `p5` directories. The recording's
starting rule occupies an existing Track padding byte, survives state prefixes,
and prevents relabelling an ordinary recording as Hoverless after changing
profiles. Accepted Hover marks its ghost assisted; incompatible rule targets
cannot contribute ghost-race credit. Generic practice statistics and gold
segments retain their existing shared history. The four-profile per-segment PB
schema is unchanged, so Hoverless has an independent overall PB and ghost
library but no fifth persisted segment-PB bank.

PR11 checks accepted Hover emission inside split capture, gold publication and
the split update itself. Retail split callbacks can run before IL eligibility is
updated, so split eligibility must not depend on the later IL callback or its
already-ineligible early return. The current Hoverless attempt loses pending
gold credit and its gold overlay; previous persisted splits/golds and the other
four profiles are unchanged. Seven native split tests cover emission at every
checkpoint and finish, no accepted emission, all ordinary profiles, prior PBs,
and the unchanged runtime memory boundaries.

PR12 replaces the original Nearby wireframe viewer with a filled World mode;
Off and Floor retain their numeric identities. Current collision coverage,
read-only admission, palette, rendering and focused evidence are documented in
[pr12-collision-world.md](pr12-collision-world.md). The original line clipper
remains available to its historical focused test, but is no longer the world
rendering path.

Focused verification includes the production SD journal, short writes and
future-rule refusal; actual ARM ghost namespace isolation; accepted-emission
observation; ghost prefix retention; and actual CARD V12/V13 migration preserving
all 544 existing profile values and other settings. The clipper is tested across
the near plane and viewport edges. All seven changed/new PPC modules passed
PAL emulator syntax checks; both launcher storage modules passed ARM checks.
Integrated protected-link checks and hardware rendering remain separate parent
task checks; host fixtures do not establish Wii rendering or timing results.
