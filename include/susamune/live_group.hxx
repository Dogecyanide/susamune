#pragma once
#include "susamune/live_group_rules.hxx"
#include "susamune/live_race_session.hxx"
#include "susamune/live_playlist.hxx"

#if TIMEWARP_LIVE_RACING
namespace LiveGroup {
enum { Welcome = 32, Snapshot, Name, Request };
struct Config {
    LiveGroupRules::Config rules;
    unsigned short entry;
    unsigned char episode, pool;
    bool playlist;
    unsigned catalogue, playlistHash;
};
struct Member { char name[17]; unsigned char region; unsigned ping; };
struct Hooks {
    void *context;
    bool (*validEntry)(void *, unsigned, unsigned pool, bool draft);
    bool (*drawCandidates)(void *, unsigned short *, unsigned count, unsigned pool);
    bool (*startRace)(void *, const Config &, const LivePlaylist::Plan *);
    void (*cancelRace)(void *);
    void (*pose)(void *, unsigned player, const MSRHeader &, const MSRPose &, unsigned now);
    void (*resetPose)(void *, unsigned player);
};
struct Room;
struct LinkContext { Room *room; unsigned index; };
struct Room {
    LiveRaceSession::Session *primary;
    LiveRaceSession::Session extra[2];
    LinkContext links[2];
    Hooks hooks;
    Config config;
    LiveGroupRules::State rules;
    LivePlaylist::Transfer playlist;
    Member members[4];
    MSRPose poses[4];
    unsigned poseSequence[4], poseReceived[4], remoteSceneEpoch[4];
    unsigned serial, receivedSerial, sentSerial[3], sentAt[3], now, settledAt, ownPoseSequence;
    unsigned requestGeneration, requestRevision, requestRound;
    int requestValue;
    unsigned char self, connectedMask, welcomedMask, poseMask, recipient, controlRecipient;
    unsigned char syncStep[3], playlistAt[3], requestAction;
    bool active, host, outcomeChanged;
};
bool host(Room &, LiveRaceSession::Session &, const Config &, const LivePlaylist::Plan *, const Hooks &, unsigned generation);
bool configure(Room &, const Config &, const LivePlaylist::Plan *);
// Called only after a bound, reliable session has delivered Welcome.
bool adopt(Room &, LiveRaceSession::Session &, const Config &, const Hooks &, const void *, unsigned bytes);
void stop(Room &);
bool receive(Room &, const TWLiveEndpoint &, const void *, unsigned bytes, unsigned now);
bool kickPeer(Room &, const TWLiveEndpoint &);
void replacePeer(Room &, const TWLiveEndpoint &oldPeer, const TWLiveEndpoint &newPeer, unsigned now);
bool control(Room &, unsigned link, const MSRHeader &, const void *, unsigned bytes);
void pose(Room &, unsigned link, const MSRHeader &, const MSRPose &, unsigned now);
void localPose(Room &, const MSRPose &, unsigned now);
void tick(Room &, unsigned now);
bool ready(Room &, bool);
bool ban(Room &, unsigned candidate);
bool result(Room &, int qf, bool eligible);
bool cancel(Room &);
unsigned connectedCount(const Room &);
unsigned remoteSlot(const Room &, unsigned player);
}
#endif
