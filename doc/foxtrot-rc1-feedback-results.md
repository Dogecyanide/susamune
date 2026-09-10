# RC1 feedback received

## C34FF061 — full-level TAS and Shined update

The full host suite passed 1,190 checks. Separate follow-ups passed 85 storage,
settings and translation checks, then 29 final menu checks; these overlapping
runs are not added as unique tests. Ordinary QFT source still matches its
authorized baseline. Both console and Dolphin builds passed for JP, US and PAL.

US Dolphin recorded 19 inputs through Bianco 3's actual secret portal, with the
area change after input 14. Loading kept the count fixed. Replay after manually
returning to the Beginning area crossed the portal again and matched every
fingerprint and the exact endpoint, with unchanged tape bytes. The final
shipping-source baseline `8332FAAC` repeated that result after the guide edit.
The private adapter positioned Mario before New TAS and supplied controller
samples; no warp or portal event was injected during recording or replay.
Evidence: `build/foxtrot-tas-zone-final` and `build/foxtrot-zone-runtime-proof.json`.

Both the earlier `233FBD49` and final `8332FAAC` passes exercised X-Shine on Movement
speed and Reverse sideways and found both under Quick without changing their values. Host checks
cover packed favourite persistence and old favourite mappings.

SD tape publication, reopening and failure handling are exercised by the
production client/ARM worker host fixtures. The new project format still needs
physical-console save/reboot feedback. Make new states/projects for this build;
older files remain tied to their matching build.

## AE95E374 — follow-up

The tester confirmed the third memory state now works, although saving it can
take longer, and reported that the text is readable. Keep these passes.

New reports: A+B held with D-Up fails to advance, normal sound effects are
missing while TASing, checkpoint replacement needs confirmation, and TAS
controls need inline binding plus a visible frame budget. These are the scope
of the follow-up controls update. SD project reboot is not inferred from the
third-slot report.

## C66EEB34 — controls update validation

All 1,146 host checks passed. The final two-coordinate header inset then passed
the targeted menu checks and a final-source Dolphin display/replay check. No
ordinary QFT formula, pool capacity or snapshot version changed.

US Dolphin exercised A+B+D-Up, inline bind editing/clearing, checkpoint
replacement and cancellation from the menu and shortcuts, Beginning/Continue,
both checkpoint loads, and shortcut-initiated replay. The full controls pass
used US image 58DDF5A8; the final header-only image C913103B repeated a five-frame
recording/replay with exact fingerprints and endpoint. Only the menu object
changed between them. Evidence: `build/foxtrot-tas-controls-proof`.

Loading gameplay from Sunshine's retail pause screen reproduced silent sound
effects because live JAudio category volumes remained zero. The fix restored
their original values through retail pause APIs; a saved pause stayed muted
until normal Resume. The stepped recording produced live SE requests and
nonzero DSP PCM audio. This is an emulator audio-output check, not a hardware
or music-continuity claim. Tested audio/practice/state/main/bind object hashes
match final shipping source. Evidence: `build/foxtrot-tas-audio-proof`.

## E4DE048F — 10 September 2026

The user reported that settings persist, both new camera settings work, Pinna 1
splits work, streaks appear to count correctly, and other sampled splits work.
TAS and Japanese-language checks are being handled by other testers; these are
not recorded as passes yet.

The user reproduced **State won't fit** with three PAL Delfino Plaza states.
This is a capacity refusal. The earlier JP report had successful-operation
messages disabled, so its exact cause was not observed.

Private PAL Dolphin samples of Peaceful Plaza and the Bianco-plant Plaza both
fit three distinct states using the released save policy, with only 541,997 and
551,860 bytes free respectively. These isolated default profiles did not
reproduce the user's refusal. The exact captured bytes use 15,179,899 and
15,217,187 bytes when all three are compacted with the production Deflate
codec, leaving roughly 3.6 MB free. The evidence is in
`build/state-capacity-pal/complete.json`; captures are private and are not
distributed. These are emulator and host-codec results, not Wii benchmarks.

The new retained-state fallback was then exercised against both sets of exact
Plaza captures using a host test pool 512 KiB smaller than the old policy needed.
Both third saves succeeded after re-encoding just one older state with fast
Deflate. Every restored raw byte matched; retained sidecars, identities and CRCs
were checked. This is a forced capacity-boundary test, not a claim that the
user's exact setup was reproduced. Evidence:
`build/state-capacity-pal/repacking-result.json`.

The user also reported that the separate recording/start-state/checkpoint/SD
workflow is confusing. The follow-up work replaces those separate storage steps
with named TAS projects and automatic beginning/checkpoint management.
