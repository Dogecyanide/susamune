#ifndef SUSAMUNE_GHOST_SERVICE_H
#define SUSAMUNE_GHOST_SERVICE_H

#include "kana_text.h"

#define GHOST_SERVICE_HOST "cvadewafbthfhvzgdgay.supabase.co"
#define GHOST_SERVICE_API "/functions/v1/moonshine-api/v1"
#define GHOST_SERVICE_STORAGE "/storage/v1/object/public/ghosts/"
#define GHOST_SERVICE_PAGE_COUNT 4u
#define GHOST_SERVICE_CURSOR_SIZE 256u
#define GHOST_SERVICE_PAGE_MAGIC 0x47535731u
#define GHOST_SERVICE_WORK_SIZE 0x00020000u
#define GHOST_SERVICE_SESSION_SIZE 0x00007200u
#define GHOST_SERVICE_CAN_SORT_ROUTE 1u
#define GHOST_SERVICE_SORTED_ROUTE 2u

enum GhostServiceError {
    GHOST_SERVICE_NETWORK = -20, GHOST_SERVICE_TLS = -21,
    GHOST_SERVICE_CLOCK = -22, GHOST_SERVICE_RANDOM = -23,
    GHOST_SERVICE_RESPONSE = -24, GHOST_SERVICE_HASH = -25,
    GHOST_SERVICE_CANCELLED = -26, GHOST_SERVICE_TIMEOUT = -27,
    GHOST_SERVICE_STARTUP = -28, GHOST_SERVICE_DNS = -29,
    GHOST_SERVICE_RATE_LIMIT = -30, GHOST_SERVICE_UNAVAILABLE = -31,
    GHOST_SERVICE_SORT_UNSUPPORTED = -32, GHOST_SERVICE_LINK_REQUIRED = -33,
    GHOST_SERVICE_LINK_EXPIRED = -34, GHOST_SERVICE_UPLOAD_REJECTED = -35,
    GHOST_SERVICE_ACCOUNT_LIMIT = -36
};

enum GhostServicePhase {
    GHOST_WEB_STARTUP = 1, GHOST_WEB_DNS, GHOST_WEB_TCP,
    GHOST_WEB_TLS, GHOST_WEB_HTTP, GHOST_WEB_VALIDATE
};
struct GhostServiceTrace {
    unsigned int phase, elapsedMs, startupMs, connectMs, httpStatus, tlsError, reused, retryAfter;
    signed int result, iosError;
    unsigned int sentBytes, receivedBytes, lastIo, handshakeMs, processingMs, method;
    char path[768], requestId[64], date[64], cfRay[64], serverTiming[96];
};

struct GhostServiceEntry {
    char title[64], author[32], id[40], path[384];
    unsigned char sha256[32];
    unsigned int bytes, resultQf, durationQf;
};
struct GhostServicePage {
    unsigned int magic, count, total, reserved;
    char next[GHOST_SERVICE_CURSOR_SIZE];
    struct GhostServiceEntry entries[GHOST_SERVICE_PAGE_COUNT];
};
struct GhostServiceQuery {
    char cursor[GHOST_SERVICE_CURSOR_SIZE];
    unsigned int sortRoute;
    unsigned int filter; /* area+1, episode+1, picker entry+1 in successive bytes */
};
#define GHOST_SERVICE_ACCOUNT_MAGIC 0x47534131u
#define GHOST_SERVICE_DESCRIPTION_MAX 240u
struct GhostServiceUpload { char description[GHOST_SERVICE_DESCRIPTION_MAX + 1]; };
static inline int GhostServiceDescriptionValid(const char *s) {
    return MoonshineKanaValid(s, GHOST_SERVICE_DESCRIPTION_MAX + 1);
}
#define GHOST_ACCOUNT_STATUS 0u
#define GHOST_ACCOUNT_LINK 1u
#define GHOST_ACCOUNT_POLL 2u
#define GHOST_ACCOUNT_UNLINK 3u
#define GHOST_ACCOUNT_UPLOAD 4u
struct GhostServiceAccountInfo {
    unsigned int magic, linked, pending, retrySeconds;
    char code[12], user[48];
};

#endif
