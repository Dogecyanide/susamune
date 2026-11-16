"""Exercise production HTTPS, framing and catalogue code; --live uses public read-only endpoints."""
from pathlib import Path
import concurrent.futures
import ctypes as C
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/ghost-service-tests'
CC=Path('C:/msys64/mingw64/bin/gcc.exe')

class Entry(C.Structure):
    _fields_=[('title',C.c_char*64),('author',C.c_char*32),('id',C.c_char*40),('path',C.c_char*384),
              ('sha256',C.c_ubyte*32),('bytes',C.c_uint),('resultQf',C.c_uint),('durationQf',C.c_uint)]
class Page(C.Structure):
    _fields_=[('magic',C.c_uint),('count',C.c_uint),('total',C.c_uint),('reserved',C.c_uint),
              ('next',C.c_char*256),('entries',Entry*4)]
SEND=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p,C.c_uint)
WAIT=C.CFUNCTYPE(C.c_int,C.c_void_p)
class Io(C.Structure):
    _fields_=[('context',C.c_void_p),('send',SEND),('recv',SEND),('wait',WAIT),('sink',C.c_void_p)]

def build():
    os.environ['PATH']=str(CC.parent)+os.pathsep+os.environ.get('PATH','')
    OUT.mkdir(exist_ok=True,parents=True)
    shim=OUT/'shim.c'
    text='''#include <stdlib.h>
#include "GhostServiceTls.h"
#include "GhostServiceJson.h"
#include "GhostServiceAccount.h"
static struct GhostAccount account;
static struct GhostServiceUpload upload;
__declspec(dllexport) void test_account_reset(void){memset(&account,0,sizeof(account));memset(&upload,0,sizeof(upload));}
__declspec(dllexport) void test_description(const void *p,unsigned n){memset(&upload,0,sizeof(upload));if(n<=sizeof(upload))memcpy(&upload,p,n);}
__declspec(dllexport) int test_account(unsigned op,unsigned now,const void *ghost,unsigned bytes,GhostAccountHttp http,struct GhostServiceAccountInfo *out){
 struct GhostJson *j=calloc(1,sizeof(*j));char *response=calloc(1,32768);
 struct GhostAccountWork w={0};w.json=j;w.response=response;w.capacity=32768;w.upload=upload;
 int r=GhostAccountRun(&account,&w,op,now,ghost,bytes,http);GhostAccountInfo(&account,now,out);
 free(response);free(j);return r;}
__declspec(dllexport) int test_http(const void *p,unsigned n,unsigned chunk,void *out,unsigned cap,unsigned *used){
 struct GhostHttp h;unsigned at=0;GhostHttpInit(&h,out,cap);
 while(at<n){unsigned take=n-at;if(take>chunk)take=chunk;if(!GhostHttpFeed(&h,(const char*)p+at,take))return 0;at+=take;}
 *used=h.used;return h.complete;}
__declspec(dllexport) int test_page(const void *p,unsigned n,struct GhostServicePage *out){
 struct GhostJson *j=calloc(1,sizeof(*j));int r=GhostServiceParsePage(j,p,n,out);free(j);return r;}
__declspec(dllexport) int test_tls(const struct GhostTlsIo *io,const char *path,void *out,unsigned cap,unsigned *used,unsigned now,const unsigned char *entropy){
 struct GhostTls *t=calloc(1,sizeof(*t));int r=GhostTlsGet(t,io,path,out,cap,used,now,entropy);free(t);return r;}
__declspec(dllexport) void *test_session_new(void){return calloc(1,sizeof(struct GhostTls));}
__declspec(dllexport) void test_session_free(void *p){free(p);}
__declspec(dllexport) int test_session_get(struct GhostTls *t,const struct GhostTlsIo *io,const char *path,void *out,unsigned cap,unsigned *used,unsigned now,const unsigned char *entropy){return GhostTlsGet(t,io,path,out,cap,used,now,entropy);}
__declspec(dllexport) const char *test_session_id(struct GhostTls *t){return t->http.requestId;}
__declspec(dllexport) int test_route_support(const void *p,unsigned n){struct GhostJson *j=calloc(1,sizeof(*j));int r=GhostServiceRouteSortSupported(j,p,n);free(j);return r;}
__declspec(dllexport) unsigned test_header(const void *p,unsigned n,unsigned kind){struct GhostHttp h;GhostHttpInit(&h,0,32768);GhostHttpFeed(&h,p,n);return kind?h.retryAfter:h.status;}
__declspec(dllexport) unsigned test_retry_date(const void *p,unsigned n,unsigned now){struct GhostHttp h;GhostHttpInit(&h,0,32768);GhostHttpFeed(&h,p,n);return GhostHttpRetryDelay(&h,now);}
'''
    if not shim.exists() or shim.read_text()!=text:shim.write_text(text)
    files=list((ROOT/'launcher/third_party/bearssl/src').rglob('*.c'))
    files += [ROOT/'launcher/kernel'/name for name in ('GhostServiceTls.c','GhostServiceHttp.c','GhostServiceJson.c','GhostServiceAccount.c')]+[shim]
    flags=['-Os','-std=gnu99','-ffunction-sections','-fdata-sections','-DBR_USE_UNIX_TIME=0','-DBR_USE_URANDOM=0','-DBR_USE_WIN32_RAND=0']
    flags+=['-iquote'+str(ROOT/'launcher/kernel')]
    for path in ['include','launcher/third_party/bearssl/inc','launcher/third_party/bearssl/src']:
        flags+=['-I'+str(ROOT/path)]
    headers = list((ROOT/'launcher/third_party/bearssl').rglob('*.h'))
    headers += list((ROOT/'launcher/kernel').glob('GhostService*'))
    headers += [ROOT/'include/susamune/ghost_service.h', ROOT/'include/susamune/ghost_format.h']
    newest_header = max(p.stat().st_mtime for p in headers)
    def compile(p):
        obj=OUT/(p.stem+'.o')
        if not obj.exists() or obj.stat().st_mtime<max(p.stat().st_mtime,newest_header):
            result=subprocess.run([str(CC),*flags,'-c',str(p),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:raise RuntimeError(result.stderr)
        return obj
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(compile,files))
    dll=OUT/'ghost-service.dll'
    subprocess.run([str(CC),'-shared','-static-libgcc','-Wl,--gc-sections','-o',str(dll),*map(str,objects)],check=True,capture_output=True)
    lib=C.CDLL(str(dll))
    lib.test_http.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.POINTER(C.c_uint)]
    lib.test_page.argtypes=[C.c_void_p,C.c_uint,C.POINTER(Page)]
    lib.test_tls.argtypes=[C.POINTER(Io),C.c_char_p,C.c_void_p,C.c_uint,C.POINTER(C.c_uint),C.c_uint,C.c_void_p]
    lib.test_session_new.restype=C.c_void_p
    lib.test_session_free.argtypes=[C.c_void_p]
    lib.test_session_get.argtypes=[C.c_void_p]+lib.test_tls.argtypes
    lib.test_session_id.argtypes=[C.c_void_p];lib.test_session_id.restype=C.c_char_p
    return lib

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.lib=build()
    def http(self,data,chunk=1,cap=512):
        out=C.create_string_buffer(cap);used=C.c_uint()
        ok=self.lib.test_http(data,len(data),chunk,out,cap,C.byref(used))
        return ok,out.raw[:used.value]
    def test_fragmented_framing(self):
        data=b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello'
        for size in [1,2,7,1024]:self.assertEqual(self.http(data,size),(1,b'hello'))
        data=b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nhe\r\n3\r\nllo\r\n0\r\nX-Test: yes\r\n\r\n'
        for size in [1,3,13,1024]:self.assertEqual(self.http(data,size),(1,b'hello'))
    def test_reject_ambiguous_and_truncated_messages(self):
        for data in [b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhell',
            b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Length: 5\r\n\r\nhello',
            b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nTransfer-Encoding: chunked\r\n\r\nhello',
            b'HTTP/1.1 302 Found\r\nContent-Length: 0\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Length: 99999999999\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Encoding: gzip\r\n\r\nhello',
            b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nhello']:
            self.assertEqual(self.http(data)[0],0,data)
    def fixture(self):
        return dict(api_version=1, catalogue_schema=1, total=1, next_cursor=None,
                    items=[dict(id='public-test-ghost', title='Pianta 2',
                                author=dict(username='runner'), timing=dict(result_qf=1234, duration_qf=1200),
                                file=dict(byte_length=256, sha256='ab'*32,
                                          download_url='https://cvadewafbthfhvzgdgay.supabase.co/storage/v1/object/public/ghosts/test.smsghost'))])
    def parse(self,p):
        data=json.dumps(p).encode();page=Page()
        return self.lib.test_page(data,len(data),C.byref(page)),page
    def test_catalogue_schema(self):
        ok,p=self.parse(self.fixture());self.assertEqual(ok,1);self.assertGreater(p.count,0)
        self.assertTrue(p.entries[0].path.startswith(b'/storage/v1/object/public/ghosts/'))
        self.assertEqual((p.entries[0].resultQf,p.entries[0].durationQf),(1234,1200))
    def test_missing_finish_is_distinct_from_clip_duration(self):
        source=self.fixture();source['items'][0]['timing']['result_qf']=None
        ok,p=self.parse(source);self.assertEqual(ok,1)
        self.assertEqual((p.entries[0].resultQf,p.entries[0].durationQf),(0xffffffff,1200))
        source['items'][0]['timing']['result_qf']=0x80000000
        self.assertEqual(self.parse(source)[0],0)
    def test_bad_catalogue(self):
        for key,value in [('byte_length',2000000),('sha256','z'*64),('download_url','https://evil.example/x'),
                          ('download_url','https://cvadewafbthfhvzgdgay.supabase.co.evil.example/x')]:
            p=self.fixture();p['items'][0]['file'][key]=value;self.assertEqual(self.parse(p)[0],0)
        p=self.fixture();p['items']=p['items']*5;self.assertEqual(self.parse(p)[0],0)
        self.assertEqual(self.lib.test_page(b'{"a":[}',8,C.byref(Page())),0)

    def test_rate_limit_headers_and_capabilities(self):
        data=b'HTTP/1.1 429 Too Many Requests\r\nRetry-After: 37\r\nContent-Length: 0\r\n\r\n'
        self.assertEqual(self.lib.test_header(data,len(data),0),429)
        self.assertEqual(self.lib.test_header(data,len(data),1),37)
        from datetime import datetime,timezone
        date=b'HTTP/1.1 503 Unavailable\r\nRetry-After: Sun, 25 Oct 2026 19:00:00 GMT\r\nContent-Length: 0\r\n\r\n'
        now=int(datetime(2026,10,25,18,59,30,tzinfo=timezone.utc).timestamp())
        self.assertEqual(self.lib.test_retry_date(date,len(date),now),30)
        for sorts,expected in [(['newest'],0),(['newest','route'],1)]:
            data=json.dumps(dict(catalogue=dict(sorts=sorts))).encode()
            self.assertEqual(self.lib.test_route_support(data,len(data)),expected)

def live(lib):
    host='cvadewafbthfhvzgdgay.supabase.co'
    def get(path,cap=32768,clock=None):
        with socket.create_connection((host,443),timeout=10) as sock:
            sock.settimeout(0.1)
            deadline=time.monotonic()+45
            @SEND
            def send(_,p,n):
                try:return sock.send(C.string_at(p,n))
                except socket.timeout:return 0
                except OSError:return -20
            @SEND
            def recv(_,p,n):
                try:
                    data=sock.recv(n)
                    if not data:return -20
                    C.memmove(p,data,len(data));return len(data)
                except socket.timeout:return 0
                except OSError:return -20
            @WAIT
            def wait(_):return 0 if time.monotonic()<deadline else -27
            io=Io(None,send,recv,wait,None);out=C.create_string_buffer(cap);used=C.c_uint();entropy=os.urandom(32)
            r=lib.test_tls(C.byref(io),path.encode(),out,cap,C.byref(used),clock or int(time.time()),entropy)
            return r,out.raw[:used.value]
    api='/functions/v1/moonshine-api/v1'
    r,data=get(api+'/capabilities');assert r==0,(r,data[:100])
    assert json.loads(data)['api_version']==1
    (OUT/'live-capabilities.json').write_bytes(data)
    r,data=get(api+'/ghosts?limit=4&playable_on=jp');assert r==0,r
    page=Page();assert lib.test_page(data,len(data),C.byref(page))==1
    (OUT/'live-catalogue.json').write_bytes(data)
    entry=page.entries[0];r,ghost=get(entry.path.decode(),entry.bytes);assert r==0,r
    assert len(ghost)==entry.bytes and hashlib.sha256(ghost).digest()==bytes(entry.sha256)
    (OUT/'live-download.smsghost').write_bytes(ghost)
    r,_=get(api+'/capabilities',clock=2051222400);assert r==-21,('expired certificate accepted',r)
    print('Verified production BearSSL: public capabilities, catalogue, SHA256 download, rejected expired certificate.')

def live_reuse(lib):
    from urllib.parse import quote
    host='cvadewafbthfhvzgdgay.supabase.co'
    api='/functions/v1/moonshine-api/v1'
    evidence=[]
    with socket.create_connection((host,443),timeout=15) as sock:
        sock.settimeout(.1);deadline=time.monotonic()+120
        @SEND
        def send(_,p,n):
            try:return sock.send(C.string_at(p,n))
            except socket.timeout:return 0
            except OSError:return -20
        @SEND
        def recv(_,p,n):
            try:
                data=sock.recv(n)
                if not data:return -20
                C.memmove(p,data,len(data));return len(data)
            except socket.timeout:return 0
            except OSError:return -20
        @WAIT
        def wait(_):return 0 if time.monotonic()<deadline else -27
        io=Io(None,send,recv,wait,None);context=lib.test_session_new()
        def get(path,cap=32768):
            out=C.create_string_buffer(cap);used=C.c_uint();started=time.monotonic()
            result=lib.test_session_get(context,C.byref(io),path.encode(),out,cap,C.byref(used),int(time.time()),os.urandom(32))
            assert result==0,(path,result)
            evidence.append(dict(path=path,bytes=used.value,seconds=round(time.monotonic()-started,3),request_id=lib.test_session_id(context).decode()))
            assert evidence[-1]['request_id']
            return out.raw[:used.value]
        try:
            caps=get(api+'/capabilities')
            assert lib.test_route_support(caps,len(caps))==1
            first=get(api+'/ghosts?limit=4&sort=route&playable_on=jp')
            first_page=Page();assert lib.test_page(first,len(first),C.byref(first_page))
            cursor=first_page.next.decode();assert cursor
            second=get(api+'/ghosts?limit=4&sort=route&playable_on=jp&cursor='+quote(cursor,safe=''))
            second_page=Page();assert lib.test_page(second,len(second),C.byref(second_page))
            assert not ({e.id for e in first_page.entries}&{e.id for e in second_page.entries})
            entry=second_page.entries[0];ghost=get(entry.path.decode(),entry.bytes)
            assert len(ghost)==entry.bytes and hashlib.sha256(ghost).digest()==bytes(entry.sha256)
            (OUT/'reuse-download.smsghost').write_bytes(ghost)
            (OUT/'reuse-catalogue.json').write_bytes(second)
        finally:lib.test_session_free(context)
    (OUT/'reuse-proof.json').write_text(json.dumps(dict(scope='Production BearSSL on PC, one TCP/TLS connection; not Wii timing',requests=evidence),indent=2))
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':
    if '--reuse' in sys.argv:live_reuse(build())
    elif '--live' in sys.argv:live(build())
    else:unittest.main()
