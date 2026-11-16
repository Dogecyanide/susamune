"""Verify the native catalogue ABI uses the same bounded parser as Wii."""
from pathlib import Path
import ctypes as C
import json,os,subprocess,unittest
from test_ghost_service import Page
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/test-dolphin-web'
class Query(C.Structure):_fields_=[('cursor',C.c_char*256),('sortRoute',C.c_uint),('filter',C.c_uint)]
QUERY=C.CFUNCTYPE(C.c_int,C.POINTER(Query),C.c_uint,C.c_void_p,C.c_uint)
PAGE=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.POINTER(Page))
ENTRY=C.CFUNCTYPE(C.c_int,C.c_void_p)
DESCRIBE=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_int,C.c_void_p)
CATALOG=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint)
SORT=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint)
class Api(C.Structure):_fields_=[('magic',C.c_uint),('version',C.c_uint),('bytes',C.c_uint),('query',QUERY),('page',PAGE),('entry',ENTRY),('sort',SORT),('describe',DESCRIBE),('catalog',CATALOG)]
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  OUT.mkdir(parents=True,exist_ok=True);os.environ['PATH']='C:/msys64/mingw64/bin'+os.pathsep+os.environ.get('PATH','')
  code=(ROOT/'native/dolphin_https/web.c').read_text().replace('"../../../launcher/kernel/GhostServiceJson.h"','"GhostServiceJson.h"').replace('"../../../launcher/kernel/GhostCanonical.inc"','"GhostCanonical.inc"')
  code=code.replace('return (struct GhostJson *)DOLPHIN_WEB_JSON_BASE;','static struct GhostJson state;return &state;')
  (OUT/'web.c').write_text(code)
  subprocess.run(['C:/msys64/mingw64/bin/g++.exe','-std=c++17','-O2','-I'+str(ROOT/'include'),'-c',str(ROOT/'native/dolphin_https/catalog.cpp'),'-o',str(OUT/'catalog.o')],check=True,capture_output=True)
  r=subprocess.run(['C:/msys64/mingw64/bin/gcc.exe','-std=c99','-O2','-shared','-static-libgcc','-Wl,--export-all-symbols','-I'+str(ROOT/'include'),'-iquote'+str(ROOT/'launcher/kernel'),str(OUT/'web.c'),str(ROOT/'launcher/kernel/GhostServiceJson.c'),str(OUT/'catalog.o'),'-o',str(OUT/'web.dll')],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  cls.lib=C.CDLL(str(OUT/'web.dll'));cls.api=Api.in_dll(cls.lib,'moonshine_web_api')
 def query(self,q,region=1,cap=704):
  out=C.create_string_buffer(704);return self.api.query(C.byref(q),region,out,cap),out.value
 def test_region_level_and_cursor_encoding(self):
  q=Query();q.filter=5|(2<<8)|(20<<16);q.cursor=b'a&b/=+';ok,url=self.query(q)
  self.assertTrue(ok);self.assertIn(b'playable_on=jp&area=4&episode=1&cursor=a%26b%2F%3D%2B',url)
  self.assertIn(b'playable_on=us',self.query(Query(),2)[1]);self.assertIn(b'playable_on=pal',self.query(Query(),3)[1])
 def test_rejects_invalid_or_overlong_queries(self):
  q=Query();q.cursor=b'%'*255;self.assertFalse(self.query(q)[0])
  for field,value in [('filter',1),('filter',62|256),('filter',1|(11<<8)),('filter',1<<24),('sortRoute',2)]:
   q=Query();setattr(q,field,value);self.assertFalse(self.query(q)[0])
  self.assertFalse(self.query(Query(),0)[0]);self.assertFalse(self.query(Query(),4)[0])
  self.assertFalse(self.query(Query(),cap=4)[0])
 def test_catalogue_uses_shared_validation(self):
  item={'id':'abc','title':'Test','author':{'username':'Runner'},'file':{'sha256':'aa'*32,'byte_length':256,'download_url':'https://cvadewafbthfhvzgdgay.supabase.co/storage/v1/object/public/ghosts/a.smsghost'},'timing':{'result_qf':1000,'duration_qf':1000}}
  document={'api_version':1,'catalogue_schema':1,'total':1,'items':[item],'next_cursor':None};out=Page()
  raw=json.dumps(document).encode();self.assertTrue(self.api.page(raw,len(raw),C.byref(out)))
  self.assertEqual(out.count,1);self.assertEqual(out.entries[0].resultQf,1000)
  for url in ['https://evil.invalid/x','https://cvadewafbthfhvzgdgay.supabase.co.evil.invalid/x','https://cvadewafbthfhvzgdgay.supabase.co/storage/v1/object/public/ghosts/../token','https://cvadewafbthfhvzgdgay.supabase.co/storage/v1/object/public/ghosts/%2e%2e/token','https://cvadewafbthfhvzgdgay.supabase.co/storage/v1/object/public/ghosts/%252e%252e/token','https://cvadewafbthfhvzgdgay.supabase.co/storage/v1/object/public/ghosts/a%2fb']:
   item['file']['download_url']=url;raw=json.dumps(document).encode();self.assertFalse(self.api.page(raw,len(raw),C.byref(out)))
 def test_shared_canonical_header_admission(self):
  from test_ghost_format import build_ghost
  raw=build_ghost();info=C.create_string_buffer(128)
  self.assertTrue(self.api.describe(raw,len(raw),0,1,1,info))
  broken=bytearray(raw);broken[48]^=1
  self.assertFalse(self.api.describe(bytes(broken),len(raw),0,1,1,info))
  self.assertFalse(self.api.describe(raw,100,0,1,1,info))
  self.assertFalse(self.api.describe(raw,len(raw),0,0,1,info))
 def test_native_catalogue_keeps_shared_admission_rules(self):
  from test_ghost_format import build_ghost
  raw=build_ghost();info=C.create_string_buffer(128);out=C.create_string_buffer(128)
  self.assertTrue(self.api.describe(raw,len(raw),0,1,1,info))
  self.assertTrue(self.api.catalog(info,out,1,1))
  self.assertFalse(self.api.catalog(info,out,0,1))
  self.assertFalse(self.api.catalog(info,out,1,0))
  info[42]=b'\xff';self.assertFalse(self.api.catalog(info,out,1,1))
 def test_empty_and_malformed_catalogue(self):
  out=Page();raw=b'{"api_version":1,"catalogue_schema":1,"total":0,"items":[],"next_cursor":null}'
  self.assertTrue(self.api.page(raw,len(raw),C.byref(out)));self.assertEqual(out.count,0)
  for bad in [raw[:-1],raw+b'x',b'[]',b'{}',b'x'*32769]:self.assertFalse(self.api.page(bad,len(bad),C.byref(out)))
if __name__=='__main__':unittest.main()
