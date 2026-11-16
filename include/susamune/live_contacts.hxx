#pragma once
#include "susamune/live_p2p.hxx"
namespace LiveContacts {
void remember(const char *name, const LiveP2P::Code &code);
const char *name(unsigned slot);
bool copy(unsigned slot, char *out);
void forget(unsigned slot);
}
