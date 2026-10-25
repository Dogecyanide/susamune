# Ghost attachments after the first online Wii test

The October 13 PAL/JP test exposed three separate limitations: missing nozzle
details, a static mounted Yoshi, and the broad R+A spray rendered as a narrow
stream. These are visual paths; they must not run retail actor movement, water
emission, sound, collision responses or RNG.

## Current bounded fixes

`ghost_model.cpp` now distinguishes the normal nozzle's eight-key animation
table from the secondary nozzles' five-key tables. In the normal table indices
2/3 are swap animations, while steady firing/retraction use 5/6. The trigger
nozzles retain firing/retraction indices 2/3. The private backpack uses its
retracted handle for a secondary nozzle.

The turbo propeller is rotated by retail `RotateCtrl`, rather than by its BCK.
The private ghost nozzle intentionally has no live-Mario callbacks, so its
propeller previously remained still. Its private joint now receives a bounded,
deterministic phase from the ghost's recorded time while firing. Pause and seek
do not use an independent clock. This reconstructs spinning; it does not record
the original propeller acceleration/coast phase.

The Yoshi attachment previously called model calculation without applying a
Yoshi animation. Basic mounted motion now reverses the rider mapping in
`TMario::setAnimation` and evaluates the corresponding Yoshi BCK at the recorded
rider phase. Calculation uses the existing private model. Each shared joint's
transform, callback and both calculator words is saved, temporarily replaced,
and restored synchronously before returning. Retail head/tongue callbacks are
not invoked, and there is no new persistent allocation or reservation.

The approximation cannot invert information that the rider mapping discarded:
left/right sidesteps share one rider ID, firing can override several actions
with the same rider ID, and walk/run blending and independent tongue animation
are absent. Basic running, jumping, fluttering and idle now have appropriate
skeletal motion; this is not exact Yoshi replay.

Rocket and turbo are already admitted by the observation hooks, sample
validator and model selection. The actual PAL ISO has an 8-joint, 10,784-byte
rocket BMD and a 6-joint, 10,272-byte turbo BMD, both inside current bounds.
Their BCK joint counts match their BMDs. No additional rocket-specific rendering
or capture failure has been proved. A console comparison of both nozzles is
still needed; do not describe the whole rocket report as resolved by these
changes.

## Broad R+A spray and future exact observations

Retail names the special R+A emission `TNozzleDeform::mBomb`. Its
`TNozzleTrigger::movement` checks a new A press while R is held; the accepted
emission then uses that sub-nozzle's directional spread, particle count, power
spread and size parameters. V6 records only nozzle identity, whether an actual
emission was accepted, origin, aim and power. The ghost's fixed small scatter
therefore cannot distinguish this burst from a normal spray.

A minimal extension can mark accepted burst emission with one new mode bit,
and read immutable burst parameters from the corresponding retail sub-nozzle
when rendering. It must be captured at the accepted emission hook, not inferred
from held inputs. Exact directional-spread values would instead need a
quantized observation. The current eight-byte FLUDD structure has three spare
mode bits, but current V6 validators deliberately reject them. A new recording
version and matching PPC/ARM/host validators are required before storing a new
meaning; old V6 recordings cannot acquire information they never captured.

Exact basic Yoshi animation needs the Yoshi BCK index and its own phase (five
bits plus twelve phase bits suffice), with additional blend/upper-body data for
walk/run and tongue fidelity. Extending every input sample would consume up to
108,000 extra bytes for three bytes per sample at ten minutes. Prefer an audited
pose extension or conditional packing that preserves the existing ten-minute
duration and all MEM1/MEM2 reservations. Live packets can carry the same semantic
observations once their protocol is versioned; packet growth does not authorize
growing the recording banks.

## Evidence

The local `build/reference-sms` sources used are `Player/WaterGun.cpp`,
`Player/Yoshi.cpp`, `Player/MarioDraw.cpp`, and the J3D joint/model traversal.
Actual PAL `data/mario.szs` and `data/yoshi.szs` were inspected read-only.

Six focused executable host checks exercise shared-joint restoration during
private calculation, malformed animation/joint rejection, nozzle table choice,
basic rider mapping, turbo phase/idle behavior and backpack animation choice.
JP, US and PAL production compilation flags accept the modified source.
The root build still has to check the final protected link/budget, and these
changes have not been observed on Wii hardware.
