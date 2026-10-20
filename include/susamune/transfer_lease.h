#ifndef SUSAMUNE_TRANSFER_LEASE_H
#define SUSAMUNE_TRANSFER_LEASE_H

/* Shared transition core. The adapter supplies cache barriers and truthful
 * worker-quiescence proofs; this header neither touches payloads nor does I/O. */
#ifndef TW_LEASE_INLINE
#define TW_LEASE_INLINE static inline
#endif
#define TW_LEASE_MAGIC 0x534C5331u
#define SUSAMUNE_TRANSFER_RUNTIME_ABI 0x00010002u
#define TW_LEASE_REQUEST_OFFSET 64u
#define TW_LEASE_RESPONSE_OFFSET 96u
#define TW_LEASE_REQUEST_PUBLICATION_OFFSET 128u
#define TW_LEASE_RESPONSE_PUBLICATION_OFFSET 160u
enum { TW_OWNER_NONE, TW_OWNER_GHOST, TW_OWNER_STATE };
enum { TW_WIRE_CAPABLE = 1, TW_WIRE_ACTIVATE, TW_WIRE_READY, TW_WIRE_LOCAL,
       TW_WIRE_ARM, TW_WIRE_CANCEL, TW_WIRE_DONE, TW_WIRE_DRAINING };
enum { TW_PPC_DETACHED, TW_PPC_ATTACHING, TW_PPC_IDLE, TW_PPC_LOCAL,
       TW_PPC_REMOTE, TW_PPC_RESULT, TW_PPC_BORROWED };

typedef struct {
    unsigned int magic, epoch, ticket, owner, phase, seq, session, command;
} TWLeaseLine;
typedef struct {
    unsigned int generation, issued, reserved[6];
} TWLeasePublication;
typedef struct {
    TWLeaseLine request, response;
    TWLeasePublication requestPublication, responsePublication;
} TWLeaseControl;
typedef struct { unsigned int epoch, ticket; } TWLeaseToken;
typedef struct {
    TWLeaseLine key;
    unsigned int nextTicket, leaseTicket, quiescentTicket, phase;
} TWLeasePpc;
typedef struct {
    TWLeaseLine key;
    unsigned int epoch, lastTicket, busy, resetMask, enabled;
} TWLeaseArm;

typedef char TWLeaseLineSize[sizeof(TWLeaseLine) == 32 ? 1 : -1];
typedef char TWLeasePublicationSize[sizeof(TWLeasePublication) == 32 ? 1 : -1];
typedef char TWLeaseControlSize[sizeof(TWLeaseControl) == 128 ? 1 : -1];
typedef char TWLeaseControlLines[
    __builtin_offsetof(TWLeaseControl, response) == 32 &&
    __builtin_offsetof(TWLeaseControl, requestPublication) == 64 &&
    __builtin_offsetof(TWLeaseControl, responsePublication) == 96 ? 1 : -1];
typedef char TWLeasePpcSize[sizeof(TWLeasePpc) == 48 ? 1 : -1];
typedef char TWLeaseArmSize[sizeof(TWLeaseArm) == 52 ? 1 : -1];

TW_LEASE_INLINE void TWLeaseBlank(TWLeaseLine *line, unsigned int epoch, unsigned int phase)
{
    line->magic = TW_LEASE_MAGIC; line->epoch = epoch; line->ticket = 0;
    line->owner = TW_OWNER_NONE; line->phase = phase;
    line->seq = line->session = line->command = 0;
}
TW_LEASE_INLINE int TWLeaseSame(const TWLeaseLine *a, const TWLeaseLine *b)
{
    return a->magic == TW_LEASE_MAGIC && b->magic == TW_LEASE_MAGIC &&
        a->epoch == b->epoch && a->ticket == b->ticket && a->owner == b->owner &&
        a->seq == b->seq && a->session == b->session && a->command == b->command;
}
TW_LEASE_INLINE int TWLeaseOwned(const TWLeasePpc *p, TWLeaseToken token)
{
    return p->key.epoch == token.epoch && p->leaseTicket == token.ticket &&
        token.ticket && p->key.owner != TW_OWNER_NONE;
}
TW_LEASE_INLINE int TWLeaseQuiet(const TWLeasePpc *p, const TWLeaseControl *c)
{
    return c->response.magic == TW_LEASE_MAGIC && c->response.epoch == p->key.epoch &&
        c->response.ticket == p->quiescentTicket &&
        (c->response.phase == TW_WIRE_READY || c->response.phase == TW_WIRE_DONE);
}

