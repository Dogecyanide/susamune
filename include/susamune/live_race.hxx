#pragma once
#include <Dolphin/types.h>
#include "susamune/live_draft.hxx"

class Menu;

#if TIMEWARP_LIVE_RACING
namespace LiveRace {
#if IS_EMULATOR
enum { LOCAL_PORT = 0 };      // A second Dolphin on this PC needs its own port.
#else
enum { LOCAL_PORT = 48222 };  // A fixed port keeps the public mapping stable between tries.
#endif
struct Options {
    char name[17];
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
    // Wii network as last seen: NET_OFF, NET_WAITING (no address yet), NET_UP or NET_FAILED.
    u8 net, waitedS;           // waitedS: seconds from Create/Join until the address was known
    u8 forwarded;              // packets the ARM kernel took from the PPC send ring this attempt
    bool trouble;              // the last attempt failed; the tab shows these lines
    u8 ip[4];                  // last local address, kept after disconnect
    u16 port;
};
enum { NET_OFF, NET_WAITING, NET_UP, NET_FAILED };
struct Status {
    const char *connection;
    const char *race;
    const char *hint;          // Room-code help or why a direct connection failed.
    char code[20], friendCode[20]; // XXXX-XXXX-XXXX-XXXX while connecting, else empty
    char peerName[17];
    u32 pingMs;
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
// Takes the friend's room code; returns null or the reason it was refused.
const char *enterCode(const char *text);
void disconnect();
bool ready();
bool newMatch();
bool chooseDraft(unsigned candidate);
void onILResult(int entry, s32 qf, bool eligible);
}
#endif
