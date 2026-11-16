#ifndef MOONSHINE_GHOST_RECORDING_MANIFEST_H
#define MOONSHINE_GHOST_RECORDING_MANIFEST_H
#include "susamune/ghost_format.h"
#define MS_RECORDING_MANIFEST_MAGIC 0x4d53474du
#define MS_RECORDING_MANIFEST_VERSION 1u
#define MS_RECORDING_MANIFEST_BYTES 256u
#define MS_RECORDING_CATALOG_VERSION 254u
#define MS_RECORDING_MODE 3u
#define MS_RECORDING_CODEC 2u
#define MS_RECORDING_SLOT_FLAG 8u
#define MS_RECORDING_FILE_LIMIT 0x7f000000u
static inline unsigned MsRecordingWord(const unsigned char*p){return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|p[3];}
static inline unsigned MsRecordingHalf(const unsigned char*p){return ((unsigned)p[0]<<8)|p[1];}
static inline void MsRecordingPut(unsigned char*p,unsigned n){p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=n;}
static inline unsigned MsRecordingCrc(const unsigned char*p){unsigned crc=~0u,i,b;for(i=0;i<256;++i){crc^=(i>=12&&i<16)?0:p[i];for(b=0;b<8;++b)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return ~crc;}
static inline int MsRecordingText(const unsigned char*p,unsigned n,unsigned cap,int required){unsigned i;if(n>cap||(required&&!n))return 0;for(i=0;i<n;++i)if(p[i]<32||p[i]>126||p[i]=='/'||p[i]=='\\')return 0;for(;i<cap;++i)if(p[i])return 0;return 1;}
static inline int MsRecordingManifestValid(const unsigned char*p,unsigned bytes,unsigned game,unsigned profile){
    unsigned start,end,result,splitCount,i,previous=0,variant,parent,flags;
    if(!p||bytes!=256||MsRecordingWord(p)!=MS_RECORDING_MANIFEST_MAGIC||MsRecordingHalf(p+4)!=1||MsRecordingHalf(p+6)!=256||
       MsRecordingWord(p+8)!=256||MsRecordingWord(p+12)!=MsRecordingCrc(p)||!MsRecordingWord(p+16)||!MsRecordingWord(p+20)||
       (MsRecordingWord(p+24)&0xff000000u)||!(MsRecordingWord(p+24)&0x20000u)||!SusamuneGhostRunFlagsValid(MsRecordingWord(p+28))||MsRecordingWord(p+32)!=game||p[36]||p[38]!=profile||
       !SusamuneGhostPersonalProfile(profile)||p[39]!=MS_RECORDING_MODE||p[40]!=MS_RECORDING_CODEC||p[41]||MsRecordingHalf(p+42)!=4||
       p[95]!=SUSAMUNE_GHOST_CHECKSUM_CRC32||MsRecordingWord(p+84)!=MsRecordingWord(p+16)||MsRecordingWord(p+88)!=MsRecordingWord(p+20)||
       !MsRecordingWord(p+224)||MsRecordingWord(p+224)<96||MsRecordingWord(p+224)>MS_RECORDING_FILE_LIMIT||!MsRecordingWord(p+228)||
       !MsRecordingWord(p+240)||MsRecordingWord(p+244)||MsRecordingWord(p+248)||MsRecordingWord(p+252))return 0;
    if(!((game==SUSAMUNE_GHOST_GAME_ID_JP&&p[37]==0)||(game==SUSAMUNE_GHOST_GAME_ID_US&&p[37]==1)||(game==SUSAMUNE_GHOST_GAME_ID_PAL&&p[37]==2)))return 0;
    start=MsRecordingWord(p+56);end=MsRecordingWord(p+60);result=MsRecordingWord(p+52);
    if(start>0x7fffffffu||end>0x7fffffffu||end<=start||MsRecordingWord(p+64)!=end-start||!MsRecordingWord(p+68)||
       (result!=0xffffffffu&&(result<start||result>end))||MsRecordingWord(p+72)||MsRecordingWord(p+76)||MsRecordingWord(p+80))return 0;
    variant=MsRecordingWord(p+48);parent=p[46];flags=p[47];
    if(p[44]>0x3c||p[45]>9||(parent!=255&&parent>0x3c)||(flags&~3u)||((flags&1u)!=0)!=(parent!=255)||((flags&2u)&&parent==255)||
       (variant>255&&variant!=0xffffffffu))return 0;
    if(!MsRecordingText(p+96,p[92],24,0)||!MsRecordingText(p+120,p[93],48,1)||!MsRecordingText(p+168,p[94],16,0))return 0;
    splitCount=p[190];if(splitCount>8||p[191]||(splitCount&&(!MsRecordingWord(p+184)||MsRecordingHalf(p+188)==0xffffu)))return 0;
    if(!splitCount&&(MsRecordingWord(p+184)||MsRecordingHalf(p+188)))return 0;
    for(i=0;i<8;++i){unsigned qf=MsRecordingWord(p+192+4*i);if(i<splitCount){if(qf<start||qf>end||(i&&qf<previous))return 0;previous=qf;}else if(qf)return 0;}
    return 1;
}
#endif
