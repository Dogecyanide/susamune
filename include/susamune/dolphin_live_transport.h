#ifndef SUSAMUNE_DOLPHIN_LIVE_TRANSPORT_H
#define SUSAMUNE_DOLPHIN_LIVE_TRANSPORT_H
#include "susamune/live_transport.h"
#include "susamune/mem2_map.h"

#define TW_DOLPHIN_LIVE_BASE 0x71901000u
#define TW_DOLPHIN_LIVE_MAGIC 0x4d444c31u
#define TW_DOLPHIN_LIVE_ABI 1u

typedef struct {
    unsigned generation, issued, magic, abi, gameVersion, instance, heartbeat, bytes;
} TWDolphinGame;
typedef struct {
    unsigned generation, issued, instance, epoch, heartbeat, reserved[3];
} TWDolphinHost;
typedef struct __attribute__((aligned(32))) {
    TWDolphinGame game;  /* PPC writer. */
    TWDolphinHost host;  /* Companion writer. */
    TWLiveMailbox wire;
} TWDolphinLive;

typedef char tw_dolphin_live_size[(sizeof(TWDolphinLive) == 2784) ? 1 : -1];
typedef char tw_dolphin_live_owners[(sizeof(TWDolphinGame) == 32 &&
    sizeof(TWDolphinHost) == 32 && __builtin_offsetof(TWDolphinLive, host) == 32 &&
    __builtin_offsetof(TWDolphinLive, wire) == 64) ? 1 : -1];
typedef char tw_dolphin_live_alignment[(TW_DOLPHIN_LIVE_BASE % 32 == 0) ? 1 : -1];
typedef char tw_dolphin_live_gap[(TW_DOLPHIN_LIVE_BASE >=
    SUSAMUNE_DOLPHIN_STATE_STAGING_PPC_BASE + SUSAMUNE_STATE_STAGING_SIZE &&
    TW_DOLPHIN_LIVE_BASE + sizeof(TWDolphinLive) <=
    SUSAMUNE_DOLPHIN_STATE_POOL_EXTRA_PPC_BASE) ? 1 : -1];
#endif
