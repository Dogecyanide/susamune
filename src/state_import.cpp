#include "susamune/state_import.hxx"

namespace StateImport {
namespace {
enum { UNKNOWN = 2, FAILED = 3 };
bool independent(const StateStore::Store &s, const void *data, unsigned int size) {
    return TWSExternal(s.memory, data, size) &&
        TWQuickSeparate(data, size, &s, sizeof(s)) &&
        TWQuickSeparate(data, size, s.memory, sizeof(*s.memory)) &&
        TWQuickSeparate(data, size, s.memory->pool, sizeof(*s.memory->pool)) &&
        (!s.nativeScratch || TWQuickSeparate(data, size, s.nativeScratch, s.nativeBytes));
}
bool current(const StateStore::Store &s, const Cursor &c) {
    const TWChunkSlot &root = TWChunkDirectory(s.memory->pool)->slots[3];
    const unsigned int packed = root.count ? root.packedBytes : c.kind == StateStore::QUICK ? 8 : 0;
    return s.pending && !s.sealed && !s.pin && c.kind <= UNKNOWN &&
        c.total && c.total <= 0x2000000u && c.offset < c.total && c.offset == packed &&
        (!root.count || TWChunkKind(TWChunkDirectory(s.memory->pool), &root) == c.kind) &&
        c.transaction.epoch == s.transaction.epoch &&
        c.transaction.sequence == s.transaction.sequence &&
        c.transaction.slot == s.transaction.slot &&
        c.transaction.generation == s.transaction.generation &&
        c.transaction.tag == s.transaction.tag && TWSTokenMatches(s.memory, c.transaction);
}
Status fail(Cursor &c, Status status) {
    c.kind = FAILED;
    return status;
}
}

bool begin(const StateStore::Store &s, Cursor &c, unsigned int packedBytes) {
    if (!packedBytes || packedBytes > 0x2000000u || !StateStore::valid(s) ||
        !s.pending || s.sealed || s.pin || !independent(s, &c, sizeof(c)) ||
        TWChunkDirectory(s.memory->pool)->slots[3].count) return false;
    c = {s.transaction, packedBytes, 0, UNKNOWN};
    return true;
}

Status append(StateStore::Store &s, Cursor &c, const void *bytes, unsigned int size) {
    if (!StateStore::valid(s) || !independent(s, &c, sizeof(c)) || !current(s, c) || !bytes || !size ||
        size > c.total - c.offset || !independent(s, bytes, size) ||
        !TWQuickSeparate(bytes, size, &c, sizeof(c))) return INVALID;
    const unsigned char *p = static_cast<const unsigned char *>(bytes);
    unsigned int used = 0;
    if (c.kind == UNKNOWN) {
        if (size < 8) return fail(c, INVALID);
        if (SusamuneStateExportWord(p) == 0x4d534c34u) {
            if (SusamuneStateExportWord(p + 4) != TW_CHUNK_RAW_BYTES || c.total <= 8)
                return fail(c, INVALID);
            c.kind = StateStore::QUICK;
            used = 8;
        } else {
            const unsigned int prefix = (static_cast<unsigned int>(p[0]) << 8) | p[1];
            if ((p[0] & 15u) != 8 || (p[0] >> 4) > 7 || (p[1] & 32u) || prefix % 31u)
                return fail(c, INVALID);
            c.kind = StateStore::DEFLATE;
        }
    }
    while (used < size) {
        const unsigned int remaining = size - used;
        if (c.kind == StateStore::QUICK) {
            if (remaining < 8) break;
            const unsigned int payload = SusamuneStateExportWord(p + used + 4) & 0x7fffffffu;
            if (!payload || payload > TW_CHUNK_RAW_BYTES) return fail(c, INVALID);
            const unsigned int block = payload + 8;
            if (block > remaining) break;
            if (!SusamuneStateExportBlockRaw(p + used, block, c.offset + used + block == c.total))
                return fail(c, INVALID);
            if (!StateStore::appendQuick(s, p + used, 8, p + used + 8, payload))
                return fail(c, FULL);
            used += block;
        } else {
            const unsigned int part = remaining < TW_CHUNK_RAW_BYTES ? remaining : TW_CHUNK_RAW_BYTES;
            if (!StateStore::appendOpaque(s, p + used, part)) return fail(c, FULL);
            used += part;
        }
    }
    if (!used || (size == c.total - c.offset && used != size)) return fail(c, INVALID);
    c.offset += used;
    return c.offset == c.total ? COMPLETE : MORE;
}
}
