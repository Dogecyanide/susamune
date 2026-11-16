#pragma once
#include "susamune/ghost_trace_io.hxx"
#include "susamune/ghost_trace_stream_native.h"
namespace GhostTraceStreamNative {
struct Context { GhostArena::Arena *arena; GhostTraceIo::Transport *transport; unsigned nonce; };
// Caller-owned control lives outside all five data banks. The lifecycle owner must
// reject recorder starts until every stream closes, including failed/cancelled I/O.
// Dolphin requires a separate external file service; this native binding fails closed there.
bool configure(Context &,GhostTraceIo::Transport &,GhostArena::Arena &,unsigned bootNonce);
bool idleWriter(unsigned bootNonce);
}
