#ifndef SUSAMUNE_DOLPHIN_ENTROPY_HXX
#define SUSAMUNE_DOLPHIN_ENTROPY_HXX
#include "dolphin_https.h"
namespace DolphinHttps { const DolphinHttpsApi *api(); }
namespace DolphinEntropy {
bool begin();
void update();
// 1 waits, 0 returns a fresh seed, negative reports failure. No token is logged.
int take(void *out);
}
#endif
