#ifndef SUSAMUNE_NATIVE_TIMER_TRANSFORM_H
#define SUSAMUNE_NATIVE_TIMER_TRANSFORM_H

static int SusamuneTimerScaleFloor(int value, int percent) {
    int product = value * percent;
    return (product - (product < 0 ? 99 : 0)) / 100;
}

static int SusamuneTimerScaleCeil(int value, int percent) {
    int product = value * percent;
    return (product + (product > 0 ? 99 : 0)) / 100;
}

static void SusamuneTimerScaleBasis(float *matrix, int percent) {
    const float scale = percent * 0.01f;
    int row;
    for (row = 0; row < 3; ++row) {
        matrix[row * 4] *= scale;
        matrix[row * 4 + 1] *= scale;
    }
}

#endif
