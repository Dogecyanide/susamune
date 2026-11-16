# JP Pachinko running-spin parity

PachinkoSpin preserves the retail JP running-jump quirk in scene 0x16:00.
It is not a new input rule: the original spin checker still evaluates the
original history, thresholds, last-sample exclusion and rotation direction.

## Retail cause

The clean regional disc binaries all have the same uninitialized-local defect
in TMario::checkStickRotate(int *):

| Region | Checker | changePlayerTriJump | Its inlined spin-check BL |
| --- | --- | --- | --- |
| JP | 0x80130758 | 0x80133144 | 0x80133380 |
| US | 0x80251304 | 0x80253D54 | 0x80253F90 |
| PAL | 0x80249090 | 0x8024BAE0 | 0x8024BD1C |

The checker creates a 0x30-byte stack frame but never initializes its four
words at sp+0x10, +0x14, +0x18, +0x1C. Each visited direction stores
1; the final test requires each word to equal exactly 1.

External Dolphin write watchpoints on clean JP identify the residue that
enables the Pachinko running jump. The preceding native HUD draw constructs
a J2DOrthoGraph from TGCConsole2::perform (return address 0x80206730).
J2DGrafContext::setColor leaves the opaque blend fields at context offsets
+0xB8/+0xBC/+0xC0/+0xC4 equal to [1,0,0,1]. Those bytes later alias the
running-jump checker's four words. The last stores are at
0x8003555C, 0x80035560, 0x80035574, and 0x80035578.

In the measured Moonshine build, onUpdate adds a 0x90-byte frame and the
Mario perform observer adds 0x30. The running checker consequently reads
a different location, whose four words were zero. The fix does not depend
on either wrapper's current size or an absolute stack address.

## Scope and implementation

Only JP's 0x80133380 call is redirected, after checking its original word
0x4BFFD3D9. The shim admits only:

- gpApplication.mCurrentScene == (0x16, 0);
- the original Mario actor;
- exact running state 0x04000440.

The admitted path performs the retail stwu, seeds the measured four words,
and branches to the unchanged checker at +4. Every other path branches to
the retail entry without allocating a frame or writing memory. Standing,
airborne and other native spin-check calls are untouched. The checker still
needs both missing directions; one direction alone does not qualify.

The compiled JP shim is 88 bytes and its checked installer is 92 bytes.
There is no persistent storage. US/PAL compile no allocated code or data.
Call PachinkoSpin::init() once from onAppInit; keep the shim in MEM1 within
REL24 reach of the retail call and checker. No manifest hook-table entry is
needed because the installer performs the checked write.

## Validation and limits

Private evidence is under build/pr64-pachinko-spin/:

| Run | Native history / pose | Entry words | Result |
| --- | --- | --- | --- |
| vanilla6 | Early upper-left sweep | [1,0,0,1] | spin 1, direction 3 |
| moonshine1 | Identical to vanilla6 | [0,0,0,0] | spin 0, direction 4 |
| vanilla-warm2 | Settled camera, 21 samples | [1,0,0,1] | spin 1, direction 3 |
| moonshine-fixed1 | Identical to vanilla-warm2 | [1,0,0,1] | spin 1, direction 3 |

vanilla-watch1 and vanilla-warm2 record the native last writers.
moonshine-fixed2 additionally checks the caller's resulting Mario state
and compares all 0x190 checker bytes with the retail disc: Mario enters
spin-jump state 0x895, and the entire checker remains byte-for-byte identical.

scripts/test_pachinko_spin.py compiles all three regions and executes the
linked shim's instructions across 108 scene/state/actor gate combinations.
It checks frame/register preservation, exact write bounds, no US/PAL
allocation, no JP persistent storage, and missing-direction negative cases.

The stock control loads the original JP ISO. Host-side GDB selects Pachinko
after native logo initialization and supplies PAD samples after native
PADRead; no callback or instruction patch touches the stock control's
movement, rendering or spin-check stack. The Moonshine comparator uses the
preserved runtime-pr59-world29 production fixture with its diagnostic
PAD hook restored to the original retail call. The prototype runs the
compiled production shim in unused private fixture space.

These are Dolphin proofs with synthetic stage entry, not Wii/Wii U results
or a complete Plaza-to-Pachinko route-entry test. Hardware confirmation still
needs the final integrated package, normal Pachinko entry, the upper-left
running-jump gesture, and standing/airborne/other-stage negative controls.
