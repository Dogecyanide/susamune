#pragma once
#include "susamune/live_p2p.hxx"

// Slots are invitations, not player numbers; joining order assigns the roster.
namespace LiveInvites {
struct Slot { LiveP2P::Code code; LiveP2P::Punch punch; };
struct State { Slot slots[3]; unsigned count, pin; };
void reset(State &, unsigned pin, unsigned count);
bool set(State &, unsigned slot, const LiveP2P::Code &);
void clear(State &, unsigned slot);
bool permits(const State &, const TWLiveEndpoint &);
int find(const State &, const TWLiveEndpoint &);
int connected(State &, const TWLiveEndpoint &);
bool receive(State &, const TWLiveEndpoint &, const void *, unsigned bytes, unsigned now);
}
