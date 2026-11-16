#pragma once
#include "ghost_trace_checkpoint.h"
namespace GhostTraceBranchIo {
enum Phase { UNCONFIGURED, IDLE, WAITING, READY, FAILED };
struct Hooks {
    void*context;
    volatile MsTraceBranchMailbox*mailbox;
    volatile MsTraceLookup*result;
    void(*flush)(void*,const void*,unsigned);
    void(*invalidate)(void*,void*,unsigned);
};
struct Client { Hooks hooks;unsigned nonce,sequence,fileNonce,run,game,error,operation;Phase phase;bool canceled;MsTraceLookup value; };
bool configure(Client&,const Hooks&,unsigned bootNonce);
bool lookup(Client&,unsigned fileNonce,unsigned run,unsigned game);
bool pin(Client&,const MsTraceBranch&,bool release=false);
bool erase(Client&,unsigned fileNonce,unsigned run,unsigned expectedHeaderHash);
Phase poll(Client&);
const MsTraceLookup*result(const Client&);
bool consume(Client&);
// Cancellation waits for the exact receipt; the shared mailbox is never stolen.
bool cancel(Client&);
bool configureNative(Client&,unsigned bootNonce);
}
