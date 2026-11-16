#ifndef SUSAMUNE_GHOST_SIMULATION_SETTINGS_H
#define SUSAMUNE_GHOST_SIMULATION_SETTINGS_H

#define SUSAMUNE_GHOST_SIMULATION_SCHEMA 1u
#define SUSAMUNE_GHOST_SIMULATION_SIZE 64u
#define SUSAMUNE_GHOST_SIMULATION_VALUE_COUNT 47u

/* Schema-1 settings are named ordinals, not the launcher's setting IDs. */
static inline int SusamuneGhostSimulationSettingsValid(const unsigned char *p) {
    /* Starlet has spare read-only text space, but its data region is full. */
    static const unsigned char maximum[47]
#if defined(__arm__)
        __attribute__((section(".text.ghost_simulation_limits")))
#endif
        = {
        1,2,1,1,1,2,1,1,1,1,1,1,1,1,2,1,3,1,1,1,
        1,1,1,1,1,1,1,1,2,1,1,1,1,1,5,1,4,4,99,99,
        1,4,4,4,1,1,1
    };
    unsigned int i, cadence, stick;
    if (!p) return 0;
    for (i = 0; i < 47; ++i) {
        if (i == 46 && p[i] == 255) continue;
        if (p[i] > maximum[i]) return 0;
    }
    if ((p[40] && !p[0]) || p[47]) return 0;
    for (i = 56; i < 64; ++i) if (p[i]) return 0;
    cadence = ((unsigned int)p[48] << 24) | ((unsigned int)p[49] << 16) |
        ((unsigned int)p[50] << 8) | p[51];
    stick = ((unsigned int)p[52] << 24) | ((unsigned int)p[53] << 16) |
        ((unsigned int)p[54] << 8) | p[55];
    return cadence >= 0x3f800000u && cadence <= 0x43700000u && stick <= 1;
}
#endif
