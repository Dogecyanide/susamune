#include "susamune/dolphin_bba.hxx"
#if IS_EMULATOR && TIMEWARP_LIVE_RACING
#include <Dolphin/types.h>

// Register protocol: devkitPro libogc BBA driver and Dolphin EXI_DeviceEthernet.
extern "C" {
s32 EXILock(s32,s32,void *);
s32 EXIUnlock(s32);
s32 EXISelect(s32,s32,u32);
s32 EXIDeselect(s32);
s32 EXIImmEx(s32,void *,s32,u32);
s32 EXIGetID(s32,s32,u32 *);
}
namespace DolphinBba {
namespace {
bool transfer(unsigned reg,void *data,unsigned bytes,bool write) {
    u32 command=(write?0xc0000000u:0x80000000u)|(reg<<8);
    if(!EXISelect(0,2,5))return false;
    const bool ok=EXIImmEx(0,&command,4,1) && EXIImmEx(0,data,bytes,write?1:0);
    EXIDeselect(0);return ok;
}
unsigned read(unsigned reg,unsigned bytes=1) {
    u8 data[4]={};if(!transfer(reg,data,bytes,false))return 0;
    unsigned value=0;for(unsigned i=0;i<bytes;++i)value|=unsigned(data[i])<<(i*8);return value;
}
void write(unsigned reg,unsigned value,unsigned bytes=1) {
    u8 data[4];for(unsigned i=0;i<bytes;++i)data[i]=value>>(i*8);
    transfer(reg,data,bytes,true);
}
void resetRing() {write(0x16,1,2);write(0x18,1,2);}
}
bool init(unsigned char mac[6]) {
    u32 id=0;if(!EXIGetID(0,2,&id) || id!=0x04020200u || !EXILock(0,2,nullptr))return false;
    write(0,1);write(0,0);
    const bool ok=transfer(0x20,mac,6,false);
    // Poll receive pages; no EXI interrupt handler is installed over the game's SDK.
    write(0x08,0);write(0x09,0xff);write(0x01,0x12);
    write(0x0c,0,2);write(0x0a,1,2);write(0x1a,15,2);resetRing();
    write(0x50,0x80);write(0,8);EXIUnlock(0);return ok;
}
bool send(const unsigned char *frame,unsigned bytes) {
    if(!frame || bytes<60 || bytes>1514 || !EXILock(0,2,nullptr))return false;
    bool ok=false;
    if(!(read(0)&6)) {
        ok=transfer(0x48,const_cast<unsigned char *>(frame),bytes,true);
        if(ok)write(0,read(0)|4);
    }
    EXIUnlock(0);return ok;
}
unsigned receive(unsigned char *frame,unsigned capacity) {
    if(!EXILock(0,2,nullptr))return 0;
    unsigned used=0,rp=read(0x18,2)&4095,wp=read(0x16,2)&4095;
    if(rp<1 || rp>15 || wp<1 || wp>15)resetRing();
    else if(rp!=wp) {
        const unsigned descriptor=read(rp<<8,4),next=descriptor&4095,length=(descriptor>>12)&4095;
        if(next<1 || next>15 || next==rp)resetRing();
        else {
            if(length>=18 && length<=1518 && length-4<=capacity && !(descriptor&0x7f000000u)) {
                used=length-4;
                unsigned first=0x1000-(rp<<8)-4;if(first>used)first=used;
                if(!transfer((rp<<8)+4,frame,first,false) ||
                    (first<used && !transfer(0x100,frame+first,used-first,false)))used=0;
            }
            write(0x18,next,2);write(0x09,0xff);
        }
    }
    EXIUnlock(0);return used;
}
}
#endif
