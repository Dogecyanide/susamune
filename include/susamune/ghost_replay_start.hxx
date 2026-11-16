#pragma once
#include "susamune/ghost_trace_decode.hxx"
#include "susamune/ghost_trace_initial_flags.hxx"
#include "susamune/warp_wheel.hxx"
namespace GhostReplayStart {
bool destination(const GhostTraceDecode::StageStart &,const unsigned char *flags,
                 unsigned scenarios,LevelWarp::Dest &source,LevelWarp::Dest &target);
}
