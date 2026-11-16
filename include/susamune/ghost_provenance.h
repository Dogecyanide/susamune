#pragma once
#include "ghost_run_flags.h"
#define MS_TRACE_PROVENANCE_SCHEMA 1u
#define MS_TRACE_PROVENANCE_TAG 0x50525631u
#define MS_TRACE_PROVENANCE_MASK 0x27u
static inline int MsTraceProvenanceValid(unsigned flags){
    return !(flags&~MS_TRACE_PROVENANCE_MASK)&&SusamuneGhostRunFlagsValid(flags)&&
        (!(flags&(SUSAMUNE_GHOST_RUN_SAVESTATE_USED|SUSAMUNE_GHOST_RUN_FAST_FORWARD_USED))||
         (flags&(SUSAMUNE_GHOST_RUN_TAS|SUSAMUNE_GHOST_RUN_ASSISTED))==(SUSAMUNE_GHOST_RUN_TAS|SUSAMUNE_GHOST_RUN_ASSISTED));
}
