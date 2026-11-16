#ifndef MOONSHINE_ISO_CACHE_BANKS_H
#define MOONSHINE_ISO_CACHE_BANKS_H

/* Extra rows come only from the shared physical-owner map. A matching mod
 * must also be admitted before ISOSetupCache; older mods keep the old bank. */
#ifndef NIN_MEM2_DISC_CACHE_EXTRA_BANKS
#define NIN_MEM2_DISC_CACHE_EXTRA_BANKS(X)
#define NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID 0u
#else
#if !defined(NIN_MEM2_DISC_CACHE_EXTRA_OWNERS_RETIRED) || NIN_MEM2_DISC_CACHE_EXTRA_OWNERS_RETIRED != 1
#error Extra disc cache requires retirement of every former owner
#endif
#if !defined(NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID) || NIN_MEM2_DISC_CACHE_EXTRA_LAYOUT_ID == 0
#error Extra disc cache requires a matching mod layout identity
#endif
#endif

#define ISO_CACHE_BANK_MAX 8u
#define ISO_CACHE_EXTRA_MAX 0x1FD000u /* 1.5 MiB plus the conditional 500 KiB. */
typedef __UINTPTR_TYPE__ ISOCacheAddress;
typedef struct { u8 *data; u32 size; } ISOCacheBank;
typedef struct {
    ISOCacheBank bank[ISO_CACHE_BANK_MAX];
    u32 count, current, offset, largest;
} ISOCacheBanks;

static inline int ISOCacheRangeValid(const u8 *data, u32 size)
{
    const ISOCacheAddress start = (ISOCacheAddress)data;
    return start && size && !(start & 31u) && !(size & 31u) &&
        size <= (ISOCacheAddress)-1 - start;
}

static inline int ISOCacheOverlap(const u8 *a, u32 an, const u8 *b, u32 bn)
{
    const ISOCacheAddress av = (ISOCacheAddress)a, bv = (ISOCacheAddress)b;
    return an && bn && (av <= bv ? bv - av < an : av - bv < bn);
}

static inline int ISOCacheAddBank(ISOCacheBanks *banks, u8 *data, u32 size)
{
    u32 i;
    if (banks->count >= ISO_CACHE_BANK_MAX || !ISOCacheRangeValid(data, size)) return 0;
    for (i = 0; i < banks->count; ++i)
        if (ISOCacheOverlap(data, size, banks->bank[i].data, banks->bank[i].size)) return 0;
    banks->bank[banks->count].data = data;
    banks->bank[banks->count++].size = size;
    if (size > banks->largest) banks->largest = size;
    return 1;
}

static inline u8 *ISOCacheTake(ISOCacheBanks *banks, u32 length)
{
    u32 tried;
    if (!length || length > banks->largest) return 0;
    for (tried = 0; tried <= banks->count; ++tried) {
        const ISOCacheBank *bank = &banks->bank[banks->current];
        const u32 aligned = (banks->offset + 31u) & ~31u;
        if (aligned >= banks->offset && aligned <= bank->size && length <= bank->size - aligned) {
            banks->offset = aligned + length;
            return bank->data + aligned;
        }
        banks->current = (banks->current + 1u) % banks->count;
        banks->offset = 0;
    }
    return 0;
}

/* Caller has verified this layout in the loaded mod, and holds DI quiescent.
 * Admission lasts until ISOClose/ISOInit: no other owner may reclaim a bank. */
int ISOAdmitExtraCache(u32 layout);
#endif