/* Reset calls require the PPC to be parked before either worker is retired. */
TW_LEASE_INLINE void TWLeaseResetBegin(TWLeaseArm *a, TWLeaseControl *c)
{
    a->enabled = 0; a->resetMask = 3;
    TWLeaseBlank(&c->response, a->epoch, TW_WIRE_DRAINING);
}
TW_LEASE_INLINE int TWLeaseRetired(TWLeaseArm *a, unsigned int owner, int quiescent)
{
    if (!quiescent || owner < TW_OWNER_GHOST || owner > TW_OWNER_STATE || !a->resetMask) return 0;
    a->resetMask &= ~(1u << (owner - 1u));
    return 1;
}
TW_LEASE_INLINE int TWLeaseResetPublish(TWLeaseArm *a, TWLeaseControl *c)
{
    if (a->enabled || a->resetMask || a->epoch == 0xffffffffu ||
        c->response.phase != TW_WIRE_DRAINING) return 0;
    ++a->epoch; a->busy = a->lastTicket = 0;
    TWLeaseBlank(&a->key, a->epoch, TW_WIRE_CAPABLE);
    a->key.command = SUSAMUNE_TRANSFER_RUNTIME_ABI;
    c->response = a->key;
    return 1;
}
TW_LEASE_INLINE int TWLeaseAttach(TWLeasePpc *p, TWLeaseControl *c)
{
    if (p->phase != TW_PPC_DETACHED || c->response.magic != TW_LEASE_MAGIC || !c->response.epoch ||
        c->response.phase != TW_WIRE_CAPABLE || c->response.ticket || c->response.owner ||
        c->response.command != SUSAMUNE_TRANSFER_RUNTIME_ABI) return 0;
    TWLeaseBlank(&p->key, c->response.epoch, TW_WIRE_ACTIVATE);
    p->key.command = SUSAMUNE_TRANSFER_RUNTIME_ABI;
    p->nextTicket = p->leaseTicket = p->quiescentTicket = 0;
    p->phase = TW_PPC_ATTACHING; c->request = p->key;
    return 1;
}
/* Both workers: closed handles, no accepted work or pending buffer access.
 * Shared-map selection and old-doorbell retirement precede READY publication. */
TW_LEASE_INLINE int TWLeaseActivate(TWLeaseArm *a, TWLeaseControl *c,
                                  int ghostQuiet, int stateQuiet)
{
    if (a->enabled || a->busy || a->resetMask || !ghostQuiet || !stateQuiet ||
        c->response.phase != TW_WIRE_CAPABLE || c->request.phase != TW_WIRE_ACTIVATE ||
        !TWLeaseSame(&a->key, &c->request)) return 0;
    a->enabled = 1;
    TWLeaseBlank(&c->response, a->epoch, TW_WIRE_READY);
    c->response.command = SUSAMUNE_TRANSFER_RUNTIME_ABI;
    return 1;
}
TW_LEASE_INLINE int TWLeaseAttached(TWLeasePpc *p, const TWLeaseControl *c)
{
    if (p->phase != TW_PPC_ATTACHING || c->response.phase != TW_WIRE_READY ||
        !TWLeaseSame(&p->key, &c->response)) return 0;
    p->phase = TW_PPC_IDLE;
    return 1;
}
TW_LEASE_INLINE int TWLeaseClaim(TWLeasePpc *p, TWLeaseControl *c,
                               unsigned int owner, TWLeaseToken *token)
{
    if (p->phase != TW_PPC_IDLE || owner < TW_OWNER_GHOST || owner > TW_OWNER_STATE ||
        p->nextTicket == 0xffffffffu || !TWLeaseQuiet(p, c)) return 0;
    TWLeaseBlank(&p->key, p->key.epoch, TW_WIRE_LOCAL);
    p->key.ticket = p->leaseTicket = ++p->nextTicket;
    p->key.owner = owner; p->phase = TW_PPC_LOCAL;
    token->epoch = p->key.epoch; token->ticket = p->leaseTicket;
    c->request = p->key;
    return 1;
}
/* Payload and legacy request flushes complete before this doorbell is flushed. */
TW_LEASE_INLINE int TWLeaseSubmit(TWLeasePpc *p, TWLeaseControl *c, TWLeaseToken token,
                                unsigned int seq, unsigned int session, unsigned int command)
{
    if (p->phase != TW_PPC_LOCAL || !TWLeaseOwned(p, token) || !seq || !command ||
        p->nextTicket == 0xffffffffu || !TWLeaseQuiet(p, c)) return 0;
    p->key.ticket = ++p->nextTicket; p->key.seq = seq;
    p->key.session = session; p->key.command = command;
    p->key.phase = TW_WIRE_ARM; p->phase = TW_PPC_REMOTE;
    c->request = p->key;
    return 1;
}
TW_LEASE_INLINE int TWLeaseCancel(TWLeasePpc *p, TWLeaseControl *c, TWLeaseToken token,
                                int commandCancellable)
{
    if (!commandCancellable || p->phase != TW_PPC_REMOTE || !TWLeaseOwned(p, token)) return 0;
    p->key.phase = TW_WIRE_CANCEL; c->request = p->key;
    return 1;
}
/* Every worker dispatch checks this gate; idle legacy doorbells are insufficient. */
TW_LEASE_INLINE int TWLeaseStart(TWLeaseArm *a, const TWLeaseControl *c,
                               unsigned int owner, unsigned int seq,
                               unsigned int session, unsigned int command)
{
    const TWLeaseLine *q = &c->request;
    if (!a->enabled || a->busy || a->resetMask || q->magic != TW_LEASE_MAGIC ||
        q->epoch != a->epoch || !q->ticket || q->ticket <= a->lastTicket ||
        (q->phase != TW_WIRE_ARM && q->phase != TW_WIRE_CANCEL) ||
        q->owner != owner || owner < TW_OWNER_GHOST || owner > TW_OWNER_STATE ||
        !seq || !command || q->seq != seq || q->session != session || q->command != command) return 0;
    a->key = *q; a->lastTicket = q->ticket; a->busy = 1;
    return 1;
}
TW_LEASE_INLINE int TWLeaseCancelRequested(const TWLeaseArm *a, const TWLeaseControl *c)
{
    return a->busy && c->request.phase == TW_WIRE_CANCEL && TWLeaseSame(&a->key, &c->request);
}
/* Flush payload + complete legacy receipt first. DONE certifies BOTH workers,
 * including error/close paths; it never means only "this FAT call returned". */
