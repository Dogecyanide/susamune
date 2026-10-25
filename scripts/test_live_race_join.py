"""Production code-entry routing with already connected group members."""
import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#define TIMEWARP_LIVE_RACING 1
#define IS_EMULATOR 1
#include "susamune/live_group.hxx"
#include "susamune/live_invites.hxx"
#include "susamune/live_p2p.hxx"
#include "susamune/live_transport.hxx"
using u32=unsigned;
extern "C" void* memset(void*d,int c,__SIZE_TYPE__ n){auto*p=(unsigned char*)d;while(n--)*p++=c;return d;}
extern "C" void* memcpy(void*d,const void*s,__SIZE_TYPE__ n){auto*p=(unsigned char*)d;auto*q=(const unsigned char*)s;while(n--)*p++=*q++;return d;}
extern "C" int memcmp(const void*a,const void*b,__SIZE_TYPE__ n){auto*p=(const unsigned char*)a;auto*q=(const unsigned char*)b;while(n--){if(*p!=*q)return *p<*q?-1:1;++p;++q;}return 0;}
static unsigned stops;
namespace LiveRaceSession {void stop(Session&){++stops;}}
namespace Session=LiveRaceSession;
namespace LiveGroup {void replacePeer(Room&,const TWLiveEndpoint&,const TWLiveEndpoint&,unsigned) {}}
static struct State {
    Session::Session session;LiveP2P::Punch punch;LiveP2P::Code own,friendCode;
    unsigned punchMs;bool active,connected,addressed,friendKnown,hosting,unreachable,started;const char*message;
} s;
static LiveGroup::Room sGroup;
static LiveInvites::State sInvites;
namespace Text {const char*connecting="connecting",*invalidSettings="invalid",*roomFirst="room",*badCode="bad",*ownCode="own",*gettingAddress="address";}
static unsigned nowMs(){return 1000;}
static bool startSession(unsigned){return true;}
'''
SCENARIO = r'''
#define API extern "C" __declspec(dllexport)
#define CHECK(x) do{if(!(x))return __LINE__;}while(0)
static TWLiveEndpoint endpoint(unsigned player){return TWLiveEndpoint{{192,0,2,(unsigned char)player},48222,0};}
API unsigned joinScenario(unsigned manual){
 s={};sGroup={};stops=0;s.active=s.connected=s.addressed=s.hosting=true;s.friendKnown=manual;
 s.own={endpoint(1),1234};sGroup.active=sGroup.host=true;sGroup.config.rules.players=4;
 sGroup.primary=&s.session;s.session.info.connected=true;s.session.info.peer=endpoint(2);
 LiveP2P::reset(s.punch,s.own.secret,LiveP2P::HOST);
 LiveP2P::Punch first;LiveP2P::reset(first,s.own.secret,LiveP2P::JOINER);LiveP2P::add(first,s.own.endpoint,LiveP2P::HOST);
 unsigned char packet[LiveP2P::PUNCH_BYTES];CHECK(LiveP2P::due(first,0,100,packet)==sizeof(packet));
 CHECK(LiveP2P::receive(s.punch,endpoint(2),packet,sizeof(packet),100,true));
 CHECK(s.punch.peers[0].state==LiveP2P::OPEN);
 LiveInvites::reset(sInvites,1234,3);
 if(!manual)CHECK(LiveInvites::connected(sInvites,endpoint(2))==-1);
 CHECK(LiveInvites::set(sInvites,0,{endpoint(2),3456}));
 CHECK(LiveInvites::connected(sInvites,endpoint(2))==0);
 char code[LiveP2P::CODE_CHARS+1];CHECK(LiveP2P::encode({endpoint(3),4567},code));
 CHECK(!enterGuestCode(1,code));
 CHECK(!memcmp(&sInvites.slots[1].punch.peers[0].endpoint,&s.friendCode.endpoint,sizeof(TWLiveEndpoint)));
 CHECK(sInvites.slots[1].punch.peers[0].state==LiveP2P::PUNCHING);
 CHECK(guestName(0)&&!guestName(1));
 CHECK(s.session.info.connected&&!stops&&s.connected&&s.own.secret==1234);
 return 0;
}
API unsigned inviteScenario(unsigned scenario){
 LiveInvites::State invites;LiveInvites::reset(invites,1234,3);
 if(scenario==0){
  CHECK(LiveInvites::connected(invites,endpoint(2))==-1);
  CHECK(!LiveInvites::permits(invites,endpoint(2)));
  CHECK(LiveInvites::set(invites,0,{endpoint(2),3456}));
  CHECK(LiveInvites::connected(invites,endpoint(2))==0);
  CHECK(LiveInvites::set(invites,1,{endpoint(3),4567}));
  CHECK(LiveInvites::set(invites,2,{endpoint(4),5678}));
 }else{
  for(unsigned i=0;i<3;++i)CHECK(LiveInvites::set(invites,i,{endpoint(i+2),4567+i}));
 }
 if(scenario==3){
  LiveInvites::clear(invites,1);
  CHECK(!LiveInvites::permits(invites,endpoint(3)));
  CHECK(LiveInvites::connected(invites,endpoint(3))==-1);
  CHECK(LiveInvites::permits(invites,endpoint(2))&&LiveInvites::permits(invites,endpoint(4)));
  CHECK(LiveInvites::set(invites,1,{endpoint(5),890}));
  CHECK(!LiveInvites::permits(invites,endpoint(3))&&LiveInvites::permits(invites,endpoint(5)));
  return 0;
 }
 if(scenario==1){
  CHECK(!LiveInvites::set(invites,2,{endpoint(2),999}));
  CHECK(LiveInvites::set(invites,1,{endpoint(5),789}));
  CHECK(LiveInvites::find(invites,endpoint(2))==0&&LiveInvites::find(invites,endpoint(4))==2);
  CHECK(LiveInvites::find(invites,endpoint(5))==1);
  return 0;
 }
 LiveP2P::Punch first;LiveP2P::reset(first,1234,LiveP2P::JOINER);LiveP2P::add(first,endpoint(1),LiveP2P::HOST);
 unsigned char packet[LiveP2P::PUNCH_BYTES];CHECK(LiveP2P::due(first,0,100,packet)==sizeof(packet));
 CHECK(LiveInvites::receive(invites,endpoint(2),packet,sizeof(packet),100));
 CHECK(LiveInvites::find(invites,endpoint(3))==1&&LiveInvites::find(invites,endpoint(4))==2);
 CHECK(invites.slots[1].punch.peers[0].state==LiveP2P::PUNCHING);
 if(scenario==2){
  auto mapped=endpoint(3);mapped.port=50000;
  // Make this IP unique: real independent-house guests normally have distinct IPs.
  mapped.ip[2]=3;auto advertised=mapped;advertised.port=48222;
  CHECK(LiveInvites::set(invites,1,{advertised,4567}));
  CHECK(LiveInvites::receive(invites,mapped,packet,sizeof(packet),110));
  CHECK(LiveInvites::find(invites,mapped)==1);
  CHECK(invites.slots[1].punch.peers[0].state==LiveP2P::OPEN);
 }else if(scenario==3){
  packet[7]^=1;
  CHECK(LiveInvites::receive(invites,endpoint(3),packet,sizeof(packet),110));
  CHECK(invites.slots[1].punch.peers[0].state==LiveP2P::PUNCHING);
 }else{
  for(unsigned i=1;i<3;++i){
   CHECK(LiveP2P::due(invites.slots[i].punch,0,200,packet)==sizeof(packet));
   CHECK(invites.slots[i].punch.peers[0].endpoint.ip[3]==i+2);
  }
 }
 return 0;
}
'''


class JoinRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        match = (ROOT / 'src/live_race.cpp').read_text()
        codec = (ROOT / 'src/live_race_session.cpp').read_text()
        source = work / 'join.cpp'
        source.write_text(HARNESS + codec[codec.index('// P2P codec begin'):codec.index('// P2P codec end')]
                          + function(match, 'usePeer') + function(match, 'guestName')
                          + function(match, 'enterGuestCode') + function(match, 'enterCode') + SCENARIO)
        dll = work / 'join.dll'
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-std=c++17', '-shared', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Wl,/noentry',
            '-O2', '-DTIMEWARP_LIVE_RACING=1', '-I', str(ROOT / 'include'), str(source),
            str(ROOT / 'src/live_invites.cpp'), '-o', str(dll)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: FreeLibrary(cls.lib._handle))
        cls.lib.joinScenario.argtypes = [C.c_uint]
        cls.lib.inviteScenario.argtypes = [C.c_uint]

    def test_uninvited_peer_rejected_then_explicit_invites_keep_slots(self):
        self.assertEqual(self.lib.joinScenario(0), 0, 'failed harness line')

    def test_revoked_invitation_cannot_reclaim_the_replacement_slot(self):
        self.assertEqual(self.lib.inviteScenario(3), 0)

    def test_new_code_replaces_manually_entered_first_guest(self):
        self.assertEqual(self.lib.joinScenario(1), 0, 'failed harness line')

    def test_three_independent_invites_survive_old_guest_packets(self):
        self.assertEqual(self.lib.inviteScenario(0), 0)

    def test_duplicate_invite_rejected_and_retry_keeps_other_slots(self):
        self.assertEqual(self.lib.inviteScenario(1), 0)

    def test_changed_nat_port_stays_with_its_guest(self):
        self.assertEqual(self.lib.inviteScenario(2), 0)

    def test_wrong_room_secret_cannot_change_pending_invite(self):
        self.assertEqual(self.lib.inviteScenario(3), 0)


if __name__ == '__main__':
    unittest.main()
