# Timer colour controls and outline

Colour preset is the first colour row (after Appearance when available).
C-stick up/down follows the displayed row order; left/right previews Sunset,
Ocean, Rainbow, Blend ends, or One colour. Current colours means no preset has
been applied in this edit. Browsing keeps the original first/last colours for
Blend ends and One colour until a manual HSL edit starts a new selection.
Native timer presets fill the two digit groups and separators, leaving TIME
and the background streak unchanged. Keep, Cancel and Reset retain their
existing confirmation and input ownership.

The native timer outline is texture data, not a separate pane. PAL retail
`data/game_6_en.szs` contains RGB5A3 `coin_number_0..9.bti`,
`coin_number_colon.bti` and `time_text.bti`: opaque black outlines surround
yellow/white interiors. For example, number 0 has 48 opaque black texels;
TIME has 152. J2DPicture interpolates its black/white material endpoints
using texture RGB. Setting both endpoints to the requested colour erases
those outlines; setting only white cannot turn the yellow interior blue.

Custom now uses the texture's red intensity for all three colour channels,
with a zero black endpoint and the chosen white endpoint during each picture
call. `native_hud_color.cpp` runs only inside the existing successful layout
draw scope. It temporarily wraps the checked, loaned picture vtable, restores
each black endpoint immediately, and restores the vtable before layout ends.
The protected `native_timer_layout.cpp` retains its exact frozen source hash.
This keeps the
outline, antialiasing and shading for every chosen hue. Texture alpha and
the material's alpha endpoints are unchanged. A scoped drawSelf wrapper
borrows TEV swap table 1 and stage 0's texture swap, then restores the exact
previous selections. It reads the retail GX shadow at `teva[0]` (0x170) and
`tevKsel[2..3]` (0x1B8/0x1BC), changing only the swap fields through GX APIs.
Original appearance retains its prior tint behavior.

Validation: 17 focused Creation/editor/draw cases passed, including preset
navigation, endpoint preservation, both timer digit groups, cancel/reset,
black/shaded/full-intensity material samples, mixed Original/Custom panes,
nondefault incoming swap state, and complete pane restoration. The extended
native draw ABI audit passed against retail JP, US and PAL DOLs; all three
regions compiled the changed PPC units. No timer counting code, pinned timer
baseline, texture allocation, saved colour layout, or reservation changed.
The shared editor adds a 12-byte endpoint cache. Visual console confirmation
is still needed; these checks do not claim a Wii rendering run.