TW_LEASE_INLINE int TWLeaseFinish(TWLeaseArm *a, TWLeaseControl *c, TWLeaseToken token,
                                int ghostQuiet, int stateQuiet, int receiptPublished)
{
    if (!a->enabled || !a->busy || a->resetMask || !ghostQuiet || !stateQuiet ||
        !receiptPublished || token.epoch != a->key.epoch || token.ticket != a->key.ticket) return 0;
    c->response = a->key; c->response.phase = TW_WIRE_DONE;
    a->busy = 0;
    return 1;
}
TW_LEASE_INLINE int TWLeasePoll(TWLeasePpc *p, const TWLeaseControl *c)
{
    if (p->phase != TW_PPC_REMOTE || c->response.phase != TW_WIRE_DONE ||
        !TWLeaseSame(&p->key, &c->response)) return 0;
    p->quiescentTicket = p->key.ticket; p->phase = TW_PPC_RESULT;
    return 1;
}
TW_LEASE_INLINE int TWLeaseTake(TWLeasePpc *p, TWLeaseToken *borrow)
{
    if (p->phase != TW_PPC_RESULT) return 0;
    borrow->epoch = p->key.epoch; borrow->ticket = p->key.ticket;
    p->phase = TW_PPC_BORROWED;
    return 1;
}
TW_LEASE_INLINE int TWLeaseConsumed(TWLeasePpc *p, TWLeaseControl *c, TWLeaseToken borrow)
{
    if (p->phase != TW_PPC_BORROWED || borrow.epoch != p->key.epoch ||
        borrow.ticket != p->key.ticket || c->response.phase != TW_WIRE_DONE ||
        !TWLeaseSame(&p->key, &c->response)) return 0;
    p->phase = TW_PPC_LOCAL; p->key.phase = TW_WIRE_LOCAL; c->request = p->key;
    return 1;
}
TW_LEASE_INLINE int TWLeaseRelease(TWLeasePpc *p, TWLeaseControl *c, TWLeaseToken token)
{
    if (p->phase != TW_PPC_LOCAL || !TWLeaseOwned(p, token) ||
        !TWLeaseQuiet(p, c)) return 0;
    p->phase = TW_PPC_IDLE; p->key.owner = TW_OWNER_NONE;
    p->leaseTicket = 0; c->request = p->key;
    return 1;
}
#endif
