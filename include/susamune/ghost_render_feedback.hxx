#pragma once

// Retail GPU feedback consumers; addresses identify observations, never call targets.
#if defined(SUSAMUNE_VERSION_JP)
#define MS_FEEDBACK_WATER_SITE 0x801fabf0u
#define MS_FEEDBACK_CAMERA_SITE 0x80359ca4u
#define MS_FEEDBACK_CAMERA_TAIL "0x80359ca8"
#define MS_FEEDBACK_SILHOUETTE_SITE 0x800c2d0cu
#define MS_FEEDBACK_SILHOUETTE_TAIL "0x800c2d10"
#elif defined(SUSAMUNE_VERSION_US)
#define MS_FEEDBACK_WATER_SITE 0x801a90acu
#define MS_FEEDBACK_CAMERA_SITE 0x8002a11cu
#define MS_FEEDBACK_CAMERA_TAIL "0x8002a120"
#define MS_FEEDBACK_SILHOUETTE_SITE 0x8022795cu
#define MS_FEEDBACK_SILHOUETTE_TAIL "0x80227960"
#elif defined(SUSAMUNE_VERSION_PAL)
#define MS_FEEDBACK_WATER_SITE 0x801a1934u
#define MS_FEEDBACK_CAMERA_SITE 0x8002a1d4u
#define MS_FEEDBACK_CAMERA_TAIL "0x8002a1d8"
#define MS_FEEDBACK_SILHOUETTE_SITE 0x8021f8b0u
#define MS_FEEDBACK_SILHOUETTE_TAIL "0x8021f8b4"
#endif
extern "C" void gFeedbackCamera();
extern "C" void gFeedbackSilhouette();
extern "C" void gFeedbackWater();
