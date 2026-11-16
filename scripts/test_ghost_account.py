"""Exercise production account/upload flow with local responses; never publish to the live service."""
import ctypes as C
import hashlib
import json
import unittest
import test_ghost_service as service

class Request(C.Structure):
    _fields_=[('method',C.c_char_p),('headers',C.c_char_p),('body',C.c_void_p),('bytes',C.c_uint)]
class Info(C.Structure):
    _fields_=[('magic',C.c_uint),('linked',C.c_uint),('pending',C.c_uint),('retry',C.c_uint),('code',C.c_char*12),('user',C.c_char*48)]
HTTP=C.CFUNCTYPE(C.c_int,C.c_char_p,C.POINTER(Request),C.c_void_p,C.c_uint,C.POINTER(C.c_uint),C.POINTER(C.c_uint))
PAIR={'access_token':'dga_'+'a'*43,'refresh_token':'dgr_'+'r'*43,'user':{'username':'runner'}}
CODE={'device_code':'dgd_'+'d'*43,'user_code':'ABCD-EFGH','expires_in':600,'interval':5}
UUID='12345678-1234-1234-1234-123456789abc'

class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib=service.build()
        cls.lib.test_account.argtypes=[C.c_uint,C.c_uint,C.c_void_p,C.c_uint,HTTP,C.POINTER(Info)]
    def setUp(self):
        self.lib.test_account_reset();self.calls=[];self.responses=[];self.fail=None;self.info=Info()
        @HTTP
        def http(path,request,out,cap,used,status):
            req=request.contents
            self.calls.append((path.decode(),req.method.decode(),req.headers.decode(),C.string_at(req.body,req.bytes)))
            if self.fail is not None:return self.fail
            if not self.responses:return -24
            code,body=self.responses.pop(0);raw=json.dumps(body).encode()
            if len(raw)>cap:return -24
            C.memmove(out,raw,len(raw));used[0]=len(raw);status[0]=code;return 0
        self.http=http
    def run_op(self,op,now=1000,ghost=b''):
        return self.lib.test_account(op,now,ghost,len(ghost),self.http,C.byref(self.info))
    def linked(self):
        self.responses=[(200,CODE),(200,PAIR)]
        self.assertEqual(self.run_op(1),0);self.assertEqual(self.run_op(2,1005),0)
        self.assertEqual(self.info.linked,1);self.calls.clear()
    def test_link_and_poll_interval(self):
        self.responses=[(200,CODE),(400,{'error':{'code':'slow_down'},'interval':15})]
        self.assertEqual(self.run_op(1),0);self.assertEqual(self.info.code,b'ABCD-EFGH')
        self.assertEqual(self.run_op(2,1004),0);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.run_op(2,1005),0);self.assertEqual(self.info.retry,15)
        self.assertEqual(self.run_op(2,1019),0);self.assertEqual(len(self.calls),2)
        self.assertEqual(self.run_op(2,1600),-34)
    def test_unlinked_upload_has_no_network_side_effect(self):
        self.assertEqual(self.run_op(4,ghost=b'ghost'),-33);self.assertEqual(self.calls,[])
    def test_check_link_after_success_keeps_the_account_without_polling_again(self):
        self.linked()
        for now in (1006,1600,86400):
            self.assertEqual(self.run_op(2,now),0)
            self.assertEqual(self.info.linked,1)
            self.assertEqual(self.info.pending,0)
            self.assertEqual(self.info.user,b'runner')
        self.assertEqual(self.calls,[])
    def test_publish_exact_bytes_and_hash(self):
        self.linked();ghost=b'canonical ghost\0\xff'*1000
        self.responses=[(200,PAIR),(201,{'result':'created','upload':{'upload_id':UUID}}),(200,{}),(201,{'result':'published'})]
        self.assertEqual(self.run_op(4,1010,ghost),0)
        self.assertEqual([c[1] for c in self.calls],['POST','POST','PUT','POST'])
        self.assertTrue(self.calls[-1][0].endswith('/'+UUID+'/publish'))
        meta=json.loads(self.calls[1][3]);digest=hashlib.sha256(ghost).hexdigest()
        self.assertEqual(meta['sha256'],digest);self.assertEqual(meta['byte_length'],len(ghost))
        self.assertIn('Idempotency-Key: '+digest,self.calls[1][2]);self.assertEqual(self.calls[2][3],ghost)
        self.assertTrue(all(c[0].startswith('/functions/v1/moonshine-api/v1/') for c in self.calls))
    def test_existing_publication_does_not_publish_again(self):
        self.linked();self.responses=[(200,PAIR),(200,{'result':'already_published'})]
        self.assertEqual(self.run_op(4,1010,b'ghost'),0);self.assertEqual(len(self.calls),2)
    def test_description_json_escaping_and_limit(self):
        self.linked()
        description=('"\\'*120).encode()
        self.lib.test_description(description,len(description))
        self.responses=[(200,PAIR),(201,{'upload':{'upload_id':UUID}}),(200,{}),(201,{})]
        ghost=b'unchanged canonical bytes'
        self.assertEqual(self.run_op(4,1010,ghost),0)
        self.assertEqual(json.loads(self.calls[1][3])['description'],description.decode())
        self.assertEqual(self.calls[2][3],ghost)
        self.assertEqual(json.loads(self.calls[1][3])['sha256'],hashlib.sha256(ghost).hexdigest())
    def test_kana_description_converts_to_utf8_json(self):
        self.linked()
        text='テスト かな "abc"ー！？'
        raw=text.encode('cp932')
        self.lib.test_description(raw,len(raw))
        self.responses=[(200,PAIR),(201,{'upload':{'upload_id':UUID}}),(200,{}),(201,{})]
        self.assertEqual(self.run_op(4,1010,b'ghost'),0)
        self.assertEqual(json.loads(self.calls[1][3])['description'],text)

    def test_invalid_description_does_not_rotate_credentials(self):
        self.linked()
        for description in (b'a'*241,b'bad\ntext',b'bad\x80'):
            self.lib.test_description(description,len(description))
            self.assertEqual(self.run_op(4,1010,b'ghost'),-35)
            self.assertEqual(self.calls,[])
            self.assertEqual(self.info.linked,1)
    def test_lost_refresh_is_never_replayed(self):
        self.linked();self.fail=-20
        self.assertEqual(self.run_op(4,1010,b'ghost'),-20);self.assertEqual(self.info.linked,0)
        self.assertEqual(self.run_op(4,1011,b'ghost'),-33);self.assertEqual(len(self.calls),1)
    def test_invalid_upload_id_cannot_redirect_token(self):
        self.linked();self.responses=[(200,PAIR),(201,{'upload':{'upload_id':'https://attacker.example/stolen'}})]
        self.assertEqual(self.run_op(4,1010,b'ghost'),-24);self.assertEqual(len(self.calls),2)
    def test_validation_failure_does_not_publish(self):
        self.linked();self.responses=[(200,PAIR),(201,{'upload':{'upload_id':UUID}}),(422,{'error':{'code':'invalid_ghost'}})]
        self.assertEqual(self.run_op(4,1010,b'ghost'),-35);self.assertEqual(len(self.calls),3)
    def test_unlink_revokes_and_clears_local_tokens(self):
        self.linked();self.responses=[(200,{'revoked':True})]
        self.assertEqual(self.run_op(3,1010),0);self.assertEqual(self.info.linked,0)
        self.assertTrue(self.calls[0][0].endswith('/device/revoke'))
    def test_malformed_token_never_links(self):
        self.responses=[(200,CODE),(200,{**PAIR,'access_token':'dga_'+'\r'*43})]
        self.assertEqual(self.run_op(1),0);self.assertEqual(self.run_op(2,1005),-24);self.assertEqual(self.info.linked,0)

if __name__=='__main__':unittest.main()
