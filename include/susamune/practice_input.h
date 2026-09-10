#ifndef SUSAMUNE_PRACTICE_INPUT_H
#define SUSAMUNE_PRACTICE_INPUT_H

/* Host, ARM and PPC use the same explicit input fields; buttons are BE on disk. */
struct SusamunePracticeInput {
    unsigned short buttons;
    signed char stickX;
    signed char stickY;
    signed char substickX;
    signed char substickY;
    unsigned char triggerL;
    unsigned char triggerR;
    unsigned char analogA;
    unsigned char analogB;
    signed char error;
    unsigned char flags;
};

#ifdef __cplusplus
static_assert(sizeof(SusamunePracticeInput) == 12, "practice input size");
#endif

#endif
