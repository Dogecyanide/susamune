#pragma once
class Menu;
namespace ReplaySession {
#if MOONSHINE_GHOST_TRACE
void begin(bool sourceTas=false);
void stop();
void stageEntry(bool replaying);
bool blocksResults();
bool sourceTas();
void markSourceTas();
bool advance();
void draw(Menu *);
#else
inline void begin(bool=false){} inline void stop(){} inline void stageEntry(bool){}
inline bool blocksResults(){return false;} inline bool sourceTas(){return false;}
inline void markSourceTas(){} inline bool advance(){return true;} inline void draw(Menu*){}
#endif
}
