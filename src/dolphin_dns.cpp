#include "susamune/dolphin_dns.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
namespace DolphinDns {
namespace {
unsigned word(const unsigned char *p) { return unsigned(p[0]) << 8 | p[1]; }
void put(unsigned char *p, unsigned n) { p[0] = n >> 8; p[1] = n; }
char lower(unsigned char c) { return c >= 'A' && c <= 'Z' ? c + ('a' - 'A') : c; }
bool equal(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}
bool nameAt(const unsigned char *packet, unsigned bytes, unsigned &cursor, char *out) {
    unsigned pos = cursor, used = 0, jumps = 0;
    bool jumped = false;
    while (pos < bytes) {
        const unsigned start = pos, length = packet[pos++];
        if ((length & 0xc0) == 0xc0) {
            if (pos == bytes || ++jumps > 16) return false;
            const unsigned target = ((length & 63) << 8) | packet[pos++];
            // Compression only references earlier wire data; cycles cannot advance.
            if (target < 12 || target >= start) return false;
            if (!jumped) cursor = pos;
            jumped = true; pos = target;
        } else {
            if (length > 63 || length > bytes - pos) return false;
            if (!length) {
                if (!jumped) cursor = pos;
                out[used] = 0;
                return true;
            }
            if (used && used < NAME_BYTES - 1) out[used++] = '.';
            if (used + length >= NAME_BYTES) return false;
            for (unsigned i = 0; i < length; ++i) {
                const unsigned char c = packet[pos++];
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '-')) return false;
                out[used++] = lower(c);
            }
        }
    }
    return false;
}
struct Record { unsigned type, klass, payload, length; };
bool recordAt(const unsigned char *p, unsigned bytes, unsigned &cursor,
              char *owner, Record &record) {
    if (!nameAt(p, bytes, cursor, owner) || bytes - cursor < 10) return false;
    record.type = word(p + cursor); record.klass = word(p + cursor + 2);
    record.length = word(p + cursor + 8); cursor += 10;
    record.payload = cursor;
    if (record.length > bytes - cursor) return false;
    cursor += record.length;
    return true;
}
}
bool normalize(const char *source, char *destination) {
    if (!source || !destination) return false;
    unsigned label = 0;
    for (unsigned i = 0; i < NAME_BYTES; ++i) {
        const unsigned char c = source[i];
        if (!c) { destination[i] = 0; return label && destination[i - 1] != '-'; }
        if (i == NAME_BYTES - 1) return false;
        if (c == '.') {
            if (!label || destination[i - 1] == '-') return false;
            label = 0;
        } else {
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '-') || (!label && c == '-') ||
                ++label > 63) return false;
        }
        destination[i] = lower(c);
    }
    return false;
}
unsigned query(unsigned char *out, unsigned capacity, const char *name, unsigned id) {
    char normalized[NAME_BYTES];
    if (!out || capacity < QUERY_BYTES || !normalize(name, normalized)) return 0;
    for (unsigned i = 0; i < 12; ++i) out[i] = 0;
    put(out, id); put(out + 2, 0x0100); put(out + 4, 1);
    unsigned cursor = 12, start = 0;
    do {
        unsigned length = 0;
        while (normalized[start + length] && normalized[start + length] != '.') ++length;
        out[cursor++] = length;
        for (unsigned i = 0; i < length; ++i) out[cursor++] = normalized[start + i];
        start += length;
    } while (normalized[start] && ++start);
    out[cursor++] = 0; put(out + cursor, 1); put(out + cursor + 2, 1);
    return cursor + 4;
}
Answer answer(const unsigned char *p, unsigned bytes, const char *name,
              unsigned id, unsigned *address) {
    if (!p || !address || bytes < 12 || bytes > 512 || word(p) != id ||
        (word(p + 2) & 0xf800) != 0x8000 || word(p + 4) != 1) return IGNORE;
    char expected[NAME_BYTES], owner[NAME_BYTES];
    unsigned cursor = 12;
    if (!normalize(name, expected) || !nameAt(p, bytes, cursor, owner) ||
        !equal(expected, owner) || bytes - cursor < 4 ||
        word(p + cursor) != 1 || word(p + cursor + 2) != 1) return IGNORE;
    cursor += 4;
    if (word(p + 2) & 0x0200) return TRUNCATED;
    if (word(p + 2) & 15) return NOT_FOUND;
    const unsigned count = word(p + 6), begin = cursor;
    if (count > 32) return IGNORE;
    Record record;
    // Validate the entire answer section before accepting an earlier address.
    for (unsigned i = 0; i < count; ++i)
        if (!recordAt(p, bytes, cursor, owner, record)) return IGNORE;
    for (unsigned hop = 0; hop < 8; ++hop) {
        cursor = begin;
        bool alias = false;
        for (unsigned i = 0; i < count; ++i) {
            if (!recordAt(p, bytes, cursor, owner, record)) return IGNORE;
            if (record.klass != 1 || !equal(expected, owner)) continue;
            if (record.type == 1 && record.length == 4) {
                const unsigned char *ip = p + record.payload;
                const unsigned value = word(ip) << 16 | word(ip + 2);
                if (!ip[0] || ip[0] == 127 || ip[0] >= 224 || value == 0xffffffffu) return IGNORE;
                *address = value; return ADDRESS;
            }
            if (record.type == 5) {
                unsigned at = record.payload;
                if (!nameAt(p, bytes, at, owner) || at != record.payload + record.length ||
                    !normalize(owner, expected)) return IGNORE;
                alias = true; break;
            }
        }
        if (!alias) return NOT_FOUND;
    }
    return IGNORE;
}
}
#endif
