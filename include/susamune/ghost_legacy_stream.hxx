#pragma once
#include "susamune/ghost_trace_index.hxx"
#include "susamune/ghost_format.h"

namespace GhostLegacyStream {
enum { kBlockBytes=16384 };
enum Status { NEED_DATA, EVENTS, COMPLETE, FAILED };
enum Error { NONE, ARGUMENT, SHORT_READ, HEADER, UNSUPPORTED, SEGMENTS, POSE, TEACHING, CAMERA, CONTEXT, CHECKSUM };
enum Type { POSE_SAMPLE, INPUT_SAMPLE, CAMERA_SAMPLE, CONTEXT_RECORD };
struct Read { unsigned offset,bytes; void *destination; };
struct Metadata {
    unsigned version,game,region,runFlags,requiredFeatures,fileChecksum;
    unsigned startQf,endQf,resultQf,poseCount,segmentCount,inputCount,splitCount,teachingFlags,lastInputQf;
    unsigned poseOffset,inputOffset,cameraOffset,cameraCount,cameraFlags,contextOffset,contextCount,contextFlags;
    SusamuneGhostSegment segments[64];
    SusamuneGhostSplitSample splits[8];
    unsigned char header[256];
};
struct Event {
    Type type;
    unsigned index,segment,offset;
    GhostTraceIndex::Sample sample;
    const unsigned char *bytes;
    unsigned byteCount;
};
struct Reader {
    Metadata metadata;
    unsigned char *buffer;
    unsigned capacity,fileBytes,targetGame,offset,pending,phase,error;
    unsigned used,at,remaining,index,segment,qf,previousQf,previousSegment;
    unsigned fileCrc,payloadCrc,sectionCrc,expectedCrc;
    unsigned char previousContext[96];
    bool contextSeen;
};
// Outputs are provisional until COMPLETE verifies every section and file checksum.
// Destination storage is caller-owned; this reader never selects fixed game memory.
bool begin(Reader &,unsigned fileBytes,unsigned targetGame,void *buffer,unsigned bufferBytes);
Status status(const Reader &);
bool nextRead(Reader &,Read &);
bool acceptRead(Reader &,unsigned bytes);
bool next(Reader &,Event &);
}
