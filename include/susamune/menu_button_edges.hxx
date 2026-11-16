#pragma once

struct MenuButtonEdges {
    unsigned short previous, pressed, released, deferred;
    void sample(unsigned short held) {
        pressed = held & ~previous;
        released = previous & ~held;
        previous = held;
    }
    unsigned short tabs(unsigned short shoulders, unsigned short onRelease) {
        // Decide on press; changing pages must not also act on its release.
        const unsigned short action = (pressed & shoulders & ~onRelease) | (released & deferred);
        deferred = (deferred & ~released) | (pressed & shoulders & onRelease);
        return action;
    }
};
