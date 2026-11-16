## Known savestate bugs 

- ~~Crash when loading on blue save screen after collecting shine~~
- ~~Timer in piantissimo levels etc. does not save and restore~~
- ~~Goop on the ground of the level is not saved and restored.~~ Not a real bug, just a misconfigured Dolphin emulator setting.
- ~~Crash during shine spawn?~~ Inconsistent. Pianta 3 still breaks on console only.
- ~~Crash when loading during death~~ 
- Delfino Piranha Plant #1 (bianco hills) crash: invalid read from 0x61f9f244, pc = 0x800bc614. Only on emulator for some reason?
- FLUDD sounds break when loading after shine spawn. Might not be fixable reasonably. Sort of inevitable since we don't completely save/restore audio state. Can also just reload the level.

## Scratch

- [ ] probably have a separate way to control default settings rather than autosaving? and rather than pressing a button to just save the current
    - A bit problematic to deal with because we _sorta_ need two different settings structs, and I dont want that, so we have to be more clever
- [ ] Input tracing feature. Needs planning.
- [ ] Switch everything to a single Clang compiler (based on the kuribo tree) that does PowerPC and ARM to simplify dependencies.
- [ ] QFT doesnt pause on shine get grab when no shine get animation is on (maybe just my qft settings? probably not)
- [ ] Chatgpt critical review that codes have been implemented accurately
- [ ] update readme its not just savestates anymore. update credits to people who made the codes
- [ ] sound fix (warspyking)
- [ ] intermittent crash?? only happened once, with the 64KiB thing
- [ ] Fast text broken on US (cant reproduce..)
- [ ] write faq note about the read only sd card
## Future ghost work

- [ ] Look into action state recording for ghosts and possibly more.

### Ghost viewer interoperability (optional for 3.0.0)

PR47 implements opt-in V10 context, pre-setup RNG and stage ages, losslessly
packed once-per-input camera yaw, settings snapshots, omission/restore markers,
and synthetic endpoints. Normal V9 remains the default until the site supports
V10. See `pr47-ghost-viewer-handoff.txt`. Full per-QF logging, action/velocity
streams and portable starting-state attachments remain follow-up work.


Triaged against PR46 source on 2026-10-26 from the supplied
`handoff-to-moonshine-dev-1.md` and `handoff-update-2026-10-26.md`.
These are follow-up requests, not release gates. The viewer's NB6 rolling-block
and floating-island examples are reported observations, not reproductions made here.

- [x] **First priority: pre-construction RNG per stage load.** V9 currently records the MSL seed at the first retained pose of segment 0 (`ghost.cpp::appendSample`, provenance `SUSAMUNE_GHOST_RNG_FIRST_POSE`). It does not capture the pre-load seed or later segments. Latch the seed before any relevant constructors or RNG-dependent resource setup, and associate it with the correct stage generation/segment. Audit `onSetup` and earlier loading before choosing a hook; do not label the existing first-pose value as a stage-load seed. Preserve what RNG-control settings actually applied.
- [x] **First priority: stage age at each segment's first real sample.** `startEpochSamples` anchors only the first segment to QF zero. Capture a stage-local movement count with explicit units and sample phase, independent of adjusted QFT and synthetic anchors. Audit `unk58`/`unk5C`, pause, intro, slowdown and regional timing; `mTickBudget` is a remainder/budget, not elapsed stage time. The viewer reports an approximately 21-frame NB6 secret offset; do not hardcode that offset. A seed and one counter are eight raw bytes per segment before flags/schema overhead.
- [ ] **Exact steering camera yaw.** Keep the existing sparse rendered-camera track for visual playback. Add the signed camera angle consumed by Mario (candidate `gpCamera->mAngleYaw` at +0x258) with explicitly defined before/after-update timing. Start by measuring once-per-input-frame yaw plus camera mode; if insufficient, record each actual movement tick with its count. Do not assume every region/frame has four ticks. Verify the handoff's sine-table precision claim against retail/decomp before defining the schema.
- [ ] **Gameplay settings provenance.** The ghost header has a profile and run flags, not a complete simulation-settings snapshot. Define a stable, versioned subset for Fast text, RNG overrides and other behaviour-changing options. Record changes during a run or explicitly mark the simulation context incomplete; a start snapshot alone cannot describe later toggles. Do not serialize raw append-order setting IDs as a portable contract.
- [ ] **Input gap detection.** Input records already carry QF stamps; capture runs after the director and QFT update, and the format records capacity truncation. Add a source-frame/tick sequence or explicit omission reason to distinguish unexpected lost records from pauses, transitions and deliberate suppression. Preserve the existing last-tick QF alignment rather than changing old timestamps.
- [ ] **Savestate-start/continuation provenance.** `SUSAMUNE_GHOST_RUN_SAVESTATE_USED` is defined, but the current restore path writes ASSISTED/TAS without distinguishing savestate use. Distinguish a genuine missing start state from a restored recording that retains its opening input/pose prefix. A full savestate or reconstruction attachment is a separate, larger feature; exact live heap bytes are not automatically portable to the external viewer.
- [ ] **Optional desync observations and synthetic endpoint markers.** Record action (`mStatus`), forward speed and vertical speed (12 bytes per input frame), possibly a stable floor-actor identity rather than a pointer. At 30 records/s, 12 bytes costs about 21.1 KiB/minute before compression, per stored track; budget RAM and file storage separately. Explicitly identify a held/interpolated terminal pose (`finishTrackAt`) and synthetic initial anchors so the viewer does not infer gameplay samples from duplicate coordinates. This also informs the existing ghost-takeover/action-state investigation.

Any format change needs coordinated updates to the PPC reader/writer, Wii and
Dolphin storage validators, host tools, website and viewer. V9's segment metadata
validator requires later-segment reserved words to be zero: do not silently reuse
them under V9. Keep older ghosts readable and report unavailable reconstruction
metadata honestly. Define flags for unknown values and capture phase before adding
fields; precise provenance matters more than an apparently plausible value.


## Dolphin storage

- [ ] Offer named offline storage banks for libraries larger than one virtual card; each active regional card still has its 16 MiB / 127-file limit.
- [ ] Investigate a larger native storage interface only if standard Dolphin adds one; no resident companion or custom emulator is assumed.
