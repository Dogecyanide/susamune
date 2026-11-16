# Online Mario colours

`live_colours.hxx` owns a 22-byte palette: seven RGB triples and an enable
mask. A 24-byte optional `MSR_READY` body carries subtype 36 and player index.
The existing reliable session acknowledges it; older peers ignore the unknown
subtype. Movement packets and the race protocol version are unchanged.

`live_race.cpp::serviceColours` reads `MarioColors::stageInto`, so an unfinished
editor preview is not published. Two-player sessions enqueue a changed palette
after race control traffic. Connection acceptance clears the sent latch.
For groups, `live_group.cpp` forwards palettes through the host, authenticates
the player index against the delivering link, and resends the roster palettes
on welcome/reconnection. A zero mask is meaningful: it clears custom colours.

`ghost_model.cpp::refreshColours` owns three independent caches indexed by
physical ModelSlot, not by the local player's network index. It recolours a
full-size private CMPR texture only when its source or palette changes.
Per-shape callbacks bind that texture and restore the original afterwards;
face shapes and the local Mario's material callbacks are untouched. The
existing ghost does not instantiate sunglasses or the optional Aloha shirt.

There are no new reservations. In Mario-only groups the first two atlases
reuse retired model working copies: Shadow staging on Wii, Piantissimo's
GPU-visible working resource on Dolphin. Immutable asset masters are never
written. The third atlas, or the single two-player atlas, uses the existing
attachment heap. FLUDD instances with the same source share private model
data and material display lists. Each instance retains its own matrices and
packets; animation evaluates private joints synchronously before viewCalc.
Never share the retail FLUDD joints, which gameplay continues to animate.

Stage/model replacement already quiesces old packets and waits for GX before
restoring working assets. Attachment rebuilds also wait for GX and invalidate
the texture caches before freeing their heap. Palette replacement waits for
GX before rewriting an atlas. A failed allocation leaves native rendering
intact; it must not borrow savestate, file-transfer or immutable-master space.

Checks: `test_live_colours.py`, `test_live_group.py`,
`test_live_race_lifecycle.py`, plus actual multi-model rendering. Host fixtures
test distinct textures, source immutability, callback restoration, cache reuse
and allocation failure. Network simulations cover loss, reconnect, changes,
rematches and forged player identities. Neither substitutes for Wii hardware
testing of all attachment combinations.
