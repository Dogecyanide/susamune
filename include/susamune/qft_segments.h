#ifndef SUSAMUNE_QFT_SEGMENTS_H
#define SUSAMUNE_QFT_SEGMENTS_H

// QFT segments and observed loading time are independent measurements.
struct MoonshineQftSegments {
    enum { CAPACITY = 8 };
    struct Stage {
        int begin, end;
        unsigned loadMs;
        unsigned short scene;
    } stages[CAPACITY];
    unsigned serial, generation;
    int last, entryEdge;
    unsigned char count;
    bool seen, valid, complete;

    void invalidate() { valid = complete = false; }
    void sample(unsigned attempt, unsigned setup, unsigned short scene, int qf,
                int localQf, unsigned loadMs) {
        if (qf < 0) { invalidate(); return; }
        if (!seen || serial != attempt) {
            serial = attempt; generation = setup; seen = valid = true;
            complete = false; count = 1; entryEdge = -1; last = qf;
            stages[0] = {0, 0, ~0u, scene};
            return;
        }
        if (!valid || complete) return;
        if (qf < last) { invalidate(); return; }
        if (setup != generation) {
            if (count == CAPACITY) { invalidate(); return; }
            const int end = entryEdge >= 0 ? entryEdge : last;
            // Standalone stages use offset -4. Sampling the first ready frame
            // instead would lose early ticks and inflate the transition gap.
            const int begin = qf - localQf + 4;
            if (end < stages[count - 1].begin || begin < end || begin > qf) { invalidate(); return; }
            stages[count - 1].end = end;
            stages[count - 1].loadMs = loadMs;
            stages[count++] = {begin, begin, ~0u, scene};
            generation = setup; entryEdge = -1;
        }
        last = qf;
    }
    void transition(int qf) {
        if (!valid || complete || !count || entryEdge >= 0) return;
        if (qf >= stages[count - 1].begin && qf <= last) entryEdge = qf;
    }
    bool finish(int qf) {
        if (!valid || complete || count < 2 || qf < stages[count - 1].begin) return false;
        stages[count - 1].end = qf;
        complete = true;
        return true;
    }
};

#endif
