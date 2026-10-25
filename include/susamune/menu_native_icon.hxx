#pragma once

namespace MenuNativeIcon {
enum { WorkspaceBytes = 76704, BooBytes = 2080, ControllerBytes = 2912,
       PiantaBytes = 1568, GlassesBytes = 1152, MarioBytes = 992, TitleBytes = 928 };
bool loadBoo(void *workspace, unsigned int workspaceBytes, void *out, unsigned int capacity);
bool scaleController(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity);
bool scalePianta(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity);
bool scaleGlasses(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity);
bool scaleMario(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity);
bool scaleTitle(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity);
}
