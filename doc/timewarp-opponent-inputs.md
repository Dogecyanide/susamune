# Online opponent inputs

MSR protocol 2 extends each pose payload from 48 to 56 bytes. The eight-byte
tail contains big-endian button bits, four signed stick axes, and two unsigned
analog triggers. The allowed GameCube button mask is `0x1f7f`; unknown bits are
rejected before publishing a remote sample. Analog A/B, local error codes and
practice-control flags are not transmitted. A full relayed pose is 136 bytes,
inside the existing 256-byte datagram and 208-byte relay-inner bounds.

The sender reads `PracticeSession::consumedInput` from the last completed
director call. `LiveRace::update` runs before `beforeDirect` clears that latch,
so the controller observation matches the current completed pose rather than
the next physical-pad sample. A frame that consumed no gameplay input sends a
neutral observation. This display never injects remote inputs into local Mario.

The receiver stores four small input observations beside its four existing
poses. Buttons and axes are held at the earlier interpolation endpoint, changing
to the next observation exactly when the pose timeline reaches it. They are not
numerically interpolated. Inputs inherit the pose's scene, ordering, visibility
and 250 ms stale checks. No matching scene, invisible pose or stale connection
means no opponent input panel.

The local Online toggle defaults to On and survives a room reset for the current
launch. The display borrows the user's input-display colours through
`drawSnapshot`, which modifies only a local copy of its layout. It occupies the
lower right inside the screen margins, with the peer name above it. Long names
shrink to remain inside the right margin. Watch mode, practice-owned controls,
stage-loader modals/results, the warp wheel, menus and Creation editors suppress
the panel.

Focused host checks cover network byte order and signed-axis extremes, reserved
button rejection, exact lengths and guards, protocol-1 rejection, input/pose
timeline alignment, staleness, scene changes and the local toggle. The actual
session tests also pass with the enlarged packet. JP/US/PAL syntax checks pass
with online enabled. Relay integration additionally requires the server's inner
protocol check to accept version 2; a version-1 server rejects the new session
before any pose is delivered. Hardware rendering remains to be tested.
