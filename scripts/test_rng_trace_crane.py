"""Exercise native crane observations and exact savestate cache ownership."""
import ctypes as C
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

from test_iling_attempt_lifecycle import function

ROOT=Path(__file__).resolve().parents[1]
BASE=0x81000000
NAMES=["crane90 0","crane90 1","crane90 2","craneUpDown 0","craneUpDown 1"]
KEYS=[0x5c04,0x5c05,0x5c06,0x09ce,0x09cf]
VTABLES=[(0x803c66d4,0x803c6570),(0x803cecdc,0x803ceb78),(0x803c64cc,0x803c6368)]


class CraneTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="moonshine-crane-trace-")
        cls.addClassCleanup(cls.temp.cleanup)
        kernel=C.WinDLL("kernel32",use_last_error=True)
        kernel.VirtualAlloc.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint]
        kernel.VirtualAlloc.restype=C.c_void_p
        kernel.VirtualFree.argtypes=[C.c_void_p,C.c_size_t,C.c_uint]
        cls.region=kernel.VirtualAlloc(BASE,0x30000,0x3000,4)
        if cls.region!=BASE:
            if cls.region:kernel.VirtualFree(cls.region,0,0x8000)
            raise unittest.SkipTest("Fixed native-address test window unavailable")
        cls.addClassCleanup(lambda:kernel.VirtualFree(BASE,0,0x8000))
        source=(ROOT/"src/rng_control.cpp").read_text()
        code=r"""
#include "susamune/rng_control.hxx"
extern "C" int _fltused=0;
struct Vec {f32 x,y,z;};
struct TMapObjBase {u8 pad[0xfc];u16 mState,padfe;u32 pad100;int mStateTimer;u32 pad108;Vec mInitialPosition,mInitialRotation;};
struct TMarDirector {int _260;u8 mAreaID;};
static TMarDirector director;static TMarDirector *gpMarDirector=&director;static bool directorPresent,threadFinished;
enum {SETTING_RICCO_CRANE_SPEED,SETTING_KING_BOO_ALWAYS_FRUIT};
static unsigned settingChoice;struct Settings {unsigned get(int){return settingChoice;}bool getBool(int){return false;}}gSettings;
static f32 seenRetail;static unsigned calls;
static void rotateRetail(void *p){f32 *speed=(f32*)((u8*)p+0x144);((f32*)((u8*)p+0x30))[1]+=*speed;seenRetail=*speed;++calls;}
static void verticalRetail(void *p){(void)p;seenRetail=*(f32*)0x81020000u;++calls;}
static const __UINTPTR_TYPE__ kRotYRetailControl=(__UINTPTR_TYPE__)&rotateRetail;
static const __UINTPTR_TYPE__ kUpDownRetailControl=(__UINTPTR_TYPE__)&verticalRetail;
extern "C" void *memset(void *p,int value,__SIZE_TYPE__ n){u8*b=(u8*)p;for(__SIZE_TYPE__ i=0;i<n;++i)b[i]=(u8)value;return p;}

static int gSetupThread;
static bool OSIsThreadTerminated(const int*){return threadFinished;}
namespace RetailInput {TMarDirector *stageDirector(){return directorPresent?&director:nullptr;}}
#if TEST_REGION==0
#define SUSAMUNE_MEM1_ADDR(j,u,p) (j)
#elif TEST_REGION==1
#define SUSAMUNE_MEM1_ADDR(j,u,p) (u)
#else
#define SUSAMUNE_MEM1_ADDR(j,u,p) (p)
#endif
"""
        for name in ("kRiccoArea","kCraneCount","kRotYCount","kNoRoll","kUpDownControlSlot","kRotYControlSlot"):
            code+=re.search(r"const u(?:8|16|32) "+name+r"\s*=.*?;",source,re.S).group(0)+"\n"
        code+="const u32 kUpDownRetailSpeed=0x81020000u;\n"
        for name in ("kCraneNames","kCraneKeys"):
            code+=re.search(r"const (?:char \*const|u16) "+name+r"\[.*?\n};",source,re.S).group(0)+"\n"
        code+=re.search(r"struct CraneRoll \{.*?\n};",source,re.S).group(0)+"\n"
        code+="CraneRoll sCranes[kCraneCount];void *sKingBooSlot;bool sKingBooRestorePending;\n"
        for name in ("sameText","traceCraneSpan","savedCraneIdentity","clearCraneCache","craneStateHash","inRicco","craneIndex","cranePercent","findCrane","rngControlBeforeStageSetup","rngControlOnSavestateLoaded","rngControlValidateSavestate","rngControlCaptureSavestate","rngControlRestoreSavestate","rngControlRestoreLegacySavestate","rngControlSavestateRequired","rngControlTraceCrane","susamuneCraneRotYControl","susamuneCraneUpDownControl"):
            body=function(source,name)
            if name=="craneIndex":body=body.replace('*reinterpret_cast<const char *const *>(bytes + 4)','reinterpret_cast<const char *>(static_cast<__UINTPTR_TYPE__>(*reinterpret_cast<const u32 *>(bytes + 4)))')
            code+=body+"\n"
        code+=r"""
#define API extern "C" __declspec(dllexport)
API void reset(){rngControlBeforeStageSetup();directorPresent=threadFinished=true;director._260=1;director.mAreaID=3;gpMarDirector=&director;settingChoice=calls=0;}
API void ready(unsigned present,unsigned loaded,unsigned area,unsigned thread){directorPresent=present;director._260=loaded;director.mAreaID=area;threadFinished=thread;gpMarDirector=present?&director:nullptr;}
API void owner(unsigned index,unsigned address,unsigned roll,unsigned saved,unsigned speed){sCranes[index].actor=(void*)(__UINTPTR_TYPE__)address;sCranes[index].roll=roll;sCranes[index].speedCaptured=saved;__builtin_memcpy(&sCranes[index].retailSpeed,&speed,4);}
static unsigned hash(const void*p,unsigned n){const u8*b=(const u8*)p;unsigned h=2166136261u;while(n--)h=(h^*b++)*16777619u;return h;}
API unsigned saveCache(u32*out,unsigned count){return rngControlCaptureSavestate(out,count);}
API unsigned validCache(const u32*in,unsigned count){return rngControlValidateSavestate(in,count);}
API unsigned restoreCache(const u32*in,unsigned count){return rngControlRestoreSavestate(in,count);}
API void rehash(u32*in){in[17]=craneStateHash(in);}
API unsigned row(unsigned index,unsigned field){const CraneRoll&r=sCranes[index];unsigned speed;__builtin_memcpy(&speed,&r.retailSpeed,4);return field==0?(unsigned)(__UINTPTR_TYPE__)r.actor:field==1?speed:r.roll|(r.speedCaptured?0x10000u:0);}
API unsigned stateHash(){return hash(sCranes,sizeof(sCranes));}
API void kingLoad(){rngControlOnSavestateLoaded();}
API void legacyLoad(){rngControlRestoreLegacySavestate();}
API unsigned cacheRequired(){return rngControlSavestateRequired();}
API void choice(unsigned n){settingChoice=n;}
API unsigned control(unsigned index){seenRetail=0;if(index<3)susamuneCraneRotYControl(sCranes[index].actor);else susamuneCraneUpDownControl(sCranes[index].actor);unsigned bits;__builtin_memcpy(&bits,&seenRetail,4);return bits;}
API unsigned observe(unsigned index,unsigned*out,unsigned cap){
 const unsigned before=hash(sCranes,sizeof(sCranes)),global=*(const u32*)kUpDownRetailSpeed;
 const unsigned result=rngControlTraceCrane(index,out,cap);
 return before==hash(sCranes,sizeof(sCranes))&&global==*(const u32*)kUpDownRetailSpeed?result:0xdeadbeefu;
}
"""
        cls.libs=[]
        for region in range(3):
            p=Path(cls.temp.name)/f"crane{region}.cpp";p.write_text(code)
            result=subprocess.run([str(ROOT/"toolchain/clang++.exe"),"--target=x86_64-pc-windows-msvc",
                "-shared","-nostdlib","-O2","-fno-builtin-memset","-fuse-ld=lld","-Wl,/noentry",f"-DTEST_REGION={region}",
                "-I",str(ROOT/"include"),str(p),"-o",str(p.with_suffix(".dll"))],capture_output=True,text=True)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
            lib=C.CDLL(str(p.with_suffix(".dll")))
            cls.addClassCleanup(lambda lib=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(lib._handle)))
            lib.owner.argtypes=[C.c_uint]*5;lib.observe.argtypes=[C.c_uint,C.POINTER(C.c_uint),C.c_uint]
            lib.observe.restype=C.c_uint
            for name in ('saveCache','validCache','restoreCache'):
                getattr(lib,name).argtypes=[C.POINTER(C.c_uint),C.c_uint];getattr(lib,name).restype=C.c_uint
            lib.rehash.argtypes=[C.POINTER(C.c_uint)];lib.row.argtypes=[C.c_uint,C.c_uint];lib.row.restype=C.c_uint
            lib.stateHash.restype=C.c_uint;lib.control.argtypes=[C.c_uint];lib.control.restype=C.c_uint
            cls.libs.append(lib)

    def setUp(self):
        C.memset(BASE,0,0x30000)
        for lib in self.libs:lib.reset()
        self.put(BASE+0x20000,0x3f123456)

    def put(self,address,value):C.c_uint.from_address(address).value=value

    def actor(self,region,index,*,saved=False,speed=0x3e234567):
        lib=self.libs[region];p=BASE+index*0x1000;n=BASE+0x10000+index*32
        for off in range(0x10,0x148,4):self.put(p+off,0x3d000000+off)
        self.put(p,VTABLES[region][index>=3]);self.put(p+4,n)
        C.c_ushort.from_address(p+8).value=KEYS[index]
        C.memmove(n,NAMES[index].encode()+b"\0",len(NAMES[index])+1)
        C.c_ushort.from_address(p+0xfc).value=3
        self.put(p+0x104,0xfffffffd)
        lib.owner(index,p,0x1234,saved,speed)
        return p

    def read(self,region,index,cap=24):
        out=(C.c_uint*24)(*[0xdeadbeef]*24)
        result=self.libs[region].observe(index,out,cap)
        return result,tuple(out)

    def test_all_five_stable_identities_and_native_fields_on_all_regions(self):
        for region in range(3):
            for index in range(5):
                p=self.actor(region,index,saved=index<3)
                before=C.string_at(p,0x148)
                result,out=self.read(region,index)
                self.assertEqual(result,24)
                self.assertEqual(out[:6],(index,p,0x1234,2 if index<3 else 1,3,0xfffffffd))
                for start,offset in ((6,0x10),(9,0x30),(12,0x10c),(15,0x118)):
                    self.assertEqual(out[start:start+3],tuple(0x3d000000+offset+4*i for i in range(3)))
                self.assertEqual(out[18:22],tuple(0x3d000138+4*i for i in range(4)))
                self.assertEqual(out[22:],(0x3f123456,0x3e234567 if index<3 else 0))
                self.assertEqual(C.string_at(p,0x148),before)

    def test_unavailable_phase_never_publishes_or_changes_output(self):
        self.actor(0,0)
        for values in ((0,1,3,1),(1,0,3,1),(1,1,1,1),(1,1,3,0)):
            self.libs[0].ready(*values)
            self.assertEqual(self.read(0,0),(0,(0xdeadbeef,)*24))

    def test_capacity_index_null_and_missing_owner_are_checked_first(self):
        self.actor(0,0)
        self.assertEqual(self.read(0,0,23),(0,(0xdeadbeef,)*24))
        self.assertEqual(self.read(0,5),(0,(0xdeadbeef,)*24))
        self.assertEqual(self.read(0,1),(0,(0xdeadbeef,)*24))
        self.assertEqual(self.libs[0].observe(0,None,24),0)

    def test_bad_actor_extent_alignment_and_roll_are_rejected(self):
        for address,roll in ((0,1),(BASE+1,1),(0x817ffebc,1),(0x90000000,1),(BASE,0xffff),(BASE,0x8000)):
            self.actor(0,0);self.libs[0].owner(0,address,roll,0,0)
            self.assertEqual(self.read(0,0),(0,(0xdeadbeef,)*24))

    def test_wrong_class_key_or_name_never_authorizes_extended_reads(self):
        for offset,value,size in ((0,VTABLES[0][1],4),(8,0x5c05,2),(4,0x817ffff8,4),(4,0,4)):
            p=self.actor(0,0)
            if size==4:self.put(p+offset,value)
            else:C.c_ushort.from_address(p+offset).value=value
            self.assertEqual(self.read(0,0),(0,(0xdeadbeef,)*24))
        self.actor(0,0);C.memmove(BASE+0x10000,b"crane90 x\0",10)
        self.assertEqual(self.read(0,0),(0,(0xdeadbeef,)*24))

    def test_float_bits_are_not_rounded_or_normalized(self):
        p=self.actor(0,2,saved=True,speed=0x80000000)
        self.put(p+0x144,0x7fc01234);self.put(BASE+0x20000,0x80000000)
        result,out=self.read(0,2)
        self.assertEqual((result,out[21],out[22],out[23]),(24,0x7fc01234,0x80000000,0x80000000))

    def test_saved_rotating_speed_and_shared_vertical_speed_stay_distinct(self):
        p=self.actor(0,0,saved=False)
        self.assertEqual(self.read(0,0)[1][23],0)
        self.libs[0].owner(0,p,0x1234,1,0x3e111111)
        self.assertEqual(self.read(0,0)[1][21:],(0x3d000144,0x3f123456,0x3e111111))

    def test_stage_reset_drops_previous_actors(self):
        self.actor(0,0);self.assertEqual(self.read(0,0)[0],24)
        self.libs[0].reset()
        self.assertEqual(self.read(0,0),(0,(0xdeadbeef,)*24))


    def save(self,region,count=128):
        out=(C.c_uint*max(128,count))(*([0xdeadbeef]*max(128,count)))
        return self.libs[region].saveCache(out,count),out

    def rows(self,region):return tuple(tuple(self.libs[region].row(i,f) for f in range(3))for i in range(5))

    def test_state_payload_is_bounded_canonical_and_capture_does_not_mutate(self):
        for region in range(3):
            for i in range(5):self.actor(region,i,saved=i<3)
            before=self.libs[region].stateHash();result,out=self.save(region)
            self.assertEqual(result,1);self.assertEqual(tuple(out[:2]),(0x43524e47,1));self.assertEqual(tuple(out[18:]),(0,)*110)
            for i in range(5):self.assertEqual(tuple(out[2+i*3:5+i*3]),(BASE+i*0x1000,0x3e234567 if i<3 else 0,0x11234 if i<3 else 0x1234))
            self.assertEqual(self.libs[region].stateHash(),before);self.assertEqual(self.libs[region].validCache(out,128),1)
            result,short=self.save(region,18);self.assertEqual(result,1);self.assertEqual(tuple(short[:18]),tuple(out[:18]));self.assertEqual(short[18],0xdeadbeef)
        self.assertEqual(self.libs[0].saveCache(None,128),0);self.assertEqual(self.save(0,17)[0],0);self.assertEqual(self.save(0,129)[0],0)

    def test_structural_validation_does_not_follow_pre_restore_actor(self):
        self.actor(0,2,saved=True);result,out=self.save(0);self.assertEqual(result,1)
        out[2+2*3]=0x817ff000;self.libs[0].rehash(out)
        self.assertEqual(self.libs[0].validCache(out,128),1)
        out[2+2*3]=BASE+0x2f000;self.libs[0].rehash(out)
        self.assertEqual(self.libs[0].restoreCache(out,128),0);self.assertEqual(self.rows(0),((0,0,0xffff),)*5)

    def test_every_corrupt_field_is_rejected_and_failed_restore_clears_all_rows(self):
        self.actor(0,0,saved=True);result,original=self.save(0);self.assertEqual(result,1)
        bad=[(0,0),(1,2),(2,0x81000001),(2,0x817ffec0),(3,0x7fc00000),(4,0x20000),(4,0x18000),(4,0x1234),(18,1),(127,1)]
        for index,value in bad:
            out=(C.c_uint*128)(*original);out[index]=value;self.libs[0].rehash(out)
            self.assertEqual(self.libs[0].validCache(out,128),0,(index,value))
        original[17]^=1;self.assertEqual(self.libs[0].validCache(original,128),0)
        self.assertEqual(self.libs[0].restoreCache(original,128),0);self.assertEqual(self.rows(0),((0,0,0xffff),)*5)

    def test_empty_rows_replace_reset_cache_instead_of_leaving_residue(self):
        result,empty=self.save(0,18);self.assertEqual(result,1)
        for i in range(5):self.actor(0,i,saved=i<3)
        native=C.string_at(BASE,0x6000);self.assertEqual(self.libs[0].restoreCache(empty,18),1)
        self.assertEqual(self.rows(0),((0,0,0xffff),)*5);self.assertEqual(C.string_at(BASE,0x6000),native)

    def test_post_restore_wrong_name_key_or_vtable_never_partially_adopts(self):
        for bad in ('name','key','class'):
            self.setUp()
            for i in range(5):self.actor(0,i,saved=i<3)
            result,out=self.save(0);self.assertEqual(result,1)
            if bad=='name':C.memmove(BASE+0x10000+4*32,b'wrong\0',6)
            if bad=='key':C.c_ushort.from_address(BASE+0x4000+8).value=0x09ce
            if bad=='class':self.put(BASE+0x4000,VTABLES[0][0])
            self.assertEqual(self.libs[0].restoreCache(out,128),0);self.assertEqual(self.rows(0),((0,0,0xffff),)*5)

    def test_same_address_new_epoch_restores_original_speed_with_control_off(self):
        for region in range(3):
            lib=self.libs[region];speedA=0x3d4ccccd;speedB=0x3ecccccd
            p=self.actor(region,2,saved=True,speed=speedA);self.put(p+0x144,speedA);native=C.string_at(p,0x14c)
            result,out=self.save(region);self.assertEqual(result,1);saved=self.rows(region)
            lib.reset();self.actor(region,2,saved=True,speed=speedB);lib.owner(2,p,0x7111,1,speedB)
            C.memmove(p,native,len(native));self.assertEqual(lib.restoreCache(out,128),1);self.assertEqual(self.rows(region),saved)
            lib.choice(0)
            for _ in range(5):self.assertEqual(lib.control(2),speedA)
            self.assertEqual(C.c_uint.from_address(p+0x144).value,speedA)

    def test_active_rotating_control_restores_roll_and_original_speed_then_off(self):
        lib=self.libs[0];p=self.actor(0,1,saved=True,speed=0x3d99999a);result,out=self.save(0);self.assertEqual(result,1)
        lib.reset();self.actor(0,1,saved=True,speed=0x3e99999a);lib.owner(1,p,0x7111,1,0x3e99999a)
        self.assertEqual(lib.restoreCache(out,128),1);lib.choice(4)
        percent=61+((0x1234*20)>>15);expected=C.c_float(C.c_float(.0015).value*percent)
        self.assertEqual(lib.control(1),struct.unpack('<I',bytes(expected))[0]);lib.choice(0)
        self.assertEqual(lib.control(1),0x3d99999a)

    def test_vertical_control_restores_roll_without_treating_native_144_as_speed(self):
        lib=self.libs[0];p=self.actor(0,3,saved=False);result,out=self.save(0);self.assertEqual(result,1)
        lib.reset();self.actor(0,3,saved=False);lib.owner(3,p,0x7777,0,0);self.assertEqual(lib.restoreCache(out,128),1)
        native144=C.c_uint.from_address(p+0x144).value;globalBits=C.c_uint.from_address(BASE+0x20000).value;lib.choice(3)
        percent=41+((0x1234*20)>>15);initial=C.c_float.from_address(BASE+0x20000).value
        expected=C.c_float(C.c_float(initial*percent).value*C.c_float(.01).value)
        self.assertEqual(lib.control(3),struct.unpack('<I',bytes(expected))[0]);self.assertEqual(C.c_uint.from_address(BASE+0x20000).value,globalBits)
        self.assertEqual(C.c_uint.from_address(p+0x144).value,native144)
        out[4+3*3]|=0x10000;self.libs[0].rehash(out);self.assertEqual(lib.validCache(out,128),0)

    def test_uncaptured_rotating_speed_recaptures_restored_native_value(self):
        lib=self.libs[0];p=self.actor(0,0,saved=False,speed=0x7fc00000);self.put(p+0x144,0x3d123456);result,out=self.save(0,18);self.assertEqual(result,1)
        lib.owner(0,p,0x7777,1,0x3f765432);self.assertEqual(lib.restoreCache(out,18),1);lib.choice(0)
        self.assertEqual(lib.control(0),0x3d123456);self.assertEqual(lib.row(0,1),0x3d123456)

    def test_legacy_fallback_clears_only_cranes_and_outer_king_callback_keeps_tagged_rows(self):
        lib=self.libs[0]
        for i in range(5):self.actor(0,i,saved=i<3)
        result,out=self.save(0);self.assertEqual(result,1);rows=self.rows(0);lib.kingLoad();self.assertEqual(self.rows(0),rows)
        native=C.string_at(BASE,0x6000);lib.legacyLoad();self.assertEqual(self.rows(0),((0,0,0xffff),)*5);self.assertEqual(C.string_at(BASE,0x6000),native)
        self.assertEqual(lib.cacheRequired(),1);lib.ready(1,1,1,1);self.assertEqual(lib.cacheRequired(),0)


if __name__=="__main__":unittest.main()
