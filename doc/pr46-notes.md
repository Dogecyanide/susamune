# PR46 camera paths and guidebook polish

Free camera now has a Camera path page: add up to 16 views, select/go to/replace/delete a view, set its arrival time (0.5–60 seconds), choose smooth or linear easing and loop. Position, yaw, pitch and field of view are captured. Opening the menu holds playback; leaving the area clears the path. Paths are session-local, not exported. The existing free-camera render/update ordering is retained. The 460-byte scalar path uses a compile-checked 512-byte unused suffix of the existing ghost-water reservation; particle capacity and all reservations are unchanged.

Get ghosts is displayed first, without changing storage selection IDs or file identities. Root guidebook pages gain a heading and light one-pixel separators; their shared sidebar layout gives the hand its own parchment gutter. Dense setting/editor pages retain their existing row layout.

Dolphin storage research: GCI Folder still allocates a standard card BAT and rejects individual saves above 2043 blocks. It cannot become an unrestricted host folder through a larger setting. Current EXI devices do not include an SD adapter. USB Gecko would require a separate process. The AGP EEPROM interface is too small; raw-card addressing alone does not provide a supported large filesystem or solve the emulated write-speed limit. Named offline banks are a practical larger-library option, with one card active at a time. No storage configuration or existing user files were changed for this investigation.

Primary sources inspected 2026-10-26:
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/GCMemcard/GCMemcardDirectory.cpp
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/EXI/EXI_Device.h
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/EXI/EXI_DeviceMemoryCard.cpp
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/EXI/EXI_DeviceAGP.cpp

Validation: all six regional console/emulator builds and their 96 protected timer symbols pass. Ten focused camera/search tests, 20 boot transport tests (one legacy skipped fixture) and five menu transport tests pass. Standard Dolphin JP confirms actual path interpolation/endpoints, pause during menus, looping/stopping, editing and area clearing, with screenshots of the guidebook and Ghosts page. PAL production boot and guidebook layout were also visually checked, including navigation onto Get ghosts. Actual JP containers restore exact MEM1/menu bytes through the production word-only installer, including reset reinstall and adjacent guards. No live network or storage-service behaviour was changed or reaccepted in this pass.

Boot transport now optionally uses an MSL5 branch-normalized LZ4 stream when smaller. Only relative linked PPC branches are normalized, by their segment-relative byte offset. Both byte and ARM word-only decoders reverse it after the full stream is decoded, so LZ4 history remains filtered throughout decoding. MSL4 remains accepted. New packages require their matching boot.dol; older launchers reject the new stream safely. The JP Wii container is 649,376 bytes, below the unchanged 651,264-byte ceiling. No runtime allocation changed.
