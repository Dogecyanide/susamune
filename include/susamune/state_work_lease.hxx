#ifndef SUSAMUNE_STATE_WORK_LEASE_HXX
#define SUSAMUNE_STATE_WORK_LEASE_HXX

namespace StateWorkLease {
// Main-thread RAM work; a deferred storage restore retains its STATE owner.
void update();
bool quiet();
unsigned int epoch();

class Guard {
    unsigned char mHeld;
public:
    explicit Guard(bool needed = true);
    ~Guard();
    Guard(const Guard &) = delete;
    Guard &operator=(const Guard &) = delete;
    explicit operator bool() const { return mHeld; }
};
}
#endif
