#pragma once
#include <Dolphin/types.h>
#include "susamune/live_draft.hxx"

class Menu;

#if TIMEWARP_LIVE_RACING
namespace LiveRace {
struct Options {
    char name[17];
    u8 serverIp[4];
    u16 port;
    u32 roomCode;
    int entry;
    u8 bestOf, episode;
    bool freeRoam, draft, setBo5;
    u8 pool;
};
struct Diagnostics {
    u32 submitted, received, accepted;
    s32 socketError;
    u16 socketSent, socketReceived;
    u8 dropped, sendErrors, receiveErrors;
    bool socketAvailable;
};
struct Status {
    const char *connection;
    const char *race;
    char peerName[17];
    u32 pingMs;
    u32 roomCode;
    s32 networkError;
    u8 localIp[4];
    u16 localPort;
    u8 localWins, peerWins;
    bool active, connected, hosting, localReady, peerReady, racing, matchDone;
    bool freeRoam, setupEditable;
    bool drafting, draftPending;
    LiveDraft::State draft;
    Diagnostics diagnostics;
};
void init();
void update();
void beforeStageSetup();
void draw(Menu *menu);
const Options &options();
bool configure(const Options &options);
Status status();
bool host();
bool join();
void disconnect();
bool ready();
bool newMatch();
bool chooseDraft(unsigned candidate);
void onILResult(int entry, s32 qf, bool eligible);
}
#endif
