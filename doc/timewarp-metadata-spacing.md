# Prototype 17: metadata value spacing

Value gap controls the space after the colon in standard metadata labels, from
0 to 32 pixels (default 7). It applies to horizontal and vertical layouts.
Custom formats continue to use their literal spacing.

Stable value widths keep the next field stationary as numbers change, but the
unused digit width now follows the number. It no longer pushes a small number
away from its label. Compact widths remove that unused space entirely. Field
gap still controls the spacing between horizontal cells; row gap and column
wrapping keep their existing behavior.

The optional value uses metadata style presence bit 14 and `reserved0[4]`.
The style remains version 2 and 832 bytes. Old configs without the bit retain
the default; Wii persists `value_gap` in the existing regional metadata
section, and Dolphin and layout profiles carry the existing complete style
block. The invisible space retains its original character-colour slot.
Logical menu rows 0–19 retain their identities; Value gap is appended at 20.

Focused checks execute the production horizontal/vertical layout, optional
field adoption/staging and ARM INI parser/emitter. Cases cover zero/default/max
gap, short and long labels, all supported font-size endpoints, changing digit
width, stable/compact packing, hidden fields, wrapping, old presence masks,
invalid values and independent character colours. Existing editor
cancellation and layout capture/apply checks pass. JP console and PAL emulator
metadata objects compile without increasing a memory reservation.
