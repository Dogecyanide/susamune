#ifndef GHOST_SERVICE_TLS_H
#define GHOST_SERVICE_TLS_H
#include "bearssl.h"
#include "GhostServiceHttp.h"
struct GhostTls {
    br_ssl_client_context client;
    br_x509_minimal_context cert;
    unsigned char records[BR_SSL_BUFSIZE_MONO];
    struct GhostHttp http;
    char request[1024];
    unsigned active;
};
struct GhostTlsIo {
    void *context;
    int (*send)(void *, const void *, unsigned);
    int (*recv)(void *, void *, unsigned);
    int (*wait)(void *);
    int (*sink)(void *, const void *, unsigned);
};
struct GhostTlsRequest {
    const char *method, *headers;
    const void *body;
    unsigned bytes;
};
int GhostTlsRequest(struct GhostTls *, const struct GhostTlsIo *, const char *,
    const struct GhostTlsRequest *, void *, unsigned, unsigned *, unsigned, const unsigned char[32]);
/* IO: positive byte count, zero would-block, negative error. Peer EOF is an error. */
int GhostTlsGet(struct GhostTls *, const struct GhostTlsIo *, const char *path,
    void *output, unsigned capacity, unsigned *used, unsigned unixTime,
    const unsigned char entropy[32]);
#endif
