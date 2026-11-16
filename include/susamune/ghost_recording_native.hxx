#pragma once
namespace GhostRecordingNative {
void poll();
void prepareWatch(bool two);
void cancelWatch();
bool watchReady();
bool watchWaiting();
bool startWatch();
bool fileBusy();
}
