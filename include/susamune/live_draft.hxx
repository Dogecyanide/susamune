#pragma once

#include <Dolphin/types.h>

namespace LiveDraft {

enum : u8 { PLAYER_ONE = 0, PLAYER_TWO = 1, NO_PLAYER = 0xff };
enum : u16 { NO_ENTRY = 0xffff };
enum : unsigned { CANDIDATE_COUNT = 5 };

enum Phase : u8 {
    UNINITIALIZED,
    OPENING_HOST_BAN,
    OPENING_GUEST_BANS,
    OPENING_HOST_PICK,
    IL_MATCH,
    NEED_CANDIDATES,
    COUNTER_WINNER_BAN,
    COUNTER_LOSER_PICK,
    SET_DONE,
};

struct Token {
    u32 generation;
    u32 revision;
};

// Local state, not a wire format. The caller validates catalogue/pool membership.
struct State {
    u32 generation;
    u32 revision;
    u16 candidates[CANDIDATE_COUNT];
    u16 selected;
    Phase phase;
    u8 bannedMask;
    u8 roundWins[2];
    u8 setWins[2];
    u8 bestOf;
    u8 previousWinner;
};
static_assert(sizeof(State) == 28, "Draft state must stay bounded");

Token token(const State &state);
u8 currentActor(const State &state);
bool begin(State &state, u32 generation, u8 bestOf,
           const u16 candidates[CANDIDATE_COUNT]);
bool ban(State &state, u8 actor, unsigned candidate, Token expected);
// A pick never starts gameplay; both players still need to ready up.
bool pick(State &state, u8 actor, unsigned candidate, Token expected);
// NO_PLAYER covers ties and ineligible/aborted rounds without awarding points.
bool recordRound(State &state, u8 winner, Token expected);
bool nextCandidates(State &state, const u16 candidates[CANDIDATE_COUNT],
                    Token expected);

} // namespace LiveDraft
