#ifndef SUSAMUNE_TRANSFER_LEASE_HXX
#define SUSAMUNE_TRANSFER_LEASE_HXX
#include "transfer_lease.h"

namespace TransferLease {
enum Mode { UNINITIALIZED, UNAVAILABLE, LEGACY, CAPABLE, ACTIVATING, SHARED, FAILED };
enum Owner { GHOST = TW_OWNER_GHOST, STATE = TW_OWNER_STATE, CODEC };
struct Token { unsigned int epoch, ticket, owner; };
struct Borrow { unsigned int epoch, ticket, owner; };

// Boot/reinjection only. A surviving active ARM epoch cannot be adopted.
Mode init();
Mode mode();
bool legacyAllowed();
bool sharedMap();
// Stop new legacy requests first; quiet includes unconsumed results and local codecs.
bool activate(bool ghostQuiet, bool stateQuiet, bool localQuiet);
void poll();
bool claim(Owner, Token &);
bool owns(const Token &);
// Check ordinary backend availability too. Flush payload and immutable request first.
bool submit(const Token &, unsigned int seq, unsigned int session, unsigned int command);
// Shared cancellation never rewrites the legacy request or releases the token.
bool cancel(const Token &);
bool take(const Token &, Borrow &);
// Only after every borrowed payload/metadata pointer is no longer used.
bool consumed(const Token &, const Borrow &);
bool release(const Token &);
}
#endif
