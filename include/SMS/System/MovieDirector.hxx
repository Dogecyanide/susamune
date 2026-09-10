#pragma once

#include <JSystem/JDrama/JDRDirector.hxx>

class TMarioGamePad;
namespace JDrama { class TDisplay; }

// Shared prefix verified against each retail constructor and direct().
class TMovieDirector : public JDrama::TDirector {
public:
    TMovieDirector();
    virtual ~TMovieDirector();
    s32 direct() override;
    s32 decideNextMode(s32 *);
    const char *getStreamMovieName(u32);
    void rsetup();
    s32 setup(JDrama::TDisplay *, TMarioGamePad *);
    void setupThreadFunc(void *);

    u8 mSyncStarted;
    s32 mState;
    TMarioGamePad *mGamePad;
    void *mCardSave;
    void *mSubTitle;
    void *mRumble;
    u16 mFlags;
    u32 _34;
    u32 _38;
};

static_assert(__builtin_offsetof(TMovieDirector, mState) == 0x1c &&
              __builtin_offsetof(TMovieDirector, mGamePad) == 0x20 &&
              __builtin_offsetof(TMovieDirector, mFlags) == 0x30,
              "retail movie director prefix");
