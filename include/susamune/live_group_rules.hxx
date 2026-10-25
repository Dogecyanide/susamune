#pragma once

// Host-owned rules for three/four racers. Network and game effects are separate.
namespace LiveGroupRules {
enum { MaxPlayers = 4, MaxCandidates = 5, Nobody = 255 };
enum Phase { Lobby, Draft, Ready, Racing, Results, NeedCandidates, Finished, Roaming };
struct Config {
    unsigned char players, bestOf, setBestOf;
    bool draft, freeRoam;
};
struct Token { unsigned generation, revision; };
struct State {
    Config config;
    unsigned generation, revision, round;
    unsigned short candidates[MaxCandidates], selected;
    int times[MaxPlayers];
    unsigned char phase, readyMask, resultMask, eligibleMask;
    unsigned char bannedMask, bans, rotation, winner;
    unsigned char roundWins[MaxPlayers], setWins[MaxPlayers];
};
bool begin(State &, Config, unsigned generation, unsigned short entry);
Token token(const State &);
unsigned actor(const State &);
bool candidates(State &, const unsigned short *, unsigned count, Token);
bool ban(State &, unsigned player, unsigned candidate, Token);
bool ready(State &, unsigned player, bool value, unsigned generation);
bool start(State &, unsigned connectedMask);
bool result(State &, unsigned player, int qf, bool eligible, unsigned generation, unsigned round);
bool advance(State &);
void cancel(State &);
}
