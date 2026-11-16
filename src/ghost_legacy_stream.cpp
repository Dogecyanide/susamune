#include "susamune/ghost_legacy_stream.hxx"
#include "susamune/ghost_storage.h"

namespace GhostLegacyStream {
namespace {
using u8=unsigned char;using u16=unsigned short;using u32=unsigned;using s32=int;
enum ValidateResult { VALIDATE_OK,VALIDATE_INVALID,VALIDATE_FORWARD };
#define memcpy __builtin_memcpy
#define memset __builtin_memset
#define memcmp __builtin_memcmp
#include "../launcher/kernel/GhostCanonical.inc"
#undef memcpy
#undef memset
#undef memcmp
enum Phase { FILE_HEADER,TABLE,POSES,TEACHING_HEADER,INPUTS,SPLITS,CAMERA_HEADER,CAMERAS,CONTEXT_HEADER,CONTEXTS,DONE,BAD };
int signedWord(unsigned v) { return v<=0x7fffffffu?int(v):-1-int(~v); }
short signedHalf(const u8 *p) { const unsigned v=ReadBe16(p);return static_cast<short>(v<=32767?int(v):int(v)-65536); }
int signed24(const u8 *p) { const unsigned v=unsigned(p[0])<<16|unsigned(p[1])<<8|p[2];return v&0x800000u?int(v)-0x1000000:int(v); }
bool fail(Reader &r,Error e) { r.error=e;r.phase=BAD;return false; }
bool range(const void *p,unsigned n) { const __UINTPTR_TYPE__ a=reinterpret_cast<__UINTPTR_TYPE__>(p);return a&&n&&a+n>=a; }
unsigned recordBytes(unsigned phase,unsigned version) {
    return phase==POSES?16:phase==INPUTS?SusamuneGhostInputStride(version):phase==SPLITS?12:phase==CAMERAS?24:96;
}
bool final(Reader &r) {
    if(r.offset!=r.fileBytes||~r.fileCrc!=ReadBe32(r.metadata.header+12)||
       ~r.payloadCrc!=ReadBe32(r.metadata.header+20))return fail(r,CHECKSUM);
    r.phase=DONE;return true;
}
void records(Reader &r,unsigned phase,unsigned count) {
    r.phase=phase;r.remaining=count;r.index=0;r.used=r.at=0;r.previousQf=0;r.previousSegment=0;
}
bool advance(Reader &r) {
    if(r.error||r.pending||r.at<r.used)return !r.error;
    Metadata &m=r.metadata;
    while(!r.remaining) {
        switch(r.phase) {
        case POSES:
            if(r.segment!=m.segmentCount)return fail(r,POSE);
            if(m.version<5)return final(r);
            r.phase=TEACHING_HEADER;r.remaining=1;break;
        case INPUTS:records(r,SPLITS,m.splitCount);break;
        case SPLITS:
            if(~r.sectionCrc!=r.expectedCrc)return fail(r,CHECKSUM);
            if(m.version<8)return final(r);
            r.phase=CAMERA_HEADER;r.remaining=1;break;
        case CAMERAS:
            if(~r.sectionCrc!=r.expectedCrc)return fail(r,CHECKSUM);
            if(m.version<10)return final(r);
            r.phase=CONTEXT_HEADER;r.remaining=1;break;
        case CONTEXTS:
            if(~r.sectionCrc!=r.expectedCrc)return fail(r,CHECKSUM);
            return final(r);
        default:return true;
        }
    }
    return true;
}
bool table(Reader &r,const u8 *data) {
    Metadata &m=r.metadata;
    if((CrcUpdate(~0u,data,2048)^~0u)!=ReadBe32(m.header+204))return fail(r,CHECKSUM);
    unsigned covered=0,previous=0;
    for(unsigned i=0;i<64;++i) {
        const u8 *p=data+i*32;
        if(i>=m.segmentCount) { if(!BytesAreZero(p,32))return fail(r,SEGMENTS);continue; }
        SusamuneGhostSegment &s=m.segments[i];
        s={ReadBe32(p),ReadBe32(p+4),ReadBe32(p+8),ReadBe32(p+12),signedWord(ReadBe32(p+16)),p[20],p[21],p[22],p[23],ReadBe32(p+24),ReadBe32(p+28)};
        if(s.firstSample!=covered||!s.sampleCount||s.sampleCount>m.poseCount-covered||s.startQf>s.endQf||
           s.endQf>SUSAMUNE_GHOST_QF_MAX||(i&&s.startQf<previous)||
           !SusamuneGhostSegmentMetadataValid(m.version,i,s.reserved0,s.reserved1)||
           !RouteIsValid(s.routeArea,s.routeEpisode,s.routeParentArea,s.routeFlags,s.routeVariant)||
           (m.game!=r.targetGame&&!PortableRouteIsValid(s.routeArea,s.routeEpisode,s.routeParentArea,s.routeFlags,s.routeVariant)))return fail(r,SEGMENTS);
        if(!i&&(s.startQf!=m.startQf||s.routeArea!=m.header[44]||s.routeEpisode!=m.header[45]||
           s.routeParentArea!=m.header[46]||s.routeFlags!=m.header[47]||s.routeVariant!=signedWord(ReadBe32(m.header+48))))return fail(r,SEGMENTS);
        covered+=s.sampleCount;previous=s.endQf;
    }
    if(covered!=m.poseCount||previous!=m.endQf||
       (m.resultQf!=0xffffffffu&&m.resultQf<m.segments[m.segmentCount-1].startQf))return fail(r,SEGMENTS);
    records(r,POSES,m.poseCount);r.segment=0;r.qf=m.segments[0].startQf;return true;
}
bool header(Reader &r) {
    Metadata &m=r.metadata;const u8 *p=r.buffer;
    const unsigned region=r.targetGame==SUSAMUNE_GHOST_GAME_ID_JP?0:r.targetGame==SUSAMUNE_GHOST_GAME_ID_US?1:2;
    const ValidateResult check=ValidateCanonicalHeader(p,256,0,true,r.targetGame,static_cast<u8>(region));
    if(check!=VALIDATE_OK)return fail(r,check==VALIDATE_FORWARD?UNSUPPORTED:HEADER);
    if(ReadBe32(p+8)!=r.fileBytes)return fail(r,HEADER);
    __builtin_memcpy(m.header,p,256);m.version=ReadBe16(p+4);m.game=ReadBe32(p+32);m.region=p[37];
    m.runFlags=ReadBe32(p+28);m.requiredFeatures=ReadBe32(p+24);m.fileChecksum=ReadBe32(p+12);
    m.startQf=ReadBe32(p+56);m.endQf=ReadBe32(p+60);m.resultQf=ReadBe32(p+52);m.poseCount=ReadBe32(p+68);
    m.segmentCount=ReadBe16(p+184);m.poseOffset=ReadBe32(p+196);
    r.fileCrc=CrcUpdateHeader(~0u,p,12,16);r.payloadCrc=~0u;r.phase=TABLE;r.remaining=1;return true;
}
bool sectionHeader(Reader &r) {
    Metadata &m=r.metadata;const u8 *p=r.buffer;const unsigned offset=r.offset-32;
    if(r.phase==TEACHING_HEADER) {
        const unsigned count=ReadBe32(p+8),splits=ReadBe32(p+12),stride=SusamuneGhostInputStride(m.version);
        if(count>SusamuneGhostInputLimit(m.version)||splits>8)return fail(r,TEACHING);
        const unsigned bytes=32+count*stride+splits*12;
        if(bytes>r.fileBytes-offset||!SusamuneGhostTeachingHeaderValid(p,bytes)||
           p[5]!=(m.version==10?4:m.version>=7?3:m.version==6?2:1)||
           (m.version<8&&bytes!=r.fileBytes-offset))return fail(r,TEACHING);
        m.inputCount=count;m.splitCount=splits;m.teachingFlags=ReadBe32(p+16);m.inputOffset=r.offset;
        r.expectedCrc=ReadBe32(p+20);records(r,INPUTS,count);
    } else if(r.phase==CAMERA_HEADER) {
        const unsigned count=ReadBe32(p+8);
        if(count>SUSAMUNE_GHOST_CAMERA_MAX_COUNT)return fail(r,CAMERA);
        const unsigned bytes=32+count*24;
        if(bytes>r.fileBytes-offset||!SusamuneGhostCameraHeaderValid(p,bytes)||
           (m.version<10&&bytes!=r.fileBytes-offset))return fail(r,CAMERA);
        m.cameraOffset=offset;m.cameraCount=count;m.cameraFlags=ReadBe32(p+12);
        r.expectedCrc=ReadBe32(p+16);records(r,CAMERAS,count);
    } else {
        const unsigned bytes=r.fileBytes-offset;
        if(!SusamuneGhostContextHeaderValid(p,bytes))return fail(r,CONTEXT);
        m.contextOffset=offset;m.contextCount=ReadBe32(p+8);m.contextFlags=ReadBe32(p+12);
        r.expectedCrc=ReadBe32(p+16);records(r,CONTEXTS,m.contextCount);r.contextSeen=false;
    }
    r.sectionCrc=~0u;return advance(r);
}
bool pose(Reader &r,const u8 *p,Event &e) {
    Metadata &m=r.metadata;const SusamuneGhostSegment &segment=m.segments[r.segment];
    const unsigned local=r.index-segment.firstSample,delta=ReadBe16(p+2),packed=unsigned(p[13])<<16|unsigned(p[14])<<8|p[15];
    const unsigned anim=packed>>15,held=m.version>=4?packed&15u:0,yoshi=m.version>=4?(packed>>4)&7u:0;
    const int x=signed24(p+4),y=signed24(p+7),z=signed24(p+10);
    if(x<-8000000||x>8000000||y<-8000000||y>8000000||z<-8000000||z>8000000||anim>335||
       (m.version==3&&(packed&7u))||yoshi>5||
       !(held==0||held<=m.header[208]||(held==15&&(ReadBe16(m.header+210)&1u))))return fail(r,POSE);
    if(!local) { if(delta)return fail(r,POSE);r.qf=segment.startQf; }
    else {
        if(!delta||(delta<4&&local+1!=segment.sampleCount)||delta>segment.endQf-r.qf)return fail(r,POSE);
        r.qf+=delta;
    }
    if(local+1==segment.sampleCount&&r.qf!=segment.endQf)return fail(r,POSE);
    e.type=POSE_SAMPLE;e.segment=r.segment;
    auto &s=e.sample;s.frame=r.index+1;s.movement=r.index;s.qf=int(r.qf);s.x=float(x)/8;s.y=float(y)/8;s.z=float(z)/8;
    s.yaw=signedHalf(p);s.animationId=static_cast<unsigned short>(anim);
    s.animationPhase=static_cast<unsigned short>(m.version>=4?((packed>>7)&255u)*4095u/255u:(packed>>3)&4095u);
    s.yoshi=static_cast<u8>(yoshi);s.visible=1;s.flags=GhostTraceIndex::POSE|GhostTraceIndex::QFT;s.reserved[0]=static_cast<u8>(m.version);
    if(held&&held!=15) { const u8 *d=m.header+214+(held-1)*6;s.heldObjectId=ReadBe32(d);s.heldNameKey=ReadBe16(d+4); }
    if(local+1==segment.sampleCount)++r.segment;
    return true;
}
bool input(Reader &r,const u8 *p,Event &e) {
    Metadata &m=r.metadata;
    if(!SusamuneGhostTeachingInputValidVersion(p,m.startQf,m.endQf,r.previousQf,r.index==0,m.version)||
       (m.version>=6&&!SusamuneGhostVisualValid(p+16,m.version>=7)))return fail(r,TEACHING);
    const unsigned qf=SusamuneGhostTeachingInputQf(p,m.startQf,m.version);r.previousQf=qf;m.lastInputQf=qf;
    e.type=INPUT_SAMPLE;e.segment=~0u;auto &s=e.sample;
    s.frame=r.index+1;s.movement=r.index;s.qf=int(qf);s.flags=GhostTraceIndex::QFT|GhostTraceIndex::INPUT;
    s.raw.buttons=ReadBe16(p+4);__builtin_memcpy(&s.raw.stickX,p+6,9);s.raw.reserved=0;
    s.reserved[0]=static_cast<u8>(m.version);s.reserved[1]=m.version==10?p[15]:0;s.yaw=m.version==10?signedHalf(p+2):0;
    if(m.version>=6)__builtin_memcpy(&s.fludd,p+16,8);
    return true;
}
}
bool begin(Reader &r,unsigned fileBytes,unsigned targetGame,void *buffer,unsigned bytes) {
    const __UINTPTR_TYPE__ a=reinterpret_cast<__UINTPTR_TYPE__>(buffer),b=reinterpret_cast<__UINTPTR_TYPE__>(&r);
    if(fileBytes<256||fileBytes>SUSAMUNE_GHOST_MAX_FILE_SIZE||bytes<2048||bytes>kBlockBytes||!range(buffer,bytes)||
       (a&31u)||(a<b+sizeof(r)&&b<a+bytes)||
       !(targetGame==SUSAMUNE_GHOST_GAME_ID_JP||targetGame==SUSAMUNE_GHOST_GAME_ID_US||targetGame==SUSAMUNE_GHOST_GAME_ID_PAL))return false;
    r={};r.buffer=static_cast<u8*>(buffer);r.capacity=bytes;r.fileBytes=fileBytes;r.targetGame=targetGame;r.phase=FILE_HEADER;r.remaining=1;return true;
}
Status status(const Reader &r) {
    if(r.error||r.phase==BAD)return FAILED;
    if(r.phase==DONE)return COMPLETE;
    return r.at<r.used?EVENTS:NEED_DATA;
}
bool nextRead(Reader &r,Read &out) {
    if(!r.buffer||r.pending||!advance(r)||status(r)!=NEED_DATA)return false;
    unsigned bytes;
    if(r.phase==FILE_HEADER)bytes=256;
    else if(r.phase==TABLE)bytes=2048;
    else if(r.phase==TEACHING_HEADER||r.phase==CAMERA_HEADER||r.phase==CONTEXT_HEADER)bytes=32;
    else {
        const unsigned stride=recordBytes(r.phase,r.metadata.version),limit=r.capacity/stride;
        bytes=(r.remaining<limit?r.remaining:limit)*stride;
    }
    if(!bytes||r.offset>r.fileBytes||bytes>r.fileBytes-r.offset)return fail(r,SHORT_READ);
    r.pending=bytes;out={r.offset,bytes,r.buffer};return true;
}
bool acceptRead(Reader &r,unsigned bytes) {
    if(!r.pending||r.error||bytes!=r.pending)return fail(r,SHORT_READ);
    r.pending=0;r.offset+=bytes;
    if(r.phase==FILE_HEADER)return header(r);
    r.fileCrc=CrcUpdate(r.fileCrc,r.buffer,bytes);r.payloadCrc=CrcUpdate(r.payloadCrc,r.buffer,bytes);
    if(r.phase==TABLE)return table(r,r.buffer);
    if(r.phase==TEACHING_HEADER||r.phase==CAMERA_HEADER||r.phase==CONTEXT_HEADER)return sectionHeader(r);
    if(r.phase!=POSES)r.sectionCrc=CrcUpdate(r.sectionCrc,r.buffer,bytes);
    r.used=bytes;r.at=0;return true;
}
bool next(Reader &r,Event &e) {
    if(r.error||r.pending||r.at>=r.used)return false;
    const u8 *p=r.buffer+r.at;const unsigned stride=recordBytes(r.phase,r.metadata.version);
    if(stride>r.used-r.at||!r.remaining)return fail(r,ARGUMENT);
    e={};e.index=r.index;e.offset=r.offset-r.used+r.at;e.bytes=p;e.byteCount=stride;
    Metadata &m=r.metadata;bool emit=true;
    switch(r.phase) {
    case POSES:if(!pose(r,p,e))return false;break;
    case INPUTS:if(!input(r,p,e))return false;break;
    case SPLITS: {
        const unsigned route=r.index?m.splits[0].route:ReadBe16(p+8),schema=r.index?m.splits[0].schema:ReadBe32(p+4);
        if(!SusamuneGhostTeachingSplitValid(p,m.startQf,m.endQf,r.previousQf,route,schema,r.index))return fail(r,TEACHING);
        m.splits[r.index]={ReadBe32(p),ReadBe32(p+4),ReadBe16(p+8),p[10],p[11]};r.previousQf=ReadBe32(p);emit=false;break;
    }
    case CAMERAS: {
        const unsigned segment=p[23]&63u;
        if(segment>=m.segmentCount||!SusamuneGhostCameraSampleValid(p,m.segments[segment].startQf,m.segments[segment].endQf,
           r.previousQf,segment,r.previousSegment,r.index==0))return fail(r,CAMERA);
        e.type=CAMERA_SAMPLE;e.segment=segment;r.previousQf=ReadBe32(p);r.previousSegment=segment;break;
    }
    case CONTEXTS: {
        const unsigned segment=SusamuneGhostContextHalf(p+24);
        if(segment>=m.segmentCount||!SusamuneGhostContextRecordValid(p,m.segmentCount,m.inputCount,
           m.segments[segment].startQf,m.segments[segment].endQf,r.contextSeen?r.previousContext:nullptr))return fail(r,CONTEXT);
        e.type=CONTEXT_RECORD;e.segment=segment;__builtin_memcpy(r.previousContext,p,96);r.contextSeen=true;break;
    }
    default:return fail(r,ARGUMENT);
    }
    ++r.index;--r.remaining;r.at+=stride;
    if(!advance(r))return false;
    // Splits are retained in metadata; no visual sample is fabricated for them.
    if(!emit)return r.at<r.used?next(r,e):false;
    return true;
}
}
