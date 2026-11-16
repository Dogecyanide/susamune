#ifndef GHOST_SERVICE_HTTP_H
#define GHOST_SERVICE_HTTP_H
#include <stddef.h>

/* Incremental framing, including chunked JSON responses. Never follows redirects. */
struct GhostHttp {
    unsigned char *body;
    unsigned capacity, used, status, state, left, headers, lineSize;
    unsigned hasLength, chunked, encoding, trailer, complete, error;
    unsigned close, responseBytes, retryAfter, jsonResponse;
    char requestId[64], date[64], cfRay[64], serverTiming[96];
    char retryDate[64];
    char line[1024];
    void *sinkContext;
    int (*sink)(void *, const void *, unsigned);
};
void GhostHttpInit(struct GhostHttp *, void *, unsigned);
int GhostHttpFeed(struct GhostHttp *, const void *, unsigned);
unsigned GhostHttpRetryDelay(const struct GhostHttp *, unsigned now);
#endif
