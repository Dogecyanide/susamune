#ifndef SUSAMUNE_GHOST_CAMERA_HXX
#define SUSAMUNE_GHOST_CAMERA_HXX
#include <Dolphin/types.h>
#include <Dolphin/MTX.h>
#include "susamune/ghost_camera.h"

namespace GhostCamera {
struct View { f32 position[3], rotation[4], fovy; };
void init();
void beginFrame();
void restore();
void onStageSetup();
bool captureView(View *out);
bool renderMatrices(Mtx view, Mtx44 projection);
void reset(void *poseBank);
void capture(void *poseBank, u32 qf, u8 segment);
void trim(void *poseBank, u32 endQf, u16 segments);
u32 prefixSize(const void *poseBank);
void *prefix(void *poseBank);
const void *prefix(const void *poseBank);
bool evaluate(const void *poseBank, u32 qf, u8 segment, View *out);
bool encode(const View &view, u32 qf, u8 flags, SusamuneGhostCameraSample *out);
void decode(const SusamuneGhostCameraSample &sample, View *out);
void matrix(const View &view, f32 out[3][3]);
}
#endif
