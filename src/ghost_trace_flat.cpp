#include "susamune/ghost_provenance.h"
#include "susamune/ghost_trace_flat.hxx"
namespace GhostTraceFlat {
namespace {
namespace L=GhostTraceLogical;namespace M=GhostTraceBranchIo;namespace I=GhostTraceIo;namespace E=GhostTraceExportIo;namespace P=GhostTraceStream;
Task*running;
bool same(I::File a,I::File b){return a.nonce==b.nonce&&a.run==b.run&&a.region==b.region;}
void fail(Task&t,Error error,unsigned detail=0){if(!t.error){t.error=error;t.detail=detail;}t.canceled=true;t.phase=CLEANUP;}
bool write(Task&t,unsigned bytes,unsigned next){if(!E::append(*t.output,bytes)){fail(t,OUTPUT,t.output->error);return false;}t.nextPhase=next;t.phase=WRITE_WAIT;return true;}
bool sourceHeader(Task&t,GhostArena::View bytes){
    if(!bytes.data||bytes.bytes!=64)return false;const auto*h=static_cast<const unsigned char*>(bytes.data);const auto&e=t.expected;
    if(MsTraceGet(h)!=MS_TRACE_MAGIC||MsTraceGet(h+4)!=e.version||MsTraceGet(h+8)!=64||MsTraceGet(h+12)!=e.game||
       MsTraceGet(h+16)!=t.copyFile.nonce||MsTraceGet(h+20)!=t.copyFile.run||MsTraceGet(h+24)!=e.scene||MsTraceGet(h+28)!=e.capabilities||
       MsTraceGet(h+32)!=MS_TRACE_BUFFER_BYTES||MsTraceGet(h+60)!=e.headerHash||MsTraceHash(2166136261u,h,60)!=e.headerHash)return false;
    t.runFlags|=MsTraceGet(h+36);return !(t.runFlags&0x20u)||(t.runFlags&1u);
}
bool sourceFooter(Task&t,GhostArena::View bytes){
    if(!bytes.data||bytes.bytes!=32)return false;const auto*p=static_cast<const unsigned char*>(bytes.data);
    return MsTraceGet(p)==0x444f4e45u&&MsTraceGet(p+4)==t.copyFile.run&&MsTraceGet(p+8)==t.expected.chunks&&
        MsTraceGet(p+12)==t.expected.bytes-32&&MsTraceGet(p+16)==t.expected.capabilities&&MsTraceHash(2166136261u,p,32)==t.expected.footerHash;
}
bool closeSource(Task&t){I::close(*t.transport,t.channel);return I::status(*t.transport,t.channel).phase==I::CLOSED;}
void cleanup(Task&t){
    M::poll(*t.maps);I::poll(*t.transport,t.channel);L::poll(*t.logical,1);E::poll(*t.output);
    if(!L::close(*t.logical)||!closeSource(t)||!E::close(*t.output))return;
    if(t.pinMayExist){if(t.maps->phase!=M::IDLE&&!M::cancel(*t.maps))return;
        if(!M::pin(*t.maps,t.pin,true))return;t.unpinIssued=1;t.phase=UNPIN;return;}
    running=nullptr;t.phase=t.published?DONE:FAILED;
}
}
bool active(){return running!=nullptr;}
bool begin(Task&t,L::Stream&logical,L::Plan plan,M::Client&maps,P::Stream&physical,I::Transport&transport,E::Client&output,
           unsigned readChannel,unsigned copyChannel,I::File source,I::File target,unsigned game,unsigned destination){
    if(running||output.phase!=E::IDLE||copyChannel>=MS_TRACE_READ_CHANNELS||copyChannel==readChannel||
       I::status(transport,copyChannel).phase!=I::CLOSED||!target.nonce||!target.run||target.region!=source.region||same(source,target))return false;
    if(!L::open(logical,plan,maps,physical,transport,readChannel,source,game,0))return false;
    t={};t.logical=&logical;t.transport=&transport;t.output=&output;t.maps=&maps;t.target=target;t.game=game;
    t.channel=copyChannel;t.destination=destination;t.phase=RESOLVE;running=&t;return true;
}
Phase poll(Task&t,unsigned budget){
    if(running!=&t)return static_cast<Phase>(t.phase);if(!budget)budget=1;if(budget>16)budget=16;
    if(t.phase==CLEANUP){cleanup(t);return static_cast<Phase>(t.phase);}
    for(unsigned step=0;step<budget;++step){
        M::poll(*t.maps);I::poll(*t.transport,t.channel);E::poll(*t.output);
        if(t.phase!=UNPIN&&t.output->phase==E::FAILED){fail(t,OUTPUT,t.output->error);break;}
        if(t.phase!=UNPIN&&t.transport->channels[t.channel].error){fail(t,SOURCE,t.transport->channels[t.channel].error);break;}
        if(t.phase!=UNPIN&&L::poll(*t.logical,1)==L::FAILED){fail(t,SOURCE,L::status(*t.logical).error);break;}
        if(t.phase==RESOLVE){
            if(t.logical->phase==L::RESOLVING)break;
            if(!t.logical->plan.count){fail(t,SOURCE);break;}
            const auto&leaf=t.logical->plan.segments[0];if(!leaf.identity.chunks){fail(t,SOURCE);break;}
            t.pin={};t.pin.nonce=t.pin.parent.nonce=leaf.file.nonce;t.pin.run=t.pin.parent.run=leaf.file.run;
            t.pin.game=leaf.identity.game;t.pin.capabilities=leaf.identity.capabilities;t.pin.parent.generation=t.pin.parent.frame=1;
            t.pin.parent.chunk=leaf.identity.chunks;t.pin.fence.fileBytes=leaf.identity.bytes-32;t.pin.fence.headerHash=leaf.identity.headerHash;
            t.pin.ownerKind=0x45585054u;t.pin.ownerId=t.target.run;t.pin.ownerGeneration=t.target.nonce;
            if(!M::pin(*t.maps,t.pin)){fail(t,OWNERSHIP);break;}t.pinMayExist=1;t.phase=PIN_SOURCE;break;
        }
        if(t.phase==PIN_SOURCE){
            if(t.maps->phase==M::WAITING)break;if(t.maps->phase!=M::READY){fail(t,SOURCE,t.maps->error);break;}M::consume(*t.maps);
            if(t.destination&MS_TRACE_EXPORT_NAMED){
                auto out=E::buffer(*t.output);
                if(!out.data||!MsTraceExportNameValid(t.exportName)){fail(t,ARGUMENT);break;}
                __builtin_memcpy(out.data,t.exportName,sizeof(t.exportName));
            }
            if(!E::begin(*t.output,t.target.nonce,t.target.run,t.game,t.destination)){fail(t,OUTPUT);break;}t.phase=BEGIN_OUTPUT;break;
        }
        if(t.phase==BEGIN_OUTPUT){if(t.output->operation)break;t.phase=HEADER;}
        if(t.phase==HEADER){
            const auto&first=t.logical->plan.segments[t.logical->plan.count-1];t.runFlags=L::runFlags(*t.logical);
            __builtin_memset(t.header,0,64);MsTracePut(t.header,MS_TRACE_MAGIC);MsTracePut(t.header+4,3);MsTracePut(t.header+8,64);
            MsTracePut(t.header+12,t.game);MsTracePut(t.header+16,t.target.nonce);MsTracePut(t.header+20,t.target.run);
            MsTracePut(t.header+24,first.identity.scene);MsTracePut(t.header+28,first.identity.capabilities);MsTracePut(t.header+32,MS_TRACE_BUFFER_BYTES);
            MsTracePut(t.header+36,t.runFlags);MsTracePut(t.header+60,MsTraceHash(2166136261u,t.header,60));__builtin_memcpy(t.initialHeader,t.header,64);
            auto out=E::buffer(*t.output);if(!out.data){fail(t,OWNERSHIP);break;}__builtin_memcpy(out.data,t.header,64);write(t,64,NEXT_CHUNK);break;
        }
        if(t.phase==WRITE_WAIT){
            if(t.output->operation)break;if(t.pendingCopy){t.copyAt+=t.pendingCopy;t.pendingCopy=0;}
            t.phase=t.nextPhase;
        }
        if(t.phase==NEXT_CHUNK){
            GhostArena::View view;P::Cursor cursor;unsigned ticket=0;const auto result=L::nextChunk(*t.logical,view,cursor,ticket);
            if(result==L::WAIT)break;if(result==L::END){t.phase=FOOTER;continue;}if(result!=L::EVENT){fail(t,SOURCE);break;}
            t.cursor=cursor;t.expected=t.logical->plan.segments[t.logical->index].identity;t.runFlags|=L::runFlags(*t.logical);
            if(!L::releaseChunk(*t.logical,ticket)){fail(t,OWNERSHIP);break;}
            t.copyAt=cursor.fileOffset;t.copyHash=2166136261u;
            if(!same(t.copyFile,cursor.file)){I::close(*t.transport,t.channel);t.copyVerified=0;}
            t.phase=OPEN_SOURCE;
        }
        if(t.phase==OPEN_SOURCE){
            const auto state=I::status(*t.transport,t.channel);
            if(state.pending||state.phase==I::CLOSING)break;
            if(state.phase==I::CLOSED){if(!I::open(*t.transport,t.channel,t.cursor.file)){fail(t,SOURCE);break;}t.copyFile=t.cursor.file;t.copyVerified=0;break;}
            if(state.phase!=I::IDLE||state.fileBytes!=t.expected.bytes){fail(t,SOURCE_CHANGED);break;}
            if(t.copyVerified){t.phase=COPY_REQUEST;continue;}
            if(!I::read(*t.transport,t.channel,0,64)){fail(t,SOURCE);break;}t.phase=SOURCE_HEADER;break;
        }
        if(t.phase==SOURCE_HEADER){
            if(I::status(*t.transport,t.channel).phase!=I::READY)break;
            if(!sourceHeader(t,I::view(*t.transport,t.channel))){fail(t,SOURCE_CHANGED);break;}
            I::consume(*t.transport,t.channel);if(!I::read(*t.transport,t.channel,t.expected.bytes-32,32)){fail(t,SOURCE);break;}t.phase=SOURCE_FOOTER;break;
        }
        if(t.phase==SOURCE_FOOTER){
            if(I::status(*t.transport,t.channel).phase!=I::READY)break;
            if(!sourceFooter(t,I::view(*t.transport,t.channel))){fail(t,SOURCE_CHANGED);break;}
            I::consume(*t.transport,t.channel);t.copyVerified=1;t.phase=COPY_REQUEST;
        }
        if(t.phase==COPY_REQUEST){
            if(t.copyAt==t.cursor.fileEnd){if(t.copyHash!=t.cursor.encodedHash){fail(t,SOURCE_CHANGED);break;}t.phase=NEXT_CHUNK;continue;}
            unsigned n=t.cursor.fileEnd-t.copyAt;if(n>MS_TRACE_READ_MAX_BYTES)n=MS_TRACE_READ_MAX_BYTES;
            if(!I::read(*t.transport,t.channel,t.copyAt,n)){fail(t,SOURCE);break;}t.phase=COPY_DATA;break;
        }
        if(t.phase==COPY_DATA){
            if(I::status(*t.transport,t.channel).phase!=I::READY)break;const auto source=I::view(*t.transport,t.channel);auto out=E::buffer(*t.output);
            if(!source.data||!source.bytes||!out.data||source.bytes>out.bytes){fail(t,OWNERSHIP);break;}
            t.copyHash=MsTraceHash(t.copyHash,source.data,source.bytes);__builtin_memcpy(out.data,source.data,source.bytes);
            if(t.copyAt==t.cursor.fileOffset){
                if(source.bytes<32||MsTraceGet(static_cast<const unsigned char*>(source.data))!=t.cursor.file.run||
                   MsTraceGet(static_cast<const unsigned char*>(source.data)+4)!=t.cursor.chunk||t.chunks==~0u){fail(t,SOURCE_CHANGED);break;}
                MsTracePut(static_cast<unsigned char*>(out.data),t.target.run);MsTracePut(static_cast<unsigned char*>(out.data)+4,++t.chunks);
            }
            t.pendingCopy=source.bytes;I::consume(*t.transport,t.channel);write(t,t.pendingCopy,COPY_REQUEST);break;
        }
        if(t.phase==FOOTER){
            auto out=E::buffer(*t.output);if(!out.data){fail(t,OWNERSHIP);break;}
            auto*p=static_cast<unsigned char*>(out.data);__builtin_memset(p,0,32);MsTracePut(p,0x444f4e45u);MsTracePut(p+4,t.target.run);
            MsTracePut(p+8,t.chunks);MsTracePut(p+12,t.output->bytes);MsTracePut(p+16,MsTraceGet(t.header+28));write(t,32,CLOSE_INPUT);break;
        }
        if(t.phase==CLOSE_INPUT){
            if(!L::close(*t.logical)||!closeSource(t))break;auto out=E::buffer(*t.output);if(!out.data){fail(t,OWNERSHIP);break;}
            t.runFlags|=L::runFlags(*t.logical);MsTracePut(t.header+36,t.runFlags);MsTracePut(t.header+40,MS_TRACE_PROVENANCE_TAG);MsTracePut(t.header+60,MsTraceHash(2166136261u,t.header,60));
            const unsigned adler=MsTraceAdlerReplaceHeader(t.output->adler,t.initialHeader,t.header,t.output->bytes);__builtin_memcpy(out.data,t.header,64);
            if(!E::commit(*t.output,adler)){fail(t,OUTPUT);break;}t.phase=COMMIT_WAIT;break;
        }
        if(t.phase==COMMIT_WAIT){
            if(t.output->operation)break;if(t.output->phase!=E::DONE){fail(t,OUTPUT,t.output->error);break;}
            t.result=t.output->identity;t.published=true;t.phase=CLEANUP;break;
        }
        if(t.phase==UNPIN){
            if(t.maps->phase==M::WAITING)break;
            if(t.maps->phase==M::READY)M::consume(*t.maps);else{t.cleanupError=t.maps->error;M::cancel(*t.maps);}
            t.pinMayExist=0;t.unpinIssued=0;running=nullptr;t.phase=t.published?DONE:FAILED;break;
        }
    }
    if(t.phase==CLEANUP)cleanup(t);return static_cast<Phase>(t.phase);
}
Status status(const Task&t){return {static_cast<Phase>(t.phase),t.error,t.detail,t.output?t.output->bytes:0,t.chunks,t.runFlags,t.cleanupError,running==&t,t.published};}
bool cancel(Task&t){if(running!=&t)return true;fail(t,CANCELED);poll(t,1);return running!=&t;}
bool close(Task&t){return running==&t?cancel(t):true;}
}
