#include "susamune/ghost_replay_start.hxx"
namespace GhostReplayStart {
bool destination(const GhostTraceDecode::StageStart &stage,const unsigned char *flags,
                        unsigned scenarios,LevelWarp::Dest &source,LevelWarp::Dest &target) {
    if(stage.previous.flags||stage.current.flags||stage.next.flags||
       stage.previous.area>0x3c||stage.previous.episode>9||stage.current.area>0x3c||stage.current.episode>9||
       stage.next.area!=stage.current.area||stage.next.episode!=stage.current.episode||
       stage.scene!=((unsigned(stage.current.area)<<8)|stage.current.episode))return false;
    GhostTraceInitialFlags::Snapshot decoded;
    if(!GhostTraceInitialFlags::decode(decoded,flags,GhostTraceInitialFlags::kImageBytes,scenarios))return false;
    source={stage.previous.area,stage.previous.episode,0};
    target={stage.current.area,stage.current.episode,static_cast<unsigned char>(decoded.gameInts[3])};
    return true;
}
}
