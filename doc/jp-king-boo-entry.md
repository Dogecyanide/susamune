# JP King Boo entry parity

King Boo's hidden proximity helper reads joint 1's X/Z translation before the
first animation initializes the model matrices. J3DModel allocates that matrix
array without initializing it. JP's normal Sirena 5 entry leaves these words
zero; shifting the heap can leave data from the previous room there instead.
The helper then sits outside the level and its native 300-unit horizontal
distance check never accepts Mario's approach.

## Repair

`KingBooEntry::init`, called once after application initialization, checks the
JP `TBossTelesa::loadAfter` final call at `0x802D62DC` (word `0x4BD6E5D1`) and
its empty `TNameRef::loadAfter` target (`0x800448AC`, `blr`). Only that call is
redirected. The leaf shim admits scene `0x38:00` and zeros two words in joint 1:
model matrix-array offsets `0x3C` and `0x5C`. The chain is boss+0x74 -> MActor,
MActor+4 -> J3DModel, model+0x58 -> matrix array. At this call all three objects
already exist. Other matrix components and all actor fields are left alone.

This runs once during loading, not every frame. Animation later replaces the
matrix normally. No extra animation evaluation, physics, RNG call, widened
trigger, forced boss-state change or timer change is introduced. The shim
uses only volatile r0/r4 and CR0 and leaves the stack, LR, r3 and all floating
registers intact. US/PAL compile no code or storage for this repair. There is
no persistent allocation or memory-reservation change.

## Evidence

Private observations are in `build/pr67-polish/king-boo`:

- The user's clean-JP direct-entry test and Moonshine direct-entry test both
  skipped correctly. Their full Sirena 5 Moonshine route did not.
- `vanilla-history-full2` loads beach, hotel, casino and boss with native scene
  lifecycle calls. Its initial joint translation is (0,0), as is the helper's
  horizontal position.
- `moonshine-history-full1` repeats that loading sequence. The words are
  `F000000F` and `00C0F0FC`, exactly matching the failed human route. The first
  value is approximately -1.58e29, so the approach cannot reach the helper.
- `moonshine-history-integrated1` verifies the production installer, observes
  only those two words changing, and checks the original helper: outside the
  radius its nerve stays unchanged; inside it calls the native forceHide path
  and enters Hide. Both native checkHit and forceHide code match the disc.
- `scripts/test_king_boo_entry.py` executes the compiled shim across scene and
  residue cases, checks exact write/register bounds and confirms there is no
  US/PAL implementation or new persistent storage.

The room-history and radius checks are synthetic Dolphin diagnostics. Wii
confirmation and a human full-route test of the integrated repair remain
necessary. The behaviour is a retail skip; these observations do not establish
whether its original designers intended it.
