#pragma once

namespace MenuNativeIcon {
enum { WorkspaceBytes = 76704, BooBytes = 2080, ControllerBytes = 6272 };
bool loadBoo(void *workspace, unsigned int workspaceBytes, void *out, unsigned int capacity);
bool scaleController(const void *source, unsigned int sourceBytes, void *out, unsigned int capacity);
}
