"""Exercise the shipped asset validator, lookup and bounded texture cache."""
import ctypes as C
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
import zlib

from gen_japanese_ui import build, catalogue, expand, TOKENS, JA_TOKENS, MAX_SIZE

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class JapaneseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset, cls.report = build()
        cls.work = tempfile.TemporaryDirectory(prefix='moonshine-ja-')
        work = Path(cls.work.name)
        source = (ROOT/'src/japanese_ui.cpp').read_text()
        harness = '''
#include "susamune/japanese_ui.h"
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
static const u8 *sAsset; static u16 sCacheIds[64]; static u8 sCache[64][128];
static unsigned int sNext, barriers, flushes, invalidations;
static bool ready() {return sAsset != nullptr;}
static void GXDrawDone() {++barriers;}
static void DCFlushRange(void *, unsigned int n) {if(n==128)++flushes;}
static void GXInvalidateTexAll() {++invalidations;}
extern "C" void *memset(void *p,int v,__SIZE_TYPE__ n) {volatile u8 *b=(volatile u8*)p;while(n--)*b++=v;return p;}
'''
        for signature in ('unsigned int word(', 'unsigned int nextCode(', 'int glyph(',
                          'int units(', 'u8 *image(', 'const char *text('):
            harness += function(source, signature)+'\n'
        harness += '''
extern "C" {
__declspec(dllexport) int valid(const u8 *p,unsigned int n) {return SusamuneJpUiValid(p,n);}
__declspec(dllexport) void reset(const u8 *p,unsigned int n) {
 sAsset=SusamuneJpUiValid(p,n)?p:nullptr;sNext=barriers=flushes=invalidations=0;
 for(unsigned int i=0;i<64;++i)sCacheIds[i]=0;
}
__declspec(dllexport) const char *lookup(const char *p) {return text(p);}
__declspec(dllexport) int measure(const char *p) {return units(p);}
__declspec(dllexport) const u8 *getImage(int id) {return image(id);}
__declspec(dllexport) unsigned int counts(unsigned int which) {return which==0?barriers:which==1?flushes:invalidations;}
}
'''
        (work/'test.cpp').write_text(harness)
        command = [str(ROOT/'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                   '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
                   '-I'+str(ROOT/'include'), str(work/'test.cpp'), '-o', str(work/'test.dll')]
        subprocess.run(command, check=True, capture_output=True)
        cls.lib = C.CDLL(str(work/'test.dll'))
        cls.lib.valid.argtypes = [C.c_void_p,C.c_uint]
        cls.lib.reset.argtypes = [C.c_void_p,C.c_uint]
        cls.lib.lookup.argtypes = [C.c_char_p]; cls.lib.lookup.restype = C.c_char_p
        cls.lib.measure.argtypes = [C.c_char_p]; cls.lib.measure.restype = C.c_int
        cls.lib.getImage.argtypes = [C.c_int];cls.lib.getImage.restype = C.c_void_p
        cls.lib.counts.argtypes = [C.c_uint];cls.lib.counts.restype = C.c_uint
        cls.buffer = C.create_string_buffer(bytes(cls.asset))

    @classmethod
    def tearDownClass(cls):
        import _ctypes
        _ctypes.FreeLibrary(cls.lib._handle)
        cls.work.cleanup()

    def setUp(self):
        self.lib.reset(self.buffer,len(self.asset))

    def test_asset_bounded_and_reproducible(self):
        self.assertEqual(self.asset,build()[0])
        self.assertLessEqual(len(self.asset),MAX_SIZE)
        self.assertEqual(len(self.asset)%32,0)
        self.assertTrue(self.lib.valid(self.buffer,len(self.asset)))

    def test_entire_catalogue_roundtrips_through_production_lookup(self):
        for line in (ROOT/'data/japanese_ui.tsv').read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.startswith('#'):continue
            en,ja=line.split('\t')
            self.assertEqual(self.lib.lookup(expand(en,TOKENS)),expand(ja,JA_TOKENS),en)

    def test_unknown_text_and_missing_asset_preserve_english(self):
        self.assertEqual(self.lib.lookup(b'User custom text 987'),b'User custom text 987')
        broken=C.create_string_buffer(b'\0'*64)
        self.lib.reset(broken,64)
        self.assertEqual(self.lib.lookup(b'Practice'),b'Practice')
        self.assertEqual(self.lib.measure('日本語'.encode('cp932')),-1)

    def test_all_asset_sections_are_covered_by_crc(self):
        for offset in (0,4,8,12,16,63,64,19000,45000,len(self.asset)-1):
            bad=bytearray(self.asset);bad[offset]^=1
            self.assertFalse(self.lib.valid(C.create_string_buffer(bytes(bad)),len(bad)),offset)
        for size in (0,32,63,len(self.asset)-1,len(self.asset)+1,MAX_SIZE+1):
            self.assertFalse(self.lib.valid(self.buffer,size),size)

    def test_rechecks_structural_bounds_even_with_repaired_crc(self):
        for offset,value in ((20,0xFFFFFFFF),(24,0),(28,65536),(32,0),(36,0xFFFFFFFF),
                             (40,0),(44,24),(48,128),(52,1),(56,1),(60,1)):
            bad=bytearray(self.asset);struct.pack_into('>I',bad,offset,value)
            struct.pack_into('>I',bad,12,0);struct.pack_into('>I',bad,12,zlib.crc32(bad))
            self.assertFalse(self.lib.valid(C.create_string_buffer(bytes(bad)),len(bad)),offset)

    def test_texture_cache_matches_every_packed_glyph_with_one_barrier_per_wrap(self):
        header=struct.unpack_from('>16I',self.asset)
        for i in range(header[9]):
            raw=self.asset[header[10]+i*64:header[10]+(i+1)*64]
            expected=bytes(v for b in raw for v in (((b>>6)*5<<4)|((b>>4&3)*5),((b>>2&3)*5<<4)|((b&3)*5)))
            self.assertEqual(C.string_at(self.lib.getImage(i),128),expected)
            self.lib.getImage(i)
        self.assertEqual(self.lib.counts(0),(header[9]-1)//64)
        self.assertEqual(self.lib.counts(1),header[9])
        self.assertEqual(self.lib.counts(2),header[9])

    def test_measurement_uses_font_widths_and_rejects_unknown_or_truncated_codes(self):
        self.assertGreater(self.lib.measure('日本語'.encode('cp932')),0)
        self.assertEqual(self.lib.measure(b'ASCII remains the retail font'),-1)
        self.assertEqual(self.lib.measure(b'\x82'),-1)
        self.assertEqual(self.lib.measure(b'\xff\xff'),-1)

    def test_approved_wording_is_presentation_only(self):
        expected={'Force plaza events':'ドルピックタウンイベントの強制再生',
                  'PB popup':'記録更新時に通知','Expert Spider Bouncer':'アメンボ跳びの達人',
                  'Coconut King':'ヤシの実王','Plungelo Plucker':'チュウハナ抜き'}
        for en,ja in expected.items():self.assertEqual(self.lib.lookup(en.encode()),ja.encode('cp932'))

    def test_current_navigation_has_translated_labels(self):
        source = (ROOT/'src/menu.cpp').read_text()
        category = source[source.index('const char kCategoryTitles'):source.index('enum CategoryTitleOffset')]
        labels = ''.join(re.findall(r'"([^"]+)"', category)).split(r'\0')
        pages = source[source.index('const SettingPage kGameplayPages'):source.index('const char *settingHelp')]
        labels += re.findall(r'\{"([^"\\]+)",', pages)
        labels += ['Quick','Practice','Runs','Records','Ghosts','Display','System',
                   'ILs','Stage Loader','PB Safety','Layout editor','Button binds',
                   'FOXTROT guide','Frame advance','Free camera','Input replay (experimental)',
                   'Timers','Controller inputs','Metadata','Native HUD colours','Custom text',
                   'Practice feedback','Menu and notifications','Save latest ghost',
                   'Achievements  >','Statistics overview  >','Worlds  >']
        for label in labels:
            with self.subTest(label=label):
                translated=self.lib.lookup(label.encode())
                self.assertNotEqual(translated,label.encode())
                if any(byte >= 128 for byte in translated):
                    self.assertGreater(self.lib.measure(translated),0)

    def test_jp_disc_asset_is_raw_and_outside_both_dol_sections(self):
        from gen_iso_bps import build_operations
        layout=json.loads((ROOT/'data/iso_layout_jp.json').read_text())
        layout['japanese_ui']={'offset':0x004AA8C0,'size':MAX_SIZE}
        manifest={'base_addr':layout['base_addr'],'writes':[],
                  'segments':[{'offset':0,'memory_size':0x57000,'code':'00'*32},
                              {'offset':0x80000,'memory_size':0x3F000,'code':'00'*32}]}
        operations=build_operations(layout,manifest)
        literals=[o for o in operations if o['kind']=='literal' and o['target_offset']==0x004AA8C0]
        self.assertEqual(len(literals),1)
        self.assertEqual(literals[0]['value'],self.asset)
        self.assertLessEqual(layout['dol']['iso_offset']+layout['dol']['size']+0x97000,0x004AA8C0)
        for region in ('us','pal'):
            other=json.loads((ROOT/f'data/iso_layout_{region}.json').read_text())
            manifest['base_addr']=other['base_addr']
            self.assertFalse(any(o['kind']=='literal' and o['value']==self.asset
                                 for o in build_operations(other,manifest)))
        for field,value in (('offset',0x004AA8C4),('size',MAX_SIZE+32)):
            changed=json.loads(json.dumps(layout));changed['japanese_ui'][field]=value
            with self.assertRaises(ValueError):build_operations(changed,manifest)

    def test_disc_extent_only_replaces_a_file_already_relocated_in_full(self):
        layout=json.loads((ROOT/'data/iso_layout_jp.json').read_text())
        start,end=0x004AA8C0,0x004AA8C0+MAX_SIZE
        self.assertTrue(any(f['source_offset']<=start and
                            end<=f['source_offset']+f['size'] for f in layout['relocated_files']))
        self.assertEqual(layout['mod_region_size'],0xA0000)


if __name__=='__main__':unittest.main()
