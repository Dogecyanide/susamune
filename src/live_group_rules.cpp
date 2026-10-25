#include "susamune/live_group_rules.hxx"
#include "susamune/live_race_wire.h"

namespace LiveGroupRules {
namespace {
bool current(const State &s, Token t) {
    return t.generation == s.generation && t.revision == s.revision && s.revision != ~0u;
}
unsigned everyone(const State &s) { return (1u << s.config.players) - 1; }
void clearAttempt(State &s) {
    s.readyMask = s.resultMask = s.eligibleMask = 0;
    s.winner = Nobody;
    for (unsigned i = 0; i < MaxPlayers; ++i) s.times[i] = -1;
}
}
bool begin(State &s, Config config, unsigned generation, unsigned short entry) {
    if (config.players < 3 || config.players > MaxPlayers || !generation ||
        (config.bestOf != 1 && config.bestOf != 3 && config.bestOf != 5 && config.bestOf != 7) ||
        (config.setBestOf != 3 && config.setBestOf != 5) ||
        (config.draft && (config.freeRoam || config.bestOf != 3))) return false;
    s = {};
    s.config = config; s.generation = generation; s.selected = entry;
    s.phase = config.freeRoam ? Roaming : config.draft ? NeedCandidates : Ready;
    clearAttempt(s);
    return true;
}
Token token(const State &s) { return Token{s.generation, s.revision}; }
unsigned actor(const State &s) {
    return s.phase == Draft ? (s.rotation + s.bans) % s.config.players : Nobody;
}
bool candidates(State &s, const unsigned short *entries, unsigned count, Token t) {
    if (!entries || !current(s, t) || s.phase != NeedCandidates || count != s.config.players + 1u) return false;
    for (unsigned i = 0; i < count; ++i)
        for (unsigned j = 0; j < i; ++j) if (entries[i] == entries[j]) return false;
    for (unsigned i = 0; i < MaxCandidates; ++i) s.candidates[i] = i < count ? entries[i] : 0;
    for (unsigned i = 0; i < MaxPlayers; ++i) s.roundWins[i] = 0;
    s.bans = s.bannedMask = 0; s.phase = Draft; ++s.revision;
    return true;
}
bool ban(State &s, unsigned player, unsigned candidate, Token t) {
    if (!current(s, t) || player != actor(s) || candidate > s.config.players ||
        (s.bannedMask & (1u << candidate))) return false;
    s.bannedMask |= 1u << candidate; ++s.bans; ++s.revision;
    if (s.bans == s.config.players) {
        for (unsigned i = 0; i <= s.config.players; ++i)
            if (!(s.bannedMask & (1u << i))) s.selected = s.candidates[i];
        s.phase = Ready; clearAttempt(s);
    }
    return true;
}
bool ready(State &s, unsigned player, bool value, unsigned generation) {
    if (s.phase != Ready || player >= s.config.players || generation != s.generation) return false;
    if (value) s.readyMask |= 1u << player;
    else s.readyMask &= ~(1u << player);
    return true;
}
bool start(State &s, unsigned connectedMask) {
    if (s.phase != Ready || s.readyMask != everyone(s) || connectedMask != everyone(s) || s.round == ~0u) return false;
    ++s.round; s.phase = Racing; s.readyMask = 0;
    return true;
}
bool result(State &s, unsigned player, int qf, bool eligible, unsigned generation, unsigned round) {
    if (s.phase != Racing || player >= s.config.players || generation != s.generation || round != s.round ||
        (s.resultMask & (1u << player)) || (eligible ? qf < 0 : qf != -1 && qf != MSR_FORFEIT_QF)) return false;
    s.resultMask |= 1u << player;
    if (eligible) s.eligibleMask |= 1u << player;
    s.times[player] = qf;
    if (s.resultMask != everyone(s)) return true;
    s.phase = Results;
    unsigned winner = Nobody;
    for (unsigned i = 0; i < s.config.players; ++i) {
        if (s.times[i] == -1) return true; // Assisted attempts still void the round.
        if ((s.eligibleMask & (1u << i)) && (winner == Nobody || s.times[i] < s.times[winner])) winner = i;
    }
    if (winner == Nobody) return true;
    for (unsigned i = 0; i < s.config.players; ++i)
        if (i != winner && s.times[i] == s.times[winner]) return true;
    s.winner = winner; ++s.roundWins[winner];
    if (s.roundWins[winner] > s.config.bestOf / 2) {
        if (!s.config.draft || ++s.setWins[winner] > s.config.setBestOf / 2) s.phase = Finished;
    }
    return true;
}
bool advance(State &s) {
    if (s.phase != Results) return false;
    const bool nextIl = s.config.draft && s.winner < s.config.players &&
        s.roundWins[s.winner] > s.config.bestOf / 2;
    clearAttempt(s);
    if (nextIl) s.rotation = (s.rotation + 1) % s.config.players;
    s.phase = nextIl ? NeedCandidates : Ready;
    return true;
}
void cancel(State &s) {
    if (s.phase != Racing && s.phase != Ready) return;
    clearAttempt(s); s.phase = Results;
}
}
