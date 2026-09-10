#ifndef SUSAMUNE_GHOST_CLOCK_H
#define SUSAMUNE_GHOST_CLOCK_H

struct SusamuneGhostClock {
    unsigned int serial;
    int liveQf;
    unsigned int omittedQf;
    bool ready;
};

static inline void SusamuneGhostClockObserve(SusamuneGhostClock *clock,
                                            unsigned int serial, int liveQf,
                                            bool held) {
    if (liveQf < 0) return;
    if (!clock->ready || clock->serial != serial || liveQf < clock->liveQf) {
        clock->omittedQf = 0;
        clock->serial = serial;
        clock->ready = true;
    } else if (held) {
        clock->omittedQf += static_cast<unsigned int>(liveQf - clock->liveQf);
    }
    clock->liveQf = liveQf;
}

static inline int SusamuneGhostClockMap(const SusamuneGhostClock *clock,
                                       int liveQf) {
    if (!clock->ready || liveQf < 0) return liveQf;
    return static_cast<unsigned int>(liveQf) < clock->omittedQf
        ? 0 : liveQf - static_cast<int>(clock->omittedQf);
}

#endif
