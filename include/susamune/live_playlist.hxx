#pragma once

namespace LivePlaylist {
enum { Capacity = 120, ChunkItems = 24, HeaderBytes = 12, Message = 10 };
struct Item { unsigned char entry, episode; }; // High bit: preset route action.
struct Plan {
    Item items[Capacity];
    unsigned char count, fastAny;
};
struct Transfer {
    Plan plan;
    unsigned hash;
    unsigned char received;
    bool complete;
};
unsigned hash(const Plan &);
unsigned encode(const Plan &, unsigned offset, unsigned char *out);
bool receive(Transfer &, const unsigned char *, unsigned bytes, unsigned expectedHash,
             unsigned entryCount);
}
