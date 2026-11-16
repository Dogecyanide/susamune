// Each project publishes an alternate manifest only after every component verifies.
unsigned decimalId(const char *p){unsigned id=0;for(unsigned i=0;i<8;++i){if(p[i]<'0'||p[i]>'9')return 0;id=id*10+p[i]-'0';}return id;}
void decimalName(unsigned id,char *p){for(int i=7;i>=0;--i){p[i]='0'+id%10;id/=10;}}
void projectName(unsigned id,char *out){memset(out,0,32);memcpy(out,"ms_t",4);decimalName(id,out+4);memcpy(out+12,"_project",8);}
unsigned projectFileId(const char *name){return !memcmp(name,"ms_t",4) && !memcmp(name+12,"_project",9)?decimalId(name+4):0;}
unsigned partFileId(const char *name){return !memcmp(name,"ms_t",4) && decimalId(name+4) && !memcmp(name+12,"_s",2) && !name[22]?decimalId(name+14):0;}
void partName(unsigned project,unsigned id,char *out){memset(out,0,32);memcpy(out,"ms_t",4);decimalName(project,out+4);memcpy(out+12,"_s",2);decimalName(id,out+14);}
void archiveName(unsigned id,char *out){if(s.context.projectId)partName(s.context.projectId,id,out);else filename(id,out);}
unsigned partId(const SusamuneTasManifest &p,unsigned role){return role==SUSAMUNE_TAS_TAPE_ROLE?p.tape.componentId:p.components[role].componentId;}
bool isTape(){return s.verifyParts?s.part==SUSAMUNE_TAS_TAPE_ROLE:s.context.projectId && s.context.role==SUSAMUNE_TAS_TAPE_ROLE;}
bool projectHeaderMatches(const SusamuneTasManifest &p,unsigned role){
    auto &h=s.header;
    if(h.gameId!=p.gameId || h.buildCrc!=p.buildCrc || h.configId!=p.configId)return false;
    if(role==SUSAMUNE_TAS_TAPE_ROLE)return SusamuneTasTapeHeaderValid(&h) && h.sceneKey==p.sceneKey && h.headerCrc==p.tape.headerCrc && h.packedSize==p.tape.packedBytes;
    auto &c=p.components[role];return h.snapshotVersion!=SUSAMUNE_TAS_TAPE_SNAPSHOT && h.sceneKey==c.sceneKey && h.headerCrc==c.headerCrc && h.packedSize==c.packedBytes;
}
bool transferHeaderValid(){
    if(!s.context.projectId)return s.header.snapshotVersion!=SUSAMUNE_TAS_TAPE_SNAPSHOT;
    if(isTape()){
        if(!SusamuneTasTapeHeaderValid(&s.header) || s.request.poolOffset || s.request.command==SUSAMUNE_STATE_CMD_READ_WINDOW)return false;
    }else if(s.header.snapshotVersion==SUSAMUNE_TAS_TAPE_SNAPSHOT)return false;
    return s.request.command==SUSAMUNE_STATE_CMD_EXPORT || projectHeaderMatches(s.project,s.context.role);
}
bool tapeMetadataValid(bool bound){
    if(!isTape())return true;
    const auto &t=*reinterpret_cast<const SusamuneTasTakeData *>(s.mailbox->metadata);
    return SusamuneTasTapeMetadataValid(&s.header,&t) && (!bound || (t.frames==s.project.tapeFrames && !memcmp(t.originKey,s.project.startKey,8)));
}
unsigned projectRecordCrc(const ProjectRecord &r){
    const unsigned z=0;unsigned crc=SusamuneStateCrcUpdate(0xffffffffu,&r,28);crc=SusamuneStateCrcUpdate(crc,&z,4);
    return ~SusamuneStateCrcUpdate(crc,&r.manifest,sizeof(r.manifest));
}
bool projectRecordValid(const ProjectRecord &r){
    if(r.magic!=0x4d54534au || r.version!=1 || r.id!=s.projectId || r.state>2 || !zero(r.reserved,8) || r.checksum!=projectRecordCrc(r))return false;
    if(!r.state)return !r.generation && zero(&r.manifest,sizeof(r.manifest));
    if(r.state==2)return r.generation && zero(&r.manifest,sizeof(r.manifest));
    return SusamuneTasManifestValidCapacity(&r.manifest,StatePoolMemoryCapacity(&s.memory)) && r.manifest.projectId==r.id && r.manifest.generation==r.generation;
}
void projectPrepare(unsigned state){
    s.projectNext={};auto &r=s.projectNext;r.magic=0x4d54534au;r.version=1;r.id=s.projectId;r.state=state;
    r.generation=state==1?s.project.generation:state==2?s.projects[s.projectBank].generation+1:0;
    if(state==1)r.manifest=s.project;
    r.checksum=projectRecordCrc(r);s.phase=PROJECTWRITE;
}
void projectStart(){
    auto &r=s.request;
    if(r.command>=SUSAMUNE_STATE_CMD_TAS_BEGIN){
        if(r.command>SUSAMUNE_STATE_CMD_TAS_DELETE || s.context.projectId || r.poolOffset || r.packedSize || r.id>SUSAMUNE_STATE_MAX_ARCHIVE_ID){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
        if((r.command==SUSAMUNE_STATE_CMD_TAS_BEGIN || r.command==SUSAMUNE_STATE_CMD_TAS_RENAME) &&
            (!SusamuneStateNameValid(s.mailbox->requestName) || !s.mailbox->requestName[0])){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
        if(r.command==SUSAMUNE_STATE_CMD_TAS_BEGIN){
            if(r.id || r.expectedHeaderCrc){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
            s.phase=s.countersLoaded?LIST:COUNTERS0;return;
        }
        if(r.command==SUSAMUNE_STATE_CMD_TAS_CATALOG){s.mailbox->catalog={};s.mailbox->catalog.afterId=s.mailbox->catalog.nextId=r.id;s.phase=LIST;return;}
        if(!r.id){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
        s.projectId=s.id=r.id;
        if(r.command==SUSAMUNE_STATE_CMD_TAS_COMMIT){s.project=s.mailbox->tasProject;
            if(!SusamuneTasManifestValidCapacity(&s.project,StatePoolMemoryCapacity(&s.memory)) || s.project.projectId!=r.id){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}}
    }else{
        if((r.command!=SUSAMUNE_STATE_CMD_EXPORT && r.command!=SUSAMUNE_STATE_CMD_IMPORT && r.command!=SUSAMUNE_STATE_CMD_READ_WINDOW) || s.context.componentId!=r.id || (r.command==SUSAMUNE_STATE_CMD_EXPORT && r.id)){finish(SUSAMUNE_STATE_BAD_REQUEST);return;}
        s.projectId=s.context.projectId;
    }
    projectName(s.projectId,s.projectFile);s.phase=PROJECT0;
}
void projectSort(){for(unsigned i=1;i<s.count;++i)for(unsigned j=i;j && projectFileId(s.files[j].name)<projectFileId(s.files[j-1].name);--j){auto a=s.files[j];s.files[j]=s.files[j-1];s.files[j-1]=a;}}
void projectScan(){
    while(s.scan<s.count && (!projectFileId(s.files[s.scan].name) || projectFileId(s.files[s.scan].name)<=s.request.id))++s.scan;
    if(s.scan==s.count){finish(0);return;}
    s.projectId=projectFileId(s.files[s.scan].name);projectName(s.projectId,s.projectFile);s.phase=PROJECT0;
}
void projectPart(){
    while(s.part<3 && !partId(s.project,s.part))++s.part;
    if(s.part>3){s.verifyParts=false;projectPrepare(1);return;}
    partName(s.projectId,partId(s.project,s.part),s.filename);s.phase=HEADER;
}
void projectLoaded(){
    const bool a=projectRecordValid(s.projects[0]),b=projectRecordValid(s.projects[1]);
    const bool catalog=s.request.command==SUSAMUNE_STATE_CMD_TAS_CATALOG;
    if((!a&&!b) || (a&&b && s.projects[0].generation==s.projects[1].generation && memcmp(&s.projects[0],&s.projects[1],sizeof(ProjectRecord)))){
        if(catalog){++s.scan;s.phase=SCAN;}else finish(SUSAMUNE_STATE_BAD_FILE);return;
    }
    s.projectBank=b && (!a || s.projects[1].generation>s.projects[0].generation)?1:0;
    const auto &record=s.projects[s.projectBank];const auto &latest=record.manifest;const bool empty=!record.state;
    if(catalog){
        if(record.state==1){auto &c=s.mailbox->catalog;
            if(c.count==SUSAMUNE_STATE_CATALOG_COUNT){c.more=1;finish(0);return;}
            auto &e=c.entries[c.count++];e={};e.id=s.projectId;e.gameId=latest.gameId;e.buildCrc=latest.buildCrc;e.sceneKey=latest.sceneKey;e.headerCrc=latest.checksum;e.metadataSize=sizeof(latest);e.rawSize=latest.tapeFrames;e.packedSize=latest.tape.packedBytes;
            for(unsigned i=0;i<3;++i)e.packedSize+=latest.components[i].packedBytes;
            memcpy(e.name,latest.name,32);c.nextId=s.projectId;
        }++s.scan;s.phase=SCAN;return;
    }
    if(record.state==2){finish(SUSAMUNE_STATE_NOT_FOUND);return;}
    auto &r=s.request;
    if(s.context.projectId){
        if(s.context.projectGeneration!=record.generation || s.context.expectedProjectCrc!=(empty?0:latest.checksum)){finish(SUSAMUNE_STATE_STALE);return;}
        if(r.command==SUSAMUNE_STATE_CMD_EXPORT){auto &h=s.mailbox->header;
            if(!empty && (h.gameId!=latest.gameId || h.buildCrc!=latest.buildCrc || h.configId!=latest.configId || ((s.context.role==0 || isTape()) && h.sceneKey!=latest.sceneKey))){finish(SUSAMUNE_STATE_WRONG_CONFIG);return;}
        }else if(empty || partId(latest,s.context.role)!=r.id){finish(SUSAMUNE_STATE_STALE);return;}
        s.project=latest;s.projectChecked=true;s.phase=START;return;
    }
    if(r.command==SUSAMUNE_STATE_CMD_TAS_READ){
        if(empty){finish(SUSAMUNE_STATE_NOT_FOUND);return;}
        if(r.expectedHeaderCrc && r.expectedHeaderCrc!=latest.checksum){finish(SUSAMUNE_STATE_STALE);return;}
        s.project=latest;finish(0);return;
    }
    if(r.expectedHeaderCrc!=(empty?0:latest.checksum)){finish(SUSAMUNE_STATE_STALE);return;}
    if(r.command==SUSAMUNE_STATE_CMD_TAS_COMMIT){
        if(record.generation==0xffffffffu || s.project.generation!=record.generation+1){finish(SUSAMUNE_STATE_STALE);return;}
        if(s.project.gameId!=s.game || s.project.configId!=s.config || (!empty && (s.project.buildCrc!=latest.buildCrc || s.project.sceneKey!=latest.sceneKey || memcmp(s.project.startKey,latest.startKey,8)))){finish(SUSAMUNE_STATE_WRONG_CONFIG);return;}
        s.part=0;s.verifyParts=true;s.phase=PROJECTPART;return;
    }
    if(record.generation==0xffffffffu){finish(SUSAMUNE_STATE_FULL);return;}
    s.project=latest;
    if(r.command==SUSAMUNE_STATE_CMD_TAS_RENAME){if(empty){finish(SUSAMUNE_STATE_NOT_FOUND);return;}++s.project.generation;memcpy(s.project.name,s.mailbox->requestName,32);s.project.checksum=SusamuneTasManifestCrc(&s.project);projectPrepare(1);}
    else projectPrepare(2);
}
void projectClean(){
    if(s.request.command==SUSAMUNE_STATE_CMD_TAS_DELETE){
        while(s.cleanIndex<s.count){const char *n=s.files[s.cleanIndex++].name;
            if(!memcmp(n,s.projectFile,12) && !memcmp(n+12,"_s",2) && !n[22] && decimalId(n+14)){memcpy(s.filename,n,32);s.phase=PROJECTREMOVE;return;}}
        s.phase=PROJECTFINAL;return;
    }
    const auto &old=s.projects[1-s.projectBank];
    while(old.state==1 && projectRecordValid(old) && s.cleanIndex<4){unsigned id=partId(old.manifest,s.cleanIndex++);bool keep=!id;
        for(unsigned i=0;i<4;++i)if(id==partId(s.project,i) || id==partId(s.projects[s.projectBank].manifest,i))keep=true;
        if(!keep){partName(s.projectId,id,s.filename);s.phase=PROJECTREMOVE;return;}}
    s.id=s.projectId;finish(0);
}
void projectIo(){
    if(s.phase==PROJECT0 || s.phase==PROJECT1){unsigned bank=s.phase==PROJECT1;s.ticket=s.host->read(s.projectFile,&s.projects[bank],sizeof(ProjectRecord),bank*kSector);}
    else if(s.phase==PROJECTCREATE)s.ticket=s.host->create(s.projectFile,2*kSector);
    else if(s.phase==PROJECTBLANK){s.projectCheck={};s.ticket=s.host->write(s.projectFile,&s.projectCheck,sizeof(ProjectRecord),kSector);}
    else if(s.phase==PROJECTWRITE)s.ticket=s.host->write(s.projectFile,&s.projectNext,sizeof(ProjectRecord),(1-s.projectBank)*kSector);
    else if(s.phase==PROJECTVERIFY)s.ticket=s.host->read(s.projectFile,&s.projectCheck,sizeof(ProjectRecord),(1-s.projectBank)*kSector);
    else if(s.phase==PROJECTREMOVE)s.ticket=s.host->remove(s.filename);
    else if(s.phase==PROJECTFINAL)s.ticket=s.host->remove(s.projectFile);
}
void projectResult(const DolphinFiles::Result &result){
    if(s.phase==PROJECTREMOVE && s.request.command!=SUSAMUNE_STATE_CMD_TAS_DELETE){s.phase=PROJECTCLEAN;return;}
    if(result.error){
        if(s.request.command==SUSAMUNE_STATE_CMD_TAS_CATALOG && result.error==-4){++s.scan;s.phase=SCAN;return;}
        if(s.phase==PROJECTREMOVE && result.error==-4){s.phase=PROJECTCLEAN;return;}
        fail(ioError(result.error));return;
    }
    if(s.phase==PROJECT0){s.phase=PROJECT1;return;}
    if(s.phase==PROJECT1){projectLoaded();return;}
    if(s.phase==PROJECTCREATE){s.created=true;s.phase=PROJECTBLANK;return;}
    if(s.phase==PROJECTBLANK){s.projects[0]=s.projects[1]={};s.projectBank=1;projectPrepare(0);return;}
    if(s.phase==PROJECTWRITE){s.phase=PROJECTVERIFY;return;}
    if(s.phase==PROJECTVERIFY){
        if(memcmp(&s.projectNext,&s.projectCheck,sizeof(ProjectRecord)) || !projectRecordValid(s.projectCheck)){fail(SUSAMUNE_STATE_IO_ERROR);return;}
        s.created=false;s.id=s.projectId;
        if(s.request.command==SUSAMUNE_STATE_CMD_TAS_BEGIN){finish(0);return;}
        if(s.request.command==SUSAMUNE_STATE_CMD_TAS_DELETE){s.phase=LIST;return;}
        s.cleanIndex=0;s.phase=PROJECTCLEAN;return;
    }
    if(s.phase==PROJECTREMOVE){s.phase=PROJECTCLEAN;return;}
    if(s.phase==PROJECTFINAL){s.id=s.projectId;finish(0);}
}
