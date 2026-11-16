#ifndef GHOST_SERVICE_JSON_H
#define GHOST_SERVICE_JSON_H
#include "susamune/ghost_service.h"
struct GhostJsonToken { unsigned short start, end, next; unsigned char type, reserved; };
struct GhostJson {
    const char *text;
    unsigned size, pos, count;
    struct GhostJsonToken tokens[2048];
};
int GhostServiceParsePage(struct GhostJson *, const void *, unsigned, struct GhostServicePage *);
int GhostServicePathValid(const char *);
int GhostServiceEntryValid(const struct GhostServiceEntry *);
int GhostServiceRouteSortSupported(struct GhostJson *, const void *, unsigned);
int GhostJsonParse(struct GhostJson *, const void *, unsigned);
unsigned GhostJsonField(struct GhostJson *, unsigned, const char *);
int GhostJsonString(struct GhostJson *, unsigned, char *, unsigned, int);
int GhostJsonInteger(struct GhostJson *, unsigned, unsigned *);
#endif
