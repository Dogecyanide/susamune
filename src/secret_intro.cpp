#include "susamune/addresses.hxx"
#include "susamune/settings.hxx"
#include "SMS/System/Application.hxx"

extern "C" bool susamuneSecretIntroMovie(TApplication *application) {
    const bool movie = application->checkAdditionalMovie();
    if (!movie || application->mCutSceneID != 5 ||
        gSettings.get(SETTING_FMV_SKIPS) != 2) return movie;
    typedef u8 (*SecretShineFn)(u8);
    const SecretShineFn secretShine = reinterpret_cast<SecretShineFn>(
        SUSAMUNE_MEM1_ADDR(0x800fc504u, 0x802a8a98u, 0x802a0b40u));
    // Movie 5 also introduces Pianta 3. Only native secret entries skip it.
    // Retail already updates its movie-seen flag; setMario still removes FLUDD.
    return secretShine(gpApplication.mCurrentScene.mAreaID) == 0xff;
}
