#ifndef SUSAMUNE_LIVE_P2P_HXX
#define SUSAMUNE_LIVE_P2P_HXX
#include "susamune/live_transport.h"

// Serverless online play: a room code carries a player's public UDP endpoint
// (learned with STUN) and the room secret, and both players punch through
// their NATs by sending to each other's endpoint at the same time.
#ifndef LIVE_P2P_MAX_PEERS
#define LIVE_P2P_MAX_PEERS 2
#endif
namespace LiveP2P {
enum {
    // Players in one room, host included. Two today; the code, punch table,
    // roster and participant numbers (MSRHeader.participant < 4) allow four.
    MAX_PEERS = LIVE_P2P_MAX_PEERS,
    CODE_CHARS = 14,      // 70 bits in a 32-symbol alphabet without 0/O/1/I
    DISPLAY_CHARS = 17,   // CODE_CHARS plus three dashes
    PUNCH_BYTES = 12,
    PUNCH_INTERVAL_MS = 200,
    PUNCH_SLOW_MS = 1000,  // after the first 30 s of waiting
    ROSTER_ENTRY_BYTES = 8,
    // A roster lists the other joiners; one spare entry keeps the array non-empty.
    ROSTER_MAX_BYTES = PUNCH_BYTES + ROSTER_ENTRY_BYTES * (MAX_PEERS - 1),
    // 13 bits; the host's secret doubles as the session PIN. A per-console
    // secret saved in susamune.ini keeps the code stable between sessions.
    SECRET_MAX = 8191,
};
enum Role { HOST = 0, JOINER = 1 };
// Either player's code works in either direction; there is no role in it.
struct Code {
    TWLiveEndpoint endpoint;
    unsigned secret;
};
// Obfuscated, checksummed (9 bits): the IP is not readable, and typos fail the
// check. This is not encryption; the secret only keeps strangers out of a room.
bool encode(const Code &code, char *out);                // CODE_CHARS + NUL
bool decode(const char *text, Code *out);                // case/dash/space tolerant
// Dashes after every four characters; `code` may be partial. DISPLAY_CHARS + NUL.
void format(const char *code, char *out);
char symbol(unsigned index);                             // the 32 code characters

enum PeerState { EMPTY, PUNCHING, OPEN };
struct Peer {
    TWLiveEndpoint endpoint;
    unsigned lastSentMs, lastHeardMs;
    unsigned char participant, state, sent;
};
struct Punch {
    Peer peers[MAX_PEERS - 1];
    unsigned pin;
    unsigned char self;
};
void reset(Punch &punch, unsigned pin, unsigned char self);
// Returns the slot for this endpoint, adding it when there is room; -1 when full.
int add(Punch &punch, const TWLiveEndpoint &endpoint, unsigned char participant);
// Writes the next punch for slot `index` when it is due and returns its size.
unsigned due(Punch &punch, unsigned index, unsigned nowMs, unsigned char *packet,
             unsigned intervalMs = PUNCH_INTERVAL_MS);
// Host only: the other open joiners, so joiner `index` can punch them too.
// Returns the roster size, or 0 when there is nobody to forward.
unsigned roster(const Punch &punch, unsigned index, unsigned char *packet);
// True when `data` is a punch or roster packet (consumed). A matching PIN opens
// a known peer; with `adopt`, an unknown sender with the right PIN is added too.
// A roster counts only from the host once its path is open.
bool receive(Punch &punch, const TWLiveEndpoint &from, const void *data, unsigned bytes,
             unsigned nowMs, bool adopt);
bool open(const Punch &punch);
static_assert(MAX_PEERS >= 2 && MAX_PEERS <= 4, "MSRHeader.participant is below 4");
}
#endif
