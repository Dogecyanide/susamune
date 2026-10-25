# PR12 free-camera rendering alignment

Retail `TMarDirector::direct()` draws the scene prepared by the previous call, then advances simulation and calls preEntry to prepare the following frame. J3D models bake the view into their prepared matrices, while flags and some water/effect paths use the draw-time view directly. Advancing Freecam before the previous scene is drawn gives those paths different views.

Freecam input is now queued before direct and consumed once after movement on the last simulation tick, before preEntry. The queued eligibility permits only the borrowed frozen state 12, with the same stage/camera ownership checks. Inactive camera, modal UI, missing input and invalid controller samples do not move the camera. Normal gameplay and simulation cadence are unchanged.

The original practice text reserves 1,124 zero bytes at the old camera-input position to retain timer dependency addresses. These bytes have no runtime work. Timer sources, symbol bytes, dependency anchors and hook writes must still pass the existing protected link.

Overlays separately retain the first main-camera view/projection of each director call. Later preparation and restoration cannot change the displayed frame's collision/marker projection. Overlay clipping uses that projection, and successful savestate loads invalidate it. No camera fields are retained across stage setup.

Focused controls tests exercise draw-before-prepare order, one update per final tick, borrowed pause eligibility, stale owner and inactive controls. Source checks are not Wii visual confirmation; pan past Pinna flags/fountains and other direct-drawn effects on hardware.
