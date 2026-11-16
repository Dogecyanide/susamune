"""Test the asynchronous native HTTPS adapter; --live uses public read-only endpoints."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import hmac,hashlib,json,os,socket,subprocess,sys,time,unittest
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/test-dolphin-https'
IO=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p,C.c_uint)
class Io(C.Structure):_fields_=[('context',C.c_void_p),('send',IO),('recv',IO)]
class Request(C.Structure):_fields_=[('method',C.c_char_p),('headers',C.c_char_p),('body',C.c_void_p),('bytes',C.c_uint)]
class Info(C.Structure):_fields_=[(n,C.c_uint) for n in ('used','httpStatus','tlsError','reusable','complete')]
INIT=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.c_void_p)
START=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_char_p,C.POINTER(Request),C.c_void_p,C.c_uint)
STEP=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(Io))
INFO=C.CFUNCTYPE(None,C.c_void_p,C.POINTER(Info))
DERIVE=C.CFUNCTYPE(None,C.c_void_p,C.c_void_p,C.c_void_p)
SHA256=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_void_p)
class Api(C.Structure):_fields_=[(n,C.c_uint) for n in ('magic','version','apiBytes','workBytes')]+[('initialize',INIT),('start',START),('step',STEP),('info',INFO),('derive',DERIVE),('sha256',SHA256)]

def build():
    OUT.mkdir(parents=True,exist_ok=True);cc=Path('C:/msys64/mingw64/bin/gcc.exe')
    os.environ['PATH']=str(cc.parent)+os.pathsep+os.environ.get('PATH','')
    sources=sorted((ROOT/'launcher/third_party/bearssl/src').rglob('*.c'))
    sources += [ROOT/'native/dolphin_https/engine.c',ROOT/'launcher/kernel/GhostServiceHttp.c']
    flags=['-Os','-std=c99','-DBR_USE_UNIX_TIME=0','-DBR_USE_URANDOM=0','-DBR_USE_WIN32_RAND=0']
    flags += ['-I'+str(ROOT/p) for p in ['include','launcher/third_party/bearssl/inc','launcher/third_party/bearssl/src']]
    dependencies=list((ROOT/'launcher/third_party/bearssl').rglob('*.h'))+list((ROOT/'launcher/kernel').glob('GhostService*'))+[ROOT/'include/susamune/dolphin_https.h']
    stamp=hashlib.sha256(b''.join(p.read_bytes() for p in dependencies)+repr(flags).encode()).digest()
    def one(p):
        obj=OUT/(p.stem+'.o');h=obj.with_suffix('.hash');value=hashlib.sha256(p.read_bytes()+stamp).hexdigest()
        if not obj.exists() or not h.exists() or h.read_text()!=value:
            r=subprocess.run([str(cc),*flags,'-c',str(p),'-o',str(obj)],capture_output=True,text=True)
            if r.returncode:raise ValueError(r.stderr)
            h.write_text(value)
        return obj
    with ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(one,sources))
    rsp=OUT/'objects.rsp';rsp.write_text('\n'.join(chr(34)+p.as_posix()+chr(34) for p in objects))
    dll=OUT/'https.dll'
    r=subprocess.run([str(cc),'-shared','-static-libgcc','-Wl,--export-all-symbols','-o',str(dll),'@'+str(rsp)],capture_output=True,text=True)
    if r.returncode:raise ValueError(r.stderr)
    lib=C.CDLL(str(dll));api=Api.in_dll(lib,'moonshine_https_api');api._library=lib
    return api

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.api=build()
    def setUp(self):
        self.work=C.create_string_buffer(self.api.workBytes);self.out=C.create_string_buffer(32768)
    def initialize(self,clock=1793016000):return self.api.initialize(self.work,clock,os.urandom(32))
    def test_api_and_initialization_fail_closed(self):
        self.assertEqual((self.api.magic,self.api.version,self.api.apiBytes),(0x4d485431,2,C.sizeof(Api)))
        self.assertLess(self.api.workBytes,65536)
        self.assertEqual(self.api.start(self.work,b'/x',None,self.out,len(self.out)),-24)
        self.assertEqual(self.initialize(1),-22)
        self.assertEqual(self.api.initialize(self.work,1793016000,None),-23)
        self.assertEqual(self.initialize(),0)
    def test_seed_derivation_matches_independent_hmac_and_hash(self):
        seed=bytes(range(32));n=C.create_string_buffer(32);entropy=C.create_string_buffer(32)
        self.api.derive(seed,n,entropy)
        self.assertEqual(n.raw,hmac.digest(seed,b'Moonshine Dolphin seed v1','sha256'))
        self.assertEqual(entropy.raw,hmac.digest(seed,b'Moonshine Dolphin TLS v1','sha256'))
        self.assertNotEqual(n.raw,entropy.raw)
        for data in (b'',b'hello',bytes(range(256))*256):
            self.api.sha256(data,len(data),n);self.assertEqual(n.raw,hashlib.sha256(data).digest())
    def test_request_admission_and_duplicate_start(self):
        self.assertEqual(self.initialize(),0)
        for path in [b'',b'x',b'/bad\r\nX: yes',b'/'+b'x'*701,b'/\xff']:
            self.assertEqual(self.api.start(self.work,path,None,self.out,len(self.out)),-24)
        bad=Request(b'DELETE',b'',None,0)
        self.assertEqual(self.api.start(self.work,b'/x',C.byref(bad),self.out,len(self.out)),-24)
        bad=Request(b'POST',b'',None,1)
        self.assertEqual(self.api.start(self.work,b'/x',C.byref(bad),self.out,len(self.out)),-24)
        self.assertEqual(self.api.start(self.work,b'/x',None,self.out,len(self.out)),0)
        self.assertEqual(self.api.start(self.work,b'/x',None,self.out,len(self.out)),-24)
    def test_would_block_yields_and_bounds_transport_chunks(self):
        self.assertEqual(self.initialize(),0);self.assertEqual(self.api.start(self.work,b'/x',None,self.out,len(self.out)),0)
        calls=[]
        @IO
        def blocked(_,data,n):calls.append(n);return 0
        io=Io(None,blocked,blocked)
        for i in range(40):self.assertEqual(self.api.step(self.work,C.byref(io)),1)
        self.assertEqual(len(calls),40);self.assertLessEqual(max(calls),2048)
        @IO
        def invalid(_,data,n):return n+1
        io=Io(None,invalid,blocked)
        self.assertEqual(self.api.step(self.work,C.byref(io)),-20)

def live(api):
    host='cvadewafbthfhvzgdgay.supabase.co';proof={'scope':'Production asynchronous HTTPS adapter on host sockets; public GET only','requests':[]}
    def session(clock,paths,expired=False):
        work=C.create_string_buffer(api.workBytes);out=C.create_string_buffer(65536)
        assert api.initialize(work,clock,os.urandom(32))==0
        with socket.create_connection((host,443),timeout=20) as sock:
            sock.setblocking(False)
            @IO
            def send(_,p,n):
                try:return sock.send(C.string_at(p,n))
                except BlockingIOError:return 0
                except OSError:return -1
            @IO
            def recv(_,p,n):
                try:
                    data=sock.recv(n)
                    if not data:return -1
                    C.memmove(p,data,len(data));return len(data)
                except BlockingIOError:return 0
                except OSError:return -1
            io=Io(None,send,recv)
            for path in paths:
                assert api.start(work,path.encode(),None,out,len(out))==0
                begin=time.monotonic();calls=0;maximum=0
                while True:
                    start=time.monotonic();result=api.step(work,C.byref(io));maximum=max(maximum,time.monotonic()-start);calls+=1
                    if result!=1:break
                    if time.monotonic()-begin>30:raise TimeoutError('TLS request')
                    time.sleep(.001)
                info=Info();api.info(work,C.byref(info))
                row=dict(path=path,result=result,http_status=info.httpStatus,tls_error=info.tlsError,bytes=info.used,seconds=round(time.monotonic()-begin,3),steps=calls,longest_step_ms=round(maximum*1000,3),expired_clock=expired)
                proof['requests'].append(row)
                if expired:assert result==-21 and info.tlsError!=0,row
                else:
                    assert result==0 and info.httpStatus==200,row
                    data=out.raw[:info.used];json.loads(data)
                    row['sha256']=hashlib.sha256(data).hexdigest()
    session(int(time.time()),['/functions/v1/moonshine-api/v1/capabilities','/functions/v1/moonshine-api/v1/ghosts?limit=4&playable_on=jp'])
    session(int(time.time()),['/functions/v1/moonshine-api/v1/capabilities'])
    session(2208988800,['/functions/v1/moonshine-api/v1/capabilities'],True)
    proof['passed']=True;(OUT/'live-receipt.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':
    if '--live' in sys.argv:live(build())
    else:unittest.main()
