"""Actual group/session engines over a lossy bounded datagram network."""
import ctypes as C
from _ctypes import FreeLibrary
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "susamune/live_group.hxx"
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){auto*a=(unsigned char*)d;auto*b=(const unsigned char*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int c,__SIZE_TYPE__ n){auto*a=(unsigned char*)d;while(n--)*a++=c;return d;}
namespace S=LiveRaceSession; namespace G=LiveGroup; namespace R=LiveGroupRules;
struct Node {S::Session session;G::Room room;unsigned id,starts,cancels,poseMask,lastX[4],lastRegion[4],lastEpoch[4],lastSequence[4];};
struct Packet {unsigned from,to,bytes;unsigned char data[256];};
static Node nodes[4];static Packet packets[128];static unsigned count,now,players,violations,dropped,dropEvery,sent;
static unsigned portShift[4];
static S::Endpoint endpoint(unsigned i){return S::Endpoint{{10,0,0,(unsigned char)(i+1)},(unsigned short)(3000+i+portShift[i]),0};}
static G::Config config(unsigned draft,unsigned playlist){G::Config c={};c.rules=R::Config{(unsigned char)players,(unsigned char)(playlist?1:3),3,draft!=0,false};c.entry=7;c.catalogue=1;c.playlist=playlist;return c;}
static unsigned workerFrames,frames;
static bool send(void*ctx,const S::Endpoint&to,const void*data,unsigned bytes){
 Node&n=*(Node*)ctx;unsigned dest=to.ip[3]-1;
 if(workerFrames){unsigned queued=0;for(unsigned i=0;i<count;++i)queued+=packets[i].from==n.id;if(queued>=4)return false;}
 if(dest>=players||bytes>256||to.port!=3000+dest+portShift[dest]||count==128){++violations;return false;}
 if(dropEvery&&++sent%dropEvery==0){++dropped;return true;}
 Packet&p=packets[count++];p.from=n.id;p.to=dest;p.bytes=bytes;memcpy(p.data,data,bytes);return true;}
static Packet latest[4];static bool hasLatest[4],disabled[4],blocked[4];static unsigned poseHits[4][4];
static bool sendPose(void*ctx,const S::Endpoint&to,const void*data,unsigned bytes){
 if(!workerFrames)return send(ctx,to,data,bytes);
 Node&n=*(Node*)ctx;Packet&p=latest[n.id];p.from=n.id;p.to=to.ip[3]-1;p.bytes=bytes;
 memcpy(p.data,data,bytes);hasLatest[n.id]=true;return true;}
static bool valid(void*,unsigned e,unsigned,bool){return e<120;}
static bool choices(void*,unsigned short*out,unsigned n,unsigned){for(unsigned i=0;i<n;++i)out[i]=10+i;return true;}
static bool start(void*c,const G::Config&,const LivePlaylist::Plan*p){Node&n=*(Node*)c;++n.starts;return !n.room.config.playlist||(p&&p->count==50);}
static void cancel(void*c){++((Node*)c)->cancels;}
static void remote(void*c,unsigned who,const MSRHeader&h,const MSRPose&p,unsigned){Node&n=*(Node*)c;n.poseMask|=1u<<who;++poseHits[n.id][who];n.lastX[who]=p.x;n.lastRegion[who]=h.region;n.lastEpoch[who]=p.sceneEpoch;n.lastSequence[who]=h.sequence;}
static G::Hooks hooks(Node&n){return G::Hooks{&n,valid,choices,start,cancel,remote};}
static void onControl(void*c,const MSRHeader&h,const void*d,unsigned bytes){Node&n=*(Node*)c;const auto*p=(const unsigned char*)d;
 if(n.id&&h.kind==MSR_READY&&bytes==28&&p[0]==G::Welcome)G::adopt(n.room,n.session,config(0,0),hooks(n),d,bytes);
 else G::control(n.room,0,h,d,bytes);}
static void onPose(void*c,const MSRHeader&h,const MSRPose&p,unsigned ms){G::pose(((Node*)c)->room,0,h,p,ms);}
static void initNode(unsigned i){Node&n=nodes[i];n.id=i;S::Config c={};c.name[0]='A'+i;c.pin=1234;c.nonceHigh=91+i;c.nonceLow=200+now+i;c.region=i%3;c.timing=1;S::Callbacks cb={&n,send,sendPose,onPose,onControl};S::init(n.session,c,cb);}
#define API extern "C" __declspec(dllexport)
API int reset(unsigned total,unsigned draft,unsigned playlist,unsigned loss){
 memset(nodes,0,sizeof(nodes));count=now=violations=dropped=sent=0;players=total;dropEvery=loss;workerFrames=frames=0;memset(portShift,0,sizeof(portShift));memset(hasLatest,0,sizeof(hasLatest));memset(disabled,0,sizeof(disabled));memset(blocked,0,sizeof(blocked));memset(poseHits,0,sizeof(poseHits));
 for(unsigned i=0;i<players;++i)initNode(i);
 S::startHost(nodes[0].session,S::Endpoint{},now);G::Config c=config(draft,playlist);LivePlaylist::Plan plan={};
 if(playlist){plan.count=50;for(unsigned i=0;i<50;++i)plan.items[i]={(unsigned char)i,0};c.playlistHash=LivePlaylist::hash(plan);}
 if(!G::host(nodes[0].room,nodes[0].session,c,playlist?&plan:nullptr,hooks(nodes[0]),1))return 0;
 for(unsigned i=1;i<players;++i)S::startGuest(nodes[i].session,endpoint(0),now);return 1;}
static void deliver(const Packet&p){
 if(blocked[p.from]||blocked[p.to]||disabled[p.to])return;
 Node&n=nodes[p.to];
 if(n.room.active&&n.room.host)G::receive(n.room,endpoint(p.from),p.data,p.bytes,now);
 else S::receivePacket(n.session,endpoint(p.from),p.data,p.bytes,now);}
API void advance(unsigned ms){for(unsigned elapsed=0;elapsed<ms;elapsed+=16){now+=16;++frames;
 for(unsigned i=0;i<players;++i){if(disabled[i])continue;Node&n=nodes[i];S::tick(n.session,now);
  if(n.session.info.state==S::FAILED||n.session.info.state==S::STOPPED){
   S::Endpoint peer=n.session.info.peer;initNode(i);
   if(!i)S::startHost(n.session,peer,now);else S::startGuest(n.session,endpoint(0),now);}
  G::tick(n.room,now);}
 unsigned pending=(!workerFrames||!(frames%workerFrames))?count:0;for(unsigned i=0;i<pending;++i){Packet p=packets[0];for(unsigned j=1;j<count;++j)packets[j-1]=packets[j];--count;deliver(p);}
 if(workerFrames&&!(frames%workerFrames))for(unsigned i=0;i<players;++i)if(hasLatest[i]){hasLatest[i]=false;deliver(latest[i]);}
 }}
API void worker(unsigned cadence){workerFrames=cadence;}
API void block(unsigned node,unsigned value){blocked[node]=value!=0;}
API unsigned hits(unsigned node,unsigned player){return poseHits[node][player];}
API unsigned get(unsigned node,unsigned field,unsigned index){const Node&n=nodes[node];const auto&r=n.room.rules;
 switch(field){case 0:return n.room.active;case 1:return G::connectedCount(n.room);case 2:return r.phase;case 3:return n.room.self;
 case 4:return R::actor(r);case 5:return r.selected;case 6:return n.starts;case 7:return r.round;case 8:return r.winner;
 case 9:return r.roundWins[index];case 10:return r.setWins[index];case 11:return n.poseMask;case 12:return n.lastX[index];
 case 13:return n.lastRegion[index];case 14:return n.room.playlist.complete;case 15:return n.cancels;case 16:return violations;case 17:return dropped;
 case 18:return r.rotation;case 19:return r.generation;case 20:return r.readyMask;case 21:return n.room.members[index].name[0];
 case 22:return n.lastEpoch[index];case 23:return n.lastSequence[index];default:return 0;}}
API int ban(unsigned node,unsigned candidate){return G::ban(nodes[node].room,candidate);}
API int ready(unsigned node){return G::ready(nodes[node].room,true);}
API int finish(unsigned node,int time){return G::result(nodes[node].room,time,time>=0);}
API void pose(unsigned node){MSRPose p={};p.x=100+node;p.area=2;p.flags=1;p.remoteMs=now;p.sceneEpoch=1;G::localPose(nodes[node].room,p,now);}
API int nextMatch(){return G::configure(nodes[0].room,nodes[0].room.config,nullptr);}
API int cancelRace(unsigned node){return G::cancel(nodes[node].room);}
API void restart(unsigned node){disabled[node]=false;S::stop(nodes[node].session);initNode(node);S::startGuest(nodes[node].session,endpoint(0),now);}
API void replacePort(unsigned node){auto old=endpoint(node);portShift[node]+=100;G::replacePeer(nodes[0].room,old,endpoint(node),now);restart(node);}
API void defer(unsigned node){disabled[node]=true;S::stop(nodes[node].session);G::stop(nodes[node].room);
 for(unsigned i=0;i<count;)if(packets[i].from==node||packets[i].to==node){for(unsigned j=i+1;j<count;++j)packets[j-1]=packets[j];--count;}else ++i;}
'''


class GroupNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'build')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        source = path / 'group.cpp'
        source.write_text(HARNESS)
        dll = path / 'group.dll'
        result = subprocess.run([str(ROOT / 'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-std=c++17', '-DTIMEWARP_LIVE_RACING=1', '-shared', '-nostdlib', '-fno-builtin',
            '-fuse-ld=lld', '-Wl,/noentry', '-O2', '-I', str(ROOT / 'include'), str(source),
            *[str(ROOT / 'src' / f'{s}.cpp') for s in ('live_group', 'live_group_rules', 'live_race_session', 'live_playlist')],
            '-o', str(dll)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: FreeLibrary(cls.lib._handle))
        for name, count in [('reset', 4), ('advance', 1), ('get', 3), ('ban', 2), ('ready', 1),
                            ('finish', 2), ('pose', 1), ('nextMatch', 0), ('cancelRace', 1), ('restart', 1), ('defer', 1), ('worker', 1), ('block', 2), ('hits', 2), ('replacePort', 1)]:
            getattr(cls.lib, name).argtypes = [C.c_uint] * count

    def g(self, n, field, index=0):
        return self.lib.get(n, field, index)

    def test_third_and_fourth_guests_join_after_listening_timeouts(self):
        for loss in (0, 7):
            with self.subTest(loss=loss):
                self.assertTrue(self.lib.reset(4, 0, 0, loss))
                self.lib.defer(2)
                self.lib.defer(3)
                self.lib.advance(65000)
                self.assertEqual(self.g(0, 1), 2)
                self.assertEqual(self.g(1, 1), 2)
                self.lib.restart(2)
                self.lib.advance(7000)
                for node in range(3):
                    self.assertEqual(self.g(node, 1), 3)
                self.lib.advance(65000)
                self.lib.restart(3)
                self.lib.advance(7000)
                for node in range(4):
                    self.assertEqual(self.g(node, 1), 4)
                self.assertEqual(self.g(0, 16), 0)

    def room(self, players, draft=False, playlist=False, loss=0):
        self.n = players
        self.assertTrue(self.lib.reset(players, draft, playlist, loss))
        self.lib.advance(5000)
        for n in range(players):
            self.assertEqual(self.g(n, 0), 1)
            self.assertEqual(self.g(n, 1), players)
            for i in range(players):
                self.assertIn(self.g(n, 21, i), range(ord('A'), ord('A') + players))
        self.assertEqual(self.g(0, 16), 0)

    def draft(self):
        for candidate in range(self.n):
            actor = self.g(0, 4)
            node = next(n for n in range(self.n) if self.g(n, 3) == actor)
            self.assertTrue(self.lib.ban(node, candidate))
            self.lib.advance(1500)
        for n in range(self.n):
            self.assertEqual(self.g(n, 2), 2)
            self.assertEqual(self.g(n, 5), 10 + self.n)

    def race(self, winner=0):
        starts = self.g(0, 6)
        for n in range(self.n):
            self.assertTrue(self.lib.ready(n))
        self.lib.advance(2000)
        for n in range(self.n):
            self.assertEqual(self.g(n, 2), 3)
            self.assertEqual(self.g(n, 6), starts + 1)
            self.assertTrue(self.lib.finish(n, 100 if n == winner else 200 + n))
        self.lib.advance(4500)

    def test_three_and_four_player_drafts_sets_and_rematch(self):
        for players in (3, 4):
            self.room(players, draft=True, loss=5)
            self.draft()
            self.race(); self.race()
            self.assertEqual(self.g(0, 10, 0), 1)
            self.assertEqual(self.g(0, 18), 1)
            self.draft()
            self.race(); self.race()
            for n in range(players):
                self.assertEqual(self.g(n, 2), 6)
            self.assertTrue(self.lib.nextMatch())
            self.lib.advance(5000)
            for n in range(players):
                self.assertEqual(self.g(n, 19), 2)
                self.assertEqual(self.g(n, 2), 1)
            self.assertGreater(self.g(0, 17), 0)

    def test_start_waits_for_last_warp_ready_player(self):
        for count in (3, 4):
            for last in range(count):
                with self.subTest(players=count, loading_player=last):
                    self.room(count, loss=7)
                    for n in range(count):
                        if n != last:
                            self.assertTrue(self.lib.ready(n))
                    self.lib.advance(5000)
                    for n in range(count):
                        self.assertEqual(self.g(n, 2), 2)
                        self.assertEqual(self.g(n, 6), 0)
                    self.assertTrue(self.lib.ready(last))
                    self.lib.advance(3000)
                    for n in range(count):
                        self.assertEqual(self.g(n, 2), 3)
                        self.assertEqual(self.g(n, 6), 1)

    def test_forfeits_do_not_void_other_players_results(self):
        for players in (3, 4):
            self.room(players, loss=7)
            for n in range(players): self.assertTrue(self.lib.ready(n))
            self.lib.advance(3000)
            self.assertTrue(self.lib.finish(1, C.c_uint(-2).value))
            for n in range(players):
                if n != 1: self.assertTrue(self.lib.finish(n, 100 + n))
            self.lib.advance(5000)
            for n in range(players):
                self.assertEqual(self.g(n, 9, 0), 1)
                self.assertEqual(self.g(n, 1), players)

    def test_everyone_receives_all_other_poses_and_regions(self):
        self.room(4)
        for _ in range(30):
            for n in range(4): self.lib.pose(n)
            self.lib.advance(32)
        for n in range(4):
            self.assertEqual(self.g(n, 11), 15 ^ (1 << self.g(n, 3)))
            for peer in range(4):
                if peer == self.g(n, 3): continue
                source = next(i for i in range(4) if self.g(i, 3) == peer)
                self.assertEqual(self.g(n, 12, peer), 100 + source)
                self.assertEqual(self.g(n, 13, peer), source % 3)
        self.assertEqual(self.g(0, 16), 0)

    def test_reconnected_guest_has_new_relay_timeline_without_an_area_change(self):
        self.room(4)
        for _ in range(40):
            for node in range(4): self.lib.pose(node)
            self.lib.advance(33)
        player = self.g(2, 3)
        previous = [(self.g(n, 22, player), self.g(n, 23, player)) for n in (0, 1, 3)]
        self.lib.defer(2)
        self.lib.advance(16000)
        self.lib.restart(2)
        self.lib.advance(7000)
        for n in range(4): self.assertEqual(self.g(n, 1), 4)
        for _ in range(8):
            for node in range(4): self.lib.pose(node)
            self.lib.advance(33)
        for node, (epoch, sequence) in zip((0, 1, 3), previous):
            self.assertGreater(self.g(node, 22, player), epoch)
            self.assertGreater(self.g(node, 23, player), sequence)

    def test_slower_shared_pose_mailbox_never_starves_a_recipient(self):
        for players in (3, 4):
            for cadence in (2, 3, 4):
                with self.subTest(players=players, worker_frames=cadence):
                    self.room(players, loss=7)
                    self.lib.worker(cadence)
                    for _ in range(1200):
                        for n in range(players): self.lib.pose(n)
                        self.lib.advance(16)
                    for n in range(players):
                        self.assertEqual(self.g(n, 1), players)
                        for other in range(players):
                            if other != self.g(n, 3):
                                self.assertGreater(self.lib.hits(n, other), 100)

    def test_occupied_slots_survive_many_timeouts_and_reverse_rejoins(self):
        for lost in (1, 2):
            with self.subTest(lost=lost):
                self.room(4)
                identities = [self.g(n, 3) for n in range(4)]
                self.lib.block(lost, 1)
                self.lib.advance(100000)
                # Another guest reconnects while the first guest's slot is reserved.
                other = 3
                self.lib.restart(other)
                self.lib.advance(12000)
                self.assertEqual(self.g(other, 3), identities[other])
                self.lib.block(lost, 0)
                self.lib.advance(65000)
                for n in range(4):
                    self.assertEqual(self.g(n, 1), 4)
                    self.assertEqual(self.g(n, 3), identities[n])
                    for player in range(4):
                        owner = identities.index(player)
                        self.assertEqual(self.g(n, 21, player), ord('A') + owner)

    def test_replacing_disconnected_code_preserves_other_guest_slots(self):
        for replaced in (1, 2, 3):
            with self.subTest(guest=replaced):
                self.room(4)
                identities = [self.g(n, 3) for n in range(4)]
                self.lib.block(replaced, 1)
                self.lib.advance(20000)
                self.lib.replacePort(replaced)
                self.lib.block(replaced, 0)
                self.lib.advance(10000)
                for n in range(4):
                    self.assertEqual(self.g(n, 1), 4)
                    self.assertEqual(self.g(n, 3), identities[n])

    def test_playlist_is_complete_before_ready_and_runs_once(self):
        self.room(4, playlist=True, loss=7)
        for n in range(4): self.assertTrue(self.g(n, 14))
        self.race(winner=2)
        for n in range(4): self.assertEqual(self.g(n, 2), 6)

    def test_cancel_clears_ready_and_extra_peer_can_reconnect(self):
        self.room(4)
        for n in range(4): self.assertTrue(self.lib.ready(n))
        self.lib.advance(1500)
        self.assertTrue(self.lib.cancelRace(2))
        self.lib.advance(4000)
        for n in range(4):
            self.assertEqual(self.g(n, 2), 2)
            self.assertEqual(self.g(n, 20), 0)
            self.assertEqual(self.g(n, 15), 1)
        self.lib.restart(3)
        self.lib.advance(7000)
        for n in range(4): self.assertEqual(self.g(n, 1), 4)
        self.race()


if __name__ == '__main__':
    unittest.main()
