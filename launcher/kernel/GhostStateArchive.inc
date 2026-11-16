/* State metadata is immutable until its matching receipt. Cache the exact reference. */
static void StateGhostReset(void) {
#if MOONSHINE_GHOST_TRACE
    GhostTraceStateReferenceReset();
#endif
}
static int StateGhostPrepare(const struct SusamuneStateArchiveHeader*h,unsigned project,unsigned id) {
#if MOONSHINE_GHOST_TRACE
    struct MsTraceStateReference reference;
    GhostTraceStateReferenceReset();
    if(!h->reserved[0])return 1;
    if(!SusamuneStateReferenceHeaderValid(h))return 0;
    memcpy(&reference,STATE_MAILBOX->metadata+h->reserved[1],sizeof(reference));
    return GhostTraceStateReferencePrepare(&reference,h->gameId,project,id,h->metadataCrc);
#else
    (void)project;(void)id;return !h->reserved[0];
#endif
}
static int StateGhostStore(void) {
#if MOONSHINE_GHOST_TRACE
    return GhostTraceStateReferenceStore();
#else
    return 1;
#endif
}
static int StateGhostRelease(void) {
#if MOONSHINE_GHOST_TRACE
    return GhostTraceStateReferenceRelease();
#else
    return 1;
#endif
}
static int StateGhostRecover(int begin) {
#if MOONSHINE_GHOST_TRACE
    return GhostTraceStateReferenceRecover(begin);
#else
    (void)begin;return 1;
#endif
}
static void StateGhostCancel(void) {
#if MOONSHINE_GHOST_TRACE
    GhostTraceStateReferenceCancel();
#endif
}
static int StateGhostIdle(void) {
#if MOONSHINE_GHOST_TRACE
    return !GhostTraceStateReferenceBusy();
#else
    return 1;
#endif
}

static FRESULT StateGhostRead(const char*path,unsigned project,unsigned id,const struct SusamuneStateArchiveHeader*expected) {
    FIL file;struct SusamuneStateArchiveHeader header;UINT done=0;FRESULT result;
    result=f_open_char(&file,path,FA_READ|FA_OPEN_EXISTING);
    if(result!=FR_OK)return result;
    result=f_read(&file,&header,sizeof(header),&done);
    if(result!=FR_OK||done!=sizeof(header)||!SusamuneStateHeaderValid(&header)||
       f_size(&file)!=sizeof(header)+header.metadataSize+header.packedSize||
       (expected&&memcmp(expected,&header,sizeof(header))))result=FR_DISK_ERR;
    if(result==FR_OK&&header.reserved[0]) {
        result=f_read(&file,STATE_MAILBOX->metadata,header.metadataSize,&done);
        sync_after_write(STATE_MAILBOX->metadata,header.metadataSize);
        if(result!=FR_OK||done!=header.metadataSize||
           SusamuneStateCrc(STATE_MAILBOX->metadata,header.metadataSize)!=header.metadataCrc)result=FR_DISK_ERR;
    }
    if(f_close(&file)!=FR_OK)result=FR_DISK_ERR;
    if(result==FR_OK&&!StateGhostPrepare(&header,project,id))result=FR_DISK_ERR;
    return result;
}
static FRESULT StateGhostUnlink(const char*path,unsigned project,unsigned id) {
    FRESULT result=StateGhostRead(path,project,id,0);
    if(result==FR_NO_FILE||result==FR_NO_PATH)return result;
    if(result!=FR_OK)return f_unlink_char(path); /* Unknown references remain pinned. */
    result=f_unlink_char(path);
    if(result==FR_OK&&!StateGhostRelease())result=FR_DISK_ERR;
    return result;
}
