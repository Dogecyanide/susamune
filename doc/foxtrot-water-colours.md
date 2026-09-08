# Sprayed-water colour scope

`WaterColors` reads the Creation editor's `FluddColors::WATER` and
`WATER_HIGHLIGHT` targets. Original bypasses all colour writes. Custom changes
only RGB during drawing and restores the exact previous RGBA bytes before
returning to the caller. Movement, water consumption, particle generation,
lifetimes and transparency remain retail.

The implementation follows the pinned Sunshine decompilation at
`a56e1cf00289fc6467af7d2c32ed428b44d2d2f8`:

* [ModelWaterManager.cpp](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/Player/ModelWaterManager.cpp):
  palette element zero colours normal water. Elements one through three are
  Yoshi juice and remain untouched. Model-water offsets `0x5D20` and `0x5D24`
  are the two additive highlight colours; the single highlight target retains
  their separate brightness levels. The wrapper handles draw cues `0x8` and
  `0x80`; mixed movement/view cues finish before lending the draw palette.
* [SplashManager.cpp](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/Player/SplashManager.cpp):
  the spray's impact splashes have a separate colour at `0x63C`.
* [WaterGun.cpp](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/Player/WaterGun.cpp),
  [EmitterViewObj.cpp](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/System/EmitterViewObj.cpp),
  and [JPAEmitter.hpp](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/include/JSystem/JParticle/JPAEmitter.hpp):
  all nozzle outlet mist uses effect `0x10D`, whose `TInfo` array is at particle
  manager offset `0x50`. Each record is 16 bytes; the observed retail capacity
  is 32. The wrapper checks the count, FLUDD owner range and emitter-manager
  identity, skips duplicate pointers, and changes only global primary and
  environment colours at emitter offsets `0x180` and `0x184`.
* [JPADraw.cpp](https://github.com/doldecomp/sms/blob/a56e1cf00289fc6467af7d2c32ed428b44d2d2f8/src/JSystem/JParticle/JPADraw.cpp):
  drawing samples those global colours, so no simulation callback or persistent
  particle edit is needed.

All three managers use the verified ninth word of their retail vtable for
`perform`. Installation replaces that word only if it still names the expected
retail function. The wrappers call the original function directly. These
vtables are outside savestate destinations, avoiding per-object callback
registries or restore-time ownership repair. No additional BPS hook sites are
required.

This colours the model-water stream, its highlights, impact splashes and
FLUDD-owned nozzle mist. Ocean and world-water rendering use other paths.
Yoshi mode bypasses the custom water effects.

Validation: `scripts/test_water_colors.py` exercises the production scopes,
Original, exact RGBA restoration, mixed cues, Yoshi exclusion, foreign emitter
exclusion, duplicate emitters, capacity bounds, emitter replacement during
calculation, repeated installation and stale-stage drawing. The three regional
retail DOLs independently confirmed the vtable entries; the private address
report is `build/water-colour-audit/retail-layout.json`. Live appearance testing
is recorded separately with the integrated build.
