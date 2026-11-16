#ifndef SUSAMUNE_DOLPHIN_HTTP_HXX
#define SUSAMUNE_DOLPHIN_HTTP_HXX
#include "dolphin_https.h"
namespace DolphinHttp {
// The response and optional request body stay borrowed until take() completes.
bool begin(const char *path,const DolphinHttpsRequest *request,void *out,unsigned capacity);
void update();
unsigned phase();
int take(DolphinHttpsInfo *out);
void cancel();
// Releases only a transport opened here, and never a live online room.
bool close();
}
#endif
