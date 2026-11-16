"""Generate BearSSL public trust anchors from the vendored Google root PEMs."""
from pathlib import Path
import hashlib
import ssl

ROOT = Path(__file__).resolve().parents[1]

def children(data):
    result = []
    pos = 0
    while pos < len(data):
        start = pos
        tag, length = data[pos:pos+2]
        pos += 2
        if length & 128:
            n = length & 127
            assert 0 < n <= 4
            length = int.from_bytes(data[pos:pos+n], 'big')
            pos += n
        end = pos + length
        assert end <= len(data)
        result.append((tag, data[pos:end], data[start:end]))
        pos = end
    return result

def generate():
    lines = ['/* Generated from official pki.goog root certificates; public keys only. */']
    anchors = []
    def array(name, data):
        lines.append('static const unsigned char '+name+'[] = {')
        for i in range(0,len(data),16):
            lines.append('    '+','.join('0x%02x'%v for v in data[i:i+16])+',')
        lines.append('};')
    for n in range(1,5):
        der=ssl.PEM_cert_to_DER_cert((ROOT/f'launcher/third_party/roots/gtsr{n}.pem').read_text())
        lines.append('/* GTS Root R%d SHA256: %s */'%(n,hashlib.sha256(der).hexdigest()))
        cert=children(children(der)[0][1]); tbs=children(cert[0][1])
        assert tbs[0][0] == 0xa0
        dn=tbs[5][2]; spki=children(tbs[6][1]); key=spki[1][1]
        assert key[0]==0
        prefix='ghost_root_%d'%n
        array(prefix+'_dn',dn)
        if n <= 2:
            rsa=children(children(key[1:])[0][1])
            modulus=rsa[0][1].lstrip(b'\0'); exponent=rsa[1][1].lstrip(b'\0')
            array(prefix+'_n',modulus); array(prefix+'_e',exponent)
            pkey='{BR_KEYTYPE_RSA, {.rsa = {(unsigned char*)%s_n, sizeof(%s_n), (unsigned char*)%s_e, sizeof(%s_e)}}}'%((prefix,)*4)
        else:
            array(prefix+'_q',key[1:])
            pkey='{BR_KEYTYPE_EC, {.ec = {BR_EC_secp384r1, (unsigned char*)%s_q, sizeof(%s_q)}}}'%(prefix,prefix)
        anchors.append('    {{(unsigned char*)%s_dn, sizeof(%s_dn)}, BR_X509_TA_CA, %s},'%(prefix,prefix,pkey))
    lines+=['static const br_x509_trust_anchor ghost_roots[] = {',*anchors,'};','']
    (ROOT/'launcher/kernel/GhostServiceRoots.inc').write_text('\n'.join(lines))

if __name__=='__main__': generate()
