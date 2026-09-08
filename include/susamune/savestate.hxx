#ifndef _SUSAMUNE_SAVESTATE_HXX
#define _SUSAMUNE_SAVESTATE_HXX

#include <Dolphin/types.h>

class Menu;

class SavestateManager {
public:
    enum { kSlotCount = 3 };
    struct SlotInfo {
        bool valid;
        u8 area;
        u8 episode;
        u32 generation;
        u32 packedBytes;
    };

    SavestateManager();

    u32 activeSlot() const;
    SlotInfo slotInfo(u32 slot) const;
    bool selectSlot(u32 slot);
    bool cycleSlot();
    bool clearSlot(u32 slot, u32 expectedGeneration);

    // Called once per frame from main.cpp's onUpdate hook. Polls the d-pad
    // and triggers saves. Loads are queued until the post-render hook so the
    // current frame cannot consume a mixture of live and restored state.
    void updateHook();

    // Called after the game's THPPlayerDrawDone()/GXDrawDone barrier. A queued
    // load is restored here, after director, fader, audio, and rendering work
    // for the current frame has finished.
    void processPendingLoad();

    // Drawn after the scene each frame; the production prompt uses the
    // configurable Creation style and the optional debug label stays separate.
    void draw(Menu *menu);

    // Public so callers can trigger from elsewhere (e.g. a debug menu).
    bool saveState();
    bool loadState();
    // Replay loads its original slot even if the menu selection changed.
    bool loadSlot(u32 slot, u32 expectedGeneration);

private:
    void feedback(const char *debug, const char *message);

#if ENABLE_SAVESTATE_DBG
    void setStatus(const char *msg);
#endif
    char mFeedback[48];
    int  mFeedbackFrames;
    bool mLoadPending;
    u16  mLoadWaitFrames;
};
static_assert(sizeof(SavestateManager) == 56,
              "savestate controller layout changed");

#endif // _SUSAMUNE_SAVESTATE_HXX
