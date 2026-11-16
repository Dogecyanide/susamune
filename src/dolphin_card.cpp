#include "susamune/dolphin_card.hxx"
#if IS_EMULATOR
#include <Dolphin/mem.h>
#include "susamune/addresses.hxx"

namespace DolphinCard {
namespace {
#if defined(SUSAMUNE_VERSION_JP)
constexpr u32 kGet=0x8009fb94,kPut=0x8009fc4c,kDir=0x800a1730,
              kUpdate=0x800a18d0,kSync=0x8009fe00,kCallback=0x8009ec50;
#elif defined(SUSAMUNE_VERSION_US)
constexpr u32 kGet=0x80355274,kPut=0x8035532c,kDir=0x80356e10,
              kUpdate=0x80356fb0,kSync=0x803554e0,kCallback=0x80354330;
#else
constexpr u32 kGet=0x8034d494,kPut=0x8034d54c,kDir=0x8034f030,
              kUpdate=0x8034f1d0,kSync=0x8034d700,kCallback=0x8034c550;
#endif
s32 acquire(void **card){return reinterpret_cast<s32(*)(s32,void **)>(kGet)(CARD_SLOTB,card);}
s32 release(void *card,s32 result){return reinterpret_cast<s32(*)(void *,s32)>(kPut)(card,result);}
CARDDirEntry *directory(void *card){return reinterpret_cast<CARDDirEntry *(*)(void *)>(kDir)(card);}
s32 publish(){return reinterpret_cast<s32(*)(s32,CARDCallback)>(kUpdate)(CARD_SLOTB,reinterpret_cast<CARDCallback>(kCallback));}
s32 wait(){return reinterpret_cast<s32(*)(s32)>(kSync)(CARD_SLOTB);}
}
s32 remove(const char *name) {
    CARDFileInfo file;
    s32 result=CARDOpen(CARD_SLOTB,name,&file);
    if(result<0)return result;
    CARDStat stat;
    result=CARDGetStatus(CARD_SLOTB,file.mFileNo,&stat);
    const s32 index=file.mFileNo,closed=CARDClose(&file);
    if(result<0)return result;
    if(closed<0)return closed;
    const u32 game=0x474d5300u|(SUSAMUNE_GAME_VERSION==1?'J':SUSAMUNE_GAME_VERSION==2?'E':'P');
    if(index<0 || index>=127 || stat.mGameCode!=game || stat.mCompany!=0x5355)
        return CARD_ERROR_NOPERM;
    void *card=nullptr;
    result=acquire(&card);if(result<0)return result;
    CARDDirEntry *entry=directory(card)+index;
    if(entry->mGameCode!=game || entry->mCompany!=0x5355 || memcmp(entry->mFilename,stat.mFilename,32))
        return release(card,CARD_ERROR_NOPERM);
    static_assert(sizeof(CARDDirEntry)==64,"retail directory stride");
    // Publish the removed name first. CARDCheck reclaims orphan blocks, including
    // after interruption between these two independently checksummed commits.
    memset(entry,0xff,sizeof(*entry));
    result=publish();
    if(result<0)return release(card,result);
    result=wait();
    return result<0?result:CARDCheck(CARD_SLOTB);
}
}
#endif
