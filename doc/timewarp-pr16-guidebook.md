# PR16 guidebook presentation

The native Z-menu guidebook is the reference for decorative animation. Menu
presentation uses scoped wrappers around the existing text and rectangle
primitives; gameplay HUD drawing and the protected timer renderer remain on
their original paths. Full-screen editors retain their own canvas.

## Texture ownership

`MenuThemeAssets::get` returns a borrowed MEM1 texture for the current draw.
Do not retain that pointer across stage setup or savestate load. The game
already owns the `mGame6Data` archive buffer; checked archive bounds allow
guide textures in its unused suffix at `+0x5B000`. Option-page artwork has an
immutable CPU backup in existing MEM2 presentation scratch and is copied
into the verified MEM1 gap at `+0x48000` when required.

The allocation is explicit in `System/MarDirectorLoadResource.cpp:119`:
`new (0x20) char[0x64000]`. PAL retail instructions at `0x802AD75C` construct
that size, pass alignment 32 and store the result at director offset `0xD4`.
This is not an allocation size inferred from the observed archive files.

MEM2 backup bytes are not GPU texture storage. The upload waits for GX to
finish using the previous contents, copies into MEM1, flushes the CPU cache
and invalidates the texture cache. CPU flushing alone does not invalidate
cached GX texels. Missing assets or unavailable safe storage yield no image;
they must not cause an unchecked archive read or a new heap reservation.
Retail `TMarDirector::direct` invalidates the texture cache before our
`afterDraw` presentation; savestate restoration also invalidates it after
storing the restored heap. These cover newly captured guide textures and
cached textures restored by a state.

## Native paper and image geometry

The PAL `data/guide_en.szs` layout `guide_1.blo` supplies the missing paper
rendering rules; decoded texture pixels alone are insufficient. Its first
picture pane (BLO offset `0x50`) draws `guide_back.bti` at `(0, 0, 622, 480)`.
The texture is a **64 × 64 I4 tile**, with repeat on both axes. The pane has
binding `10`, wrap `10`, no mirror/rotation, and default white corners. In
`J2DPicture::drawFullSet`, those settings produce UVs from `(0, 0)` to
`(622 / 64, 480 / 64)`: the pattern retains its pixel scale across the page.

The pane remaps texture intensity between black RGBA `0x3C320000` and white
RGBA `0xE6E6BEFF`. Its BTI has alpha setting zero, so native
`J2DPicture::setTevMode` uses opaque alpha rather than the I4 intensity as
transparency. The equivalent single-stage paper shader is
`RGB = (60, 50, 0) * (1 - I) + (230, 230, 190) * I`, alpha 255. Stretching
one tile across the whole page, or drawing its raw grayscale values, loses
both the native grain scale and parchment colour.

Other useful native geometry:

- The cursor textures are 32 × 46. The native `cu_a`/`cu_b` panes retain
  those dimensions, use centred base position 4 and rotation 30 degrees.
  The menu's right-pointing hand deliberately rotates the texture 90 degrees
  for row selection; fit geometry must therefore use aspect ratio 46:32.
- `guide_picture_02.bti` is 176 × 152; the native detail pane is 198 × 178.
  Fitting its source aspect into the menu postcard box avoids square
  distortion.
- `option_sunglass.bti` is 100 × 36. Its menu icon needs a wide fitted
  rectangle, rather than stretching into a square.

Raw asset previews are under `build/pr15-menu-assets/guide_en` and `option`.
`build/pr15-menu-assets/guide-blo-pane-proof.json` records the parsed native
pane fields and source archive, including the original background colours.

## Native boat and hand

The boat switches between the original `guide_draw_ship_1.bti` and
`guide_draw_ship_2.bti` textures, both 96 × 72. It does not move, rotate, scale
or crossfade. The different drawings provide the apparent movement.

In `build/reference-sms/src/GC2D/Guide.cpp`:

- `load` binds pane `'13'` to `unk138` and inserts the second boat texture
  (lines 123–126); the BLO supplies the first texture.
- `linkSelect` calls `changePattern(unk138, 90, unkF0)` (line 464).
- `changePattern` updates only when the counter is divisible by the period.
  Even quotients select texture 2; odd quotients select texture 1. Both colour
  and alpha weights are either `[0, 1, 0, 0]` or `[1, 0, 0, 0]`
  (lines 496–508).
- The selected hand uses the same operation with period 45 on both cursor
  panes (lines 443–444). Its second pane is a shadow, alpha 80 and offset
  `(+7, +4)`, while the main pane has alpha 255.
- The counter advances once per `linkSelect`, resets only after exceeding
  540, and stops while the guidebook detail state is open
  (lines 491–493 and the `perform` state switch).

These are UI simulation ticks, not rendered frames.
`MarDirectorInitECT.cpp:236–238` places the guide in the `unk30` list with
`CUE_MOVE | CUE_CALC_ANIM`. `MarDirectorDirect.cpp:54–150` calls that list on
every simulation tick, including while ordinary gameplay movement is held.
`TGuide::perform` calls `linkSelect` on `CUE_MOVE` in `STATE_SELECT`.

At normal 60 Hz video output, `SMSGetVSyncTimesPerSec` returns 30 and
`direct` adds `600 / 30 = 20` to its tick budget, consuming 5 per tick.
That is four UI ticks per rendered frame, or 120 ticks per second. The boat
holds each pose for approximately **0.75 seconds**; the selected hand holds
each pose for approximately **0.375 seconds**. A once-per-render counter
would make both animations four times too slow.

The menu advances its pattern counter by the validated director `unk5C`
tick delta, accepting only deltas at most 8 and reducing the counter modulo
541. Stage changes and restored tick counters therefore do not inject a
large elapsed-time jump.

## Retail cross-check

The local decomp marks `Guide.cpp` as nonmatching, so the boat operation was
also checked in the unmodified PAL DOL at
`build/timewarp-pr10-pal-boot/retail-pal.dol`.

`linkSelect__6TGuideFv` starts at `0x801706B4`:

| Address | Observed operation |
| --- | --- |
| `0x80170C20` | Read the counter from `TGuide + 0xF0` |
| `0x80170C28` | Read the boat picture from `TGuide + 0x138` |
| `0x80170C40` | Multiply the period quotient by 90 for the boundary check |
| `0x80170C48` | Skip updates between boundaries |
| `0x801712D8`–`0x801712E8` | Increment the counter and compare against 540 |

The selected branch writes exact `0.0`/`1.0` blend weights, using constants at
`0x80409A38`/`0x80409A34`, then calls `setBlendKonstColor` (`0x802C59E0`) and
`setBlendKonstAlpha` (`0x802C5B18`). This confirms the hard texture swap and
90-update period independently of the decomp. Other regional `linkSelect`
symbols are JP `0x8023AC70` and US `0x8017A7F0`; those addresses alone are not
an additional execution test.

The PAL retail tick-rate instructions also agree with the source:
`0x802916F4` loads the numerator 600, `0x8029180C` subtracts 5 from the budget,
and `SMSGetVSyncTimesPerSec` at `0x8029FC8C` multiplies the 60.0 constant at
`0x8040DD38` by 0.5 at `0x8040DD10`. The four-tick cadence is independently
checked rather than inferred from the display's two-retrace wait.

The reference supports native paired artwork and its cadence. It does not
justify adding a bounce to every tab icon or changing gameplay animation.
Wii appearance and navigation still require the combined build's normal
visual check.
