#ifndef GHOST_SERVICE_ACCOUNT_H
#define GHOST_SERVICE_ACCOUNT_H
#include "GhostServiceTls.h"
#include "GhostServiceJson.h"
/* Backend-private credentials. Never copy them into a UI mailbox or a log. */
struct GhostAccountSecret { char access[48], refresh[48], user[48]; };
struct GhostAccount {
    struct GhostAccountSecret secret;
    char device[48], code[12];
    unsigned expires, nextPoll, interval, changed;
};
struct GhostAccountWork {
    struct GhostJson *json;
    char *response;
    unsigned capacity;
    char body[768], headers[256], path[160];
    struct GhostServiceUpload upload;
    struct GhostTlsRequest request;
    const char *clientName;
};
struct GhostAccountFlow {
    unsigned step, now, bytes;
    const void *ghost;
    char hash[65], uploadId[37];
};
/* 1 means a prepared HTTP request; 0 or a negative status completes the operation. */
int GhostAccountBegin(struct GhostAccount *,struct GhostAccountWork *,struct GhostAccountFlow *,
    unsigned op,unsigned now,const void *ghost,unsigned bytes);
int GhostAccountNext(struct GhostAccount *,struct GhostAccountWork *,struct GhostAccountFlow *,
    int transport,unsigned used,unsigned status);
typedef int (*GhostAccountHttp)(const char *, const struct GhostTlsRequest *, void *, unsigned, unsigned *, unsigned *);
int GhostAccountRun(struct GhostAccount *, struct GhostAccountWork *, unsigned op,
    unsigned now, const void *ghost, unsigned bytes, GhostAccountHttp);
void GhostAccountInfo(const struct GhostAccount *, unsigned now, struct GhostServiceAccountInfo *);
int GhostAccountSecretValid(const struct GhostAccountSecret *);
#endif
