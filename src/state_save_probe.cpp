#include "susamune/state_save_probe.hxx"
#if SUSAMUNE_SAVE_PROBE
#if IS_EMULATOR || !MOONSHINE_GHOST_TRACE || !TIMEWARP_QUICK_REPLAY || !TIMEWARP_SHARED_STORE || TIMEWARP_QF_MEMORY_PILOT
#error Save probe requires native shared Quick state and the nondestructive trace grant
#endif
#include "susamune/ghost_memory.hxx"
#include "susamune/ghost_trace.hxx"
#include "susamune/ghost_world_runtime.hxx"
#include "susamune/state_work_lease.hxx"
#include "susamune/transfer_lease.hxx"
#include "Dolphin/OS.h"
#include "Dolphin/mem.h"
#include "Dolphin/printf.h"

#ifndef STATE_SAVE_PROBE_CONTROL
#define STATE_SAVE_PROBE_CONTROL (MS_TRACE_CONTROL_PPC+StateSaveProbe::kControlOffset)
#define STATE_SAVE_PROBE_BUFFER MS_TRACE_BUFFER0_PPC
#define STATE_SAVE_PROBE_READER(i) MS_TRACE_READ_MAILBOX_PPC(i)
#define STATE_SAVE_PROBE_WRITER MS_TRACE_CONTROL_PPC
#endif
namespace StateSaveProbe {
namespace {
Token activeToken;
bool quarantined;
Control &control(){return *reinterpret_cast<Control*>(STATE_SAVE_PROBE_CONTROL);}
unsigned char *buffer(){return reinterpret_cast<unsigned char*>(STATE_SAVE_PROBE_BUFFER);}
unsigned nonce(){
    auto *m=reinterpret_cast<volatile MsTraceMailbox*>(STATE_SAVE_PROBE_WRITER);
    DCInvalidateRange(const_cast<MsTraceResponse*>(&m->response),32);
    return m->response.magic==MS_TRACE_MAGIC && m->response.version==MS_TRACE_VERSION?m->response.nonce:0;
}
bool validControl(){return GhostMemory::ready() && control().magic==kMagic && control().nonce && control().nonce==nonce();}
bool critical(){unsigned msr,hid2;asm volatile("mfmsr %0\n\tmfspr %1,920":"=r"(msr),"=r"(hid2)::"memory");return !(msr&0x8000u)&&!(hid2&0x0f000000u);}
bool ownersIdle(unsigned boot){
    if(!boot || !GhostMemory::ready() || !GhostTrace::saveProbeIdle() || GhostWorldRuntime::busy())return false;
    for(unsigned i=0;i<MS_TRACE_READ_CHANNELS;++i){
        const auto *m=reinterpret_cast<volatile const MsTraceReadMailbox*>(STATE_SAVE_PROBE_READER(i));
        DCInvalidateRange(const_cast<MsTraceReadResponse*>(&m->response),32);
        const auto &r=m->response;
        if(r.magic!=MS_TRACE_READ_MAGIC || r.version!=MS_TRACE_READ_VERSION || r.bootNonce!=boot ||
            r.status!=MS_TRACE_READ_OK || r.fileSize || r.bytes || m->request.sequence!=r.ack)return false;
    }
    return true;
}
bool canaries(const Control &c){
    const auto *first=reinterpret_cast<const unsigned*>(buffer());
    const auto *last=reinterpret_cast<const unsigned*>(buffer()+32+kExtraBytes);
    for(unsigned i=0;i<8;++i)if(first[i]!=(c.canaryLow^i*0x9e3779b9u) || last[i]!=(c.canaryHigh^i*0x9e3779b9u))return false;
    return true;
}
bool spillAdmitted(void *opaque,const void *data,unsigned bytes){
    return data==buffer()+32 && bytes==kExtraBytes && admitted(*static_cast<const Token*>(opaque));
}
}
bool enabled(){return quarantined || (validControl() && control().mode!=OFF);}
Mode mode(){return validControl() && control().mode<=EXTRA?static_cast<Mode>(control().mode):OFF;}
bool select(Mode next){
    if(quarantined || next>EXTRA || !GhostMemory::ready() || !TransferLease::sharedMap() || !StateWorkLease::quiet())return false;
    const bool irq=OSDisableInterrupts();const unsigned boot=nonce();Control &c=control();
    bool ok=ownersIdle(boot) && (!validControl() || !c.busy);
    if(ok){if(c.magic!=kMagic || c.nonce!=boot){c={};c.magic=kMagic;c.nonce=boot;}c.mode=next;}
    OSRestoreInterrupts(irq);return ok;
}
const char *label(){if(quarantined)return "Fault: restart";return mode()==BASELINE?"A: current":mode()==EXTRA?"B: +500 KiB":"Off";}
void summary(char *out,unsigned bytes){
    if(quarantined){snprintf(out,bytes,"Probe safety check failed; restart the launcher.");return;}
    if(!enabled() || !control().saves){snprintf(out,bytes,"Stop trace recording/replay before A/B. All three states stay available.");return;}
    const Control &c=control();const unsigned divisor=OS_TIMER_CLOCK/1000u;
    snprintf(out,bytes,"%c #%u: %u ms, %u repeat blocks%s",c.lastMode==EXTRA?'B':'A',c.saves,divisor?c.ticks/divisor:0,c.spilled,c.success?"":" (failed)");
}
Token current(){return activeToken;}
bool admitted(const Token &token){
    if(!token.serial)return !quarantined && !activeToken.serial;
    const Control &c=control();
    return validControl() && critical() && c.busy && c.nonce==token.nonce && c.serial==token.serial &&
        c.epoch==token.epoch && c.mode==token.mode && token.epoch && StateWorkLease::epoch()==token.epoch &&
        ownersIdle(token.nonce) && canaries(c);
}
bool validActive(){return !quarantined && admitted(activeToken);}
StateCodec::WriteSpan destination(const Token &token){return token.serial?StateCodec::WriteSpan{buffer(),kLoanBytes}:StateCodec::WriteSpan{};}
StateQuickReplay::SpillCache spill(Token &token){return {buffer()+32,kExtraBytes,&token,spillAdmitted};}
void note(const StateQuickReplay::Stats &stats){
    if(!enabled() || !control().busy)return;
    Control &c=control();++c.passes;c.cached+=stats.cachedBytes;c.spilled+=stats.spilledBlocks;
    c.replayed+=stats.replayRawBytes;c.moved+=stats.movedBytes;
}
Trial::Trial(unsigned epoch,unsigned slot,unsigned start):mToken{},mStart(start),mValid(!enabled()){
    if(mValid)return;
    if(quarantined || !GhostMemory::ready())return;
    Control &c=control();
    if(!critical() || !epoch || StateWorkLease::epoch()!=epoch || c.busy || c.serial==~0u || !ownersIdle(c.nonce))return;
    DCFlushRange(buffer(),kLoanBytes);DCInvalidateRange(buffer(),kLoanBytes);
    c.busy=1;c.epoch=epoch;++c.serial;c.lastMode=c.mode;c.lastSlot=slot;c.error=0;
    c.raw=c.packed=c.cached=c.spilled=c.replayed=c.moved=c.passes=c.success=0;
    c.canaryLow=kMagic^c.nonce^c.serial^c.epoch;c.canaryHigh=~c.canaryLow;
    auto *first=reinterpret_cast<unsigned*>(buffer());auto *last=reinterpret_cast<unsigned*>(buffer()+32+kExtraBytes);
    for(unsigned i=0;i<8;++i){first[i]=c.canaryLow^i*0x9e3779b9u;last[i]=c.canaryHigh^i*0x9e3779b9u;}
    mToken={c.nonce,c.serial,c.epoch,c.mode};activeToken=mToken;mValid=admitted(mToken);
}
void Trial::success(unsigned raw,unsigned packed){const bool irq=OSDisableInterrupts();if(mToken.serial && admitted(mToken)){Control &c=control();c.raw=raw;c.packed=packed;c.success=1;}OSRestoreInterrupts(irq);}
Trial::~Trial(){
    if(!mToken.serial)return;
    const bool irq=OSDisableInterrupts();Control &c=control();
    if(!admitted(mToken)){quarantined=true;c.error=1;c.success=0;activeToken={};OSRestoreInterrupts(irq);return;}
    c.ticks=OSGetTick()-mStart;++c.saves;
    // Loan contents are dead. Discard dirty lines before returning the buffer.
    DCInvalidateRange(buffer(),kLoanBytes);c.busy=0;c.epoch=0;activeToken={};OSRestoreInterrupts(irq);
}
}
#endif
