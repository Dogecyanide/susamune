#include "GhostTraceReadStorage.h"
#if MOONSHINE_GHOST_TRACE
#include "global.h"
#include "susamune/ghost_trace_stream_native.h"
#include <string.h>

int GhostTraceReadStorageWindow(unsigned channel,unsigned nonce,unsigned lease,struct GhostTraceReadWindow *window) {
    const struct MoonshineGhostMemoryProof *proof=(const void*)MOONSHINE_GHOST_PROOF_PHYS_BASE;
    const volatile struct MsTraceMailbox *writer=(const void*)MS_TRACE_CONTROL_PHYS;
    const volatile struct MsTraceReadMailbox *box;
    const volatile struct MsTraceReadGrant *source;
    struct MsTraceReadGrant grant;
    struct MsTraceReadRequest request;
    struct MsTraceReadBuffer buffer;
    if(channel>=MS_TRACE_READ_CHANNELS || !nonce || !lease || !window)return 0;
    sync_before_read((void*)proof,sizeof(*proof));
    if(!MoonshineGhostMemoryProofValid(proof,proof->word[MGM_GAME]) || proof->word[MGM_NONCE]!=nonce)return 0;
    sync_before_read((void*)writer,sizeof(*writer));
    if(writer->response.magic!=MS_TRACE_MAGIC || writer->response.version!=MS_TRACE_VERSION ||
       writer->response.nonce!=nonce || writer->request.sequence!=writer->response.ackRequest ||
       (writer->response.phase!=MS_TRACE_IDLE && writer->response.phase!=MS_TRACE_SAVED &&
        writer->response.phase!=MS_TRACE_DISCARDED))return 0;
    box=(const void*)MS_TRACE_READ_MAILBOX_PHYS(channel);
    source=(const void*)MS_TRACE_STREAM_GRANT_PHYS(channel);
    sync_before_read((void*)box,64);sync_before_read((void*)source,32);
    memcpy(&grant,(const void*)source,sizeof(grant));
    memcpy(&request,(const void*)&box->request,sizeof(request));
    memcpy(&buffer,(const void*)&box->buffer,sizeof(buffer));
    if(grant.lease!=lease || !MsTraceReadGrantValid(&grant,&request,&buffer,nonce))return 0;
    window->physical=grant.physical;window->bytes=grant.bytes;return 1;
}
#endif
