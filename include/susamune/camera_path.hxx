#pragma once

namespace CameraPath {
struct Pose { float x, y, z, yaw, pitch, fov; };
struct Frame { Pose pose; unsigned short halves; };
struct Path {
    Frame frames[16];
    float elapsed;
    unsigned char count, selected, segment;
    bool playing, linear, loop;
    void clear() { count = selected = segment = 0; elapsed = 0; playing = false; }
    void stop() { playing = false; elapsed = 0; }
    bool add(const Pose &pose) {
        if (count == 16) return false;
        stop(); selected = count++; frames[selected] = {pose, 6}; return true;
    }
    void erase() {
        if (!count) return;
        stop();
        for (unsigned i = selected + 1; i < count; ++i) frames[i-1] = frames[i];
        if (--count && selected >= count) --selected;
        if (!count) selected = 0;
    }
    bool start(Pose &out) {
        if (count < 2) return false;
        segment = 0; elapsed = 0; playing = true; out = frames[0].pose; return true;
    }
    bool advance(float seconds, Pose &out) {
        if (!playing || count < 2 || !(seconds >= 0)) return false;
        elapsed += seconds;
        unsigned next = (segment + 1) % count;
        float duration = frames[next].halves * 0.5f;
        while (elapsed >= duration) {
            elapsed -= duration; segment = next;
            if (segment == count - 1 && !loop) {
                out = frames[segment].pose; stop(); return true;
            }
            next = (segment + 1) % count; duration = frames[next].halves * 0.5f;
        }
        float t = elapsed / duration;
        if (!linear) t = t * t * (3 - 2 * t);
        const Pose &a = frames[segment].pose, &b = frames[next].pose;
        float yaw = b.yaw - a.yaw;
        if (yaw > 3.14159265f) yaw -= 6.2831853f;
        if (yaw < -3.14159265f) yaw += 6.2831853f;
        out = {a.x+(b.x-a.x)*t, a.y+(b.y-a.y)*t, a.z+(b.z-a.z)*t,
               a.yaw+yaw*t, a.pitch+(b.pitch-a.pitch)*t, a.fov+(b.fov-a.fov)*t};
        if (out.yaw > 3.14159265f) out.yaw -= 6.2831853f;
        if (out.yaw < -3.14159265f) out.yaw += 6.2831853f;
        return true;
    }
};
}
