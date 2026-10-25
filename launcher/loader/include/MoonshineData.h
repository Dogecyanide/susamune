#ifndef MOONSHINE_LOADER_DATA_H
#define MOONSHINE_LOADER_DATA_H

#include "ff.h"

const char *MoonshineDataErrorOperation(void);
const char *MoonshineDataErrorPath(void);

FRESULT MoonshineDataPrepare(const char *device);

#endif
