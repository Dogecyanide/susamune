#pragma once
#ifndef SUSAMUNE_SAVE_PROBE
#define SUSAMUNE_SAVE_PROBE 0
#endif
#if SUSAMUNE_SAVE_PROBE
#include "susamune/state_codec.hxx"
#include "susamune/state_quick_replay.hxx"
#include "susamune/ghost_trace_stream_storage.h"

namespace StateSaveProbe {
enum Mode { OFF, BASELINE, EXTRA };
enum { kMagic=0x53535031u, kControlOffset=0xA0u, kExtraBytes=500u*1024u, kLoanBytes=kExtraBytes+64u };
struct Token { unsigned nonce,serial,epoch,mode; };
struct Control {
    unsigned magic,nonce,mode,busy,serial,epoch,saves,error;
    unsigned lastMode,lastSlot,ticks,raw,packed,cached,spilled,replayed;
    unsigned moved,passes,success,canaryLow,canaryHigh,reserved[3];
};
static_assert(sizeof(Control)==96 && kControlOffset>=sizeof(MsTraceMailbox) &&
    kControlOffset+sizeof(Control)<=MS_TRACE_READ_MAILBOX_OFFSET,"probe stays in unused PPC-owned control lines");
static_assert(kLoanBytes<=MS_TRACE_BUFFER_BYTES,"probe uses only trace buffer zero");
bool enabled();
Mode mode();
bool select(Mode);
const char *label();
void summary(char *,unsigned);
Token current();
bool admitted(const Token &);
bool validActive();
StateCodec::WriteSpan destination(const Token &);
StateQuickReplay::SpillCache spill(Token &);
void note(const StateQuickReplay::Stats &);
class Trial {
    Token mToken;
    unsigned mStart;
    bool mValid;
public:
    Trial(unsigned epoch,unsigned slot,unsigned startTick);
    ~Trial();
    explicit operator bool() const {return mValid;}
    void success(unsigned raw,unsigned packed);
};
}
#else
namespace StateSaveProbe { inline bool enabled(){return false;} }
#endif
