#include <susamune/live_draft.hxx>

namespace LiveDraft {
namespace {

bool validCandidates(const u16 *candidates) {
    if (!candidates) return false;
    for (unsigned i = 0; i < CANDIDATE_COUNT; ++i) {
        if (candidates[i] == NO_ENTRY) return false;
        for (unsigned j = 0; j < i; ++j)
            if (candidates[i] == candidates[j]) return false;
    }
    return true;
}

void copyCandidates(State &state, const u16 *candidates) {
    for (unsigned i = 0; i < CANDIDATE_COUNT; ++i)
        state.candidates[i] = candidates[i];
    state.selected = NO_ENTRY;
    state.bannedMask = 0;
}

bool matches(const State &state, Token expected) {
    return state.generation && state.revision != ~0u &&
        state.generation == expected.generation && state.revision == expected.revision;
}

bool available(const State &state, unsigned candidate) {
    return candidate < CANDIDATE_COUNT && !(state.bannedMask & (1u << candidate));
}

} // namespace

Token token(const State &state) { return {state.generation, state.revision}; }

u8 currentActor(const State &state) {
    switch (state.phase) {
    case OPENING_HOST_BAN:
    case OPENING_HOST_PICK: return PLAYER_ONE;
    case OPENING_GUEST_BANS: return PLAYER_TWO;
    case COUNTER_WINNER_BAN: return state.previousWinner;
    case COUNTER_LOSER_PICK: return state.previousWinner ^ 1u;
    default: return NO_PLAYER;
    }
}

bool begin(State &state, u32 generation, u8 bestOf, const u16 *candidates) {
    if (!generation || (bestOf != 3 && bestOf != 5) || !validCandidates(candidates)) return false;
    State next = {};
    next.generation = generation;
    next.revision = 1;
    next.bestOf = bestOf;
    next.previousWinner = NO_PLAYER;
    next.phase = OPENING_HOST_BAN;
    copyCandidates(next, candidates);
    state = next;
    return true;
}

bool ban(State &state, u8 actor, unsigned candidate, Token expected) {
    if (!matches(state, expected) || actor > PLAYER_TWO || actor != currentActor(state) ||
        !available(state, candidate)) return false;
    if (state.phase != OPENING_HOST_BAN && state.phase != OPENING_GUEST_BANS &&
        state.phase != COUNTER_WINNER_BAN) return false;
    state.bannedMask |= 1u << candidate;
    if (state.phase == OPENING_HOST_BAN) state.phase = OPENING_GUEST_BANS;
    else if (state.phase == COUNTER_WINNER_BAN) state.phase = COUNTER_LOSER_PICK;
    else {
        unsigned count = 0;
        for (unsigned i = 0; i < CANDIDATE_COUNT; ++i)
            count += (state.bannedMask >> i) & 1u;
        if (count == 3) state.phase = OPENING_HOST_PICK;
    }
    ++state.revision;
    return true;
}

bool pick(State &state, u8 actor, unsigned candidate, Token expected) {
    if (!matches(state, expected) || actor > PLAYER_TWO || actor != currentActor(state) ||
        !available(state, candidate) ||
        (state.phase != OPENING_HOST_PICK && state.phase != COUNTER_LOSER_PICK)) return false;
    state.selected = state.candidates[candidate];
    state.roundWins[0] = state.roundWins[1] = 0;
    state.phase = IL_MATCH;
    ++state.revision;
    return true;
}

bool recordRound(State &state, u8 winner, Token expected) {
    if (!matches(state, expected) || state.phase != IL_MATCH ||
        (winner > PLAYER_TWO && winner != NO_PLAYER)) return false;
    if (winner != NO_PLAYER && ++state.roundWins[winner] == 2) {
        ++state.setWins[winner];
        state.previousWinner = winner;
        state.phase = state.setWins[winner] > state.bestOf / 2 ? SET_DONE : NEED_CANDIDATES;
    }
    ++state.revision;
    return true;
}

bool nextCandidates(State &state, const u16 *candidates, Token expected) {
    if (!matches(state, expected) || state.phase != NEED_CANDIDATES || !validCandidates(candidates)) return false;
    copyCandidates(state, candidates);
    state.phase = COUNTER_WINNER_BAN;
    ++state.revision;
    return true;
}

} // namespace LiveDraft
