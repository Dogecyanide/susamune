#ifndef SUSAMUNE_TRANSFER_PUBLICATION_H
#define SUSAMUNE_TRANSFER_PUBLICATION_H
#include "transfer_lease.h"

/* Cache operations must complete before their following barrier returns. */
typedef struct {
    unsigned int (*load)(const volatile unsigned int *word);
    void (*store)(volatile unsigned int *word, unsigned int value);
    void (*flush)(volatile void *line, unsigned int size);
    void (*invalidate)(volatile void *line, unsigned int size);
    void (*barrier)(void);
} TWLeasePublicationIo;

typedef struct { unsigned int issued; } TWLeasePublisher;
typedef char TWLeasePublisherSize[sizeof(TWLeasePublisher) == 4 ? 1 : -1];

/* Resume only with this writer stopped; the opposite processor never writes
 * either line. The durable high-water mark survives a withdrawn publication. */
TW_LEASE_INLINE int TWLeasePublicationResume(TWLeasePublisher *writer,
    volatile TWLeasePublication *publication, const TWLeasePublicationIo *io)
{
    unsigned int committed, issued;
    io->invalidate(publication, 32); io->barrier();
    committed = io->load(&publication->generation);
    issued = io->load(&publication->issued);
    if (committed && committed != issued) return 0;
    writer->issued = issued;
    return 1;
}

/* All wire pointers identify distinct aligned cache lines. draft is private.
 * Flush completion means writes reached shared RAM before the next step. */
TW_LEASE_INLINE int TWLeasePublicationWrite(TWLeasePublisher *writer,
    volatile TWLeaseLine *body, volatile TWLeasePublication *publication,
    const TWLeaseLine *draft, const TWLeasePublicationIo *io)
{
    unsigned int i, generation;
    volatile unsigned int *destination = (volatile unsigned int *)body;
    const unsigned int *source = (const unsigned int *)draft;
    if (writer->issued == 0xffffffffu) return 0;
    generation = ++writer->issued;
    io->store(&publication->generation, 0);
    io->store(&publication->issued, generation);
    io->flush(publication, 32); io->barrier();
    for (i = 0; i < 8; ++i) io->store(destination + i, source[i]);
    io->flush(body, 32); io->barrier();
    io->store(&publication->generation, generation);
    io->flush(publication, 32); io->barrier();
    return 1;
}

/* Never retain a prior accepted snapshot when this read fails. */
TW_LEASE_INLINE int TWLeasePublicationRead(TWLeaseLine *snapshot,
    volatile TWLeaseLine *body, volatile TWLeasePublication *publication,
    const TWLeasePublicationIo *io)
{
    TWLeaseLine candidate;
    unsigned int i, first, last;
    unsigned int *target = (unsigned int *)&candidate;
    const volatile unsigned int *source = (const volatile unsigned int *)body;
    io->invalidate(publication, 32); io->barrier();
    first = io->load(&publication->generation);
    if (!first) { TWLeaseBlank(snapshot, 0, 0); return 0; }
    io->invalidate(body, 32); io->barrier();
    for (i = 0; i < 8; ++i) target[i] = io->load(source + i);
    io->invalidate(publication, 32); io->barrier();
    last = io->load(&publication->generation);
    if (!last || last != first) { TWLeaseBlank(snapshot, 0, 0); return 0; }
    *snapshot = candidate;
    return 1;
}
#endif
