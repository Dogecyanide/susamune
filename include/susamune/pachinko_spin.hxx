#ifndef _SUSAMUNE_PACHINKO_SPIN_HXX
#define _SUSAMUNE_PACHINKO_SPIN_HXX

namespace PachinkoSpin {
#if defined(SUSAMUNE_VERSION_JP)
void init();
#else
inline void init() {}
#endif
}

#endif
