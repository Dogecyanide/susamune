#ifndef MOONSHINE_GHOST_RUN_FLAGS_H
#define MOONSHINE_GHOST_RUN_FLAGS_H
// Stable run attributes. MSGT provenance validates their recorded history separately.
#define SUSAMUNE_GHOST_RUN_ASSISTED          0x00000001u
#define SUSAMUNE_GHOST_RUN_SAVESTATE_USED    0x00000002u
#define SUSAMUNE_GHOST_RUN_FAST_FORWARD_USED 0x00000004u
#define SUSAMUNE_GHOST_RUN_INCOMPLETE        0x00000008u
#define SUSAMUNE_GHOST_RUN_CUSTOM_ROUTE      0x00000010u
#define SUSAMUNE_GHOST_RUN_TAS               0x00000020u

static inline int SusamuneGhostRunFlagsValid(unsigned int flags) {
    return !(flags & SUSAMUNE_GHOST_RUN_TAS) ||
           (flags & SUSAMUNE_GHOST_RUN_ASSISTED);
}

#endif
