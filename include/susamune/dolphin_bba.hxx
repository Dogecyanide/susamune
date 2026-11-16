#ifndef SUSAMUNE_DOLPHIN_BBA_HXX
#define SUSAMUNE_DOLPHIN_BBA_HXX
namespace DolphinBba {
bool init(unsigned char mac[6]);
bool send(const unsigned char *frame, unsigned bytes);
// Zero means no packet or a busy shared EXI bus; malformed frames are discarded.
unsigned receive(unsigned char *frame, unsigned capacity);
}
#endif
