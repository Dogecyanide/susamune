#pragma once
class TMario;
struct SusamunePracticeInput;
namespace GhostWorldRuntime {
#if MOONSHINE_GHOST_TRACE
// Private replay diagnostics require both memory-card ports absent.
bool arm(unsigned fileBytes);
bool armFile(unsigned nonce, unsigned run, unsigned region);
unsigned startError();
bool ready();
bool startAt(int entry);
// Ordinary Watch takes its destination from the checked first stage record.
bool startRecorded();
// Only the pending playback-start warp may keep the replay owner.
bool permitsStartWarp(unsigned scene);
void prepareStartDeparture();
bool setSourceRunFlags(unsigned flags);
void stop();
void saveFailure();
bool busy();
bool temporarySettings();
bool active();
bool inputState(SusamunePracticeInput &);
bool hooksActive();
bool wantsRenderFeedback();
bool wantsWaterFeedback();
bool wantsSpinFeedback();
void stageSetup(unsigned area, unsigned episode, unsigned generation);
void afterWorldDraw();
void beforeFrame();
void observeFrame();
unsigned controls();
bool beforeDirect(bool frozen, bool suppressed, unsigned directorState);
void movement(TMario *, unsigned cue);
void random(unsigned caller, unsigned result, unsigned seed);
unsigned renderFeedback(unsigned caller,unsigned nativeValue,unsigned seed);
unsigned waterFeedback(unsigned caller,unsigned nativeValue,unsigned seed);
void status(unsigned *out);
void visualStatus(unsigned *out);
#else
inline bool busy() { return false; }
inline void prepareStartDeparture() {}
inline bool temporarySettings() { return false; }
inline bool active() { return false; }
inline bool inputState(SusamunePracticeInput &) { return false; }
inline bool permitsStartWarp(unsigned){return false;}
inline bool hooksActive() { return false; }
inline bool wantsRenderFeedback(){return false;}
inline bool wantsWaterFeedback(){return false;}
inline bool wantsSpinFeedback(){return false;}
inline void stageSetup(unsigned, unsigned, unsigned) {}
inline void afterWorldDraw() {}
inline void beforeFrame() {}
inline void observeFrame() {}
inline unsigned controls() { return 0; }
inline bool beforeDirect(bool, bool, unsigned) { return true; }
inline void movement(TMario *, unsigned) {}
inline void random(unsigned, unsigned, unsigned) {}
#endif
}
