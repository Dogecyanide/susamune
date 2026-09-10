#pragma once

#include <Dolphin/types.h>

class TMarDirector;
class TMovieDirector;

namespace RetailInput {
enum Context { Unavailable, StageLoading, StageReady, MovieLoading, MovieReady };
enum { kMovieSceneTag = 0xfe000000u };

Context context();
u32 sceneKey();
TMarDirector *stageDirector();
TMovieDirector *movieDirector();
}
