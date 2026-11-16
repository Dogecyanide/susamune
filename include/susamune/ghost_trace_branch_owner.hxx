#pragma once
namespace GhostTraceBranchOwner {
struct State { const volatile void *mailbox; const void *owner; unsigned nonce; };
extern State state;
// Validate the kernel nonce first. An ACK does not release an unread reply.
inline bool claim(const volatile void *mailbox, unsigned nonce, const void *owner) {
    if (!mailbox || !nonce || !owner) return false;
    if (state.mailbox == mailbox && state.nonce != nonce) state = {};
    if (state.owner) return state.mailbox == mailbox && state.nonce == nonce && state.owner == owner;
    state = {mailbox, owner, nonce};
    return true;
}
inline void release(const volatile void *mailbox, unsigned nonce, const void *owner) {
    if (state.mailbox == mailbox && state.nonce == nonce && state.owner == owner) state.owner = nullptr;
}
}
