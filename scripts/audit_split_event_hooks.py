"""Verify checkpoint entry hooks and semantic field accesses in retail DOLs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from audit_practice_hooks import Dol

ROOT = Path(__file__).resolve().parents[1]
METHODS = {
    'kStreamingMovie': 'fireStreamingMovie__12TMarDirectorFUc',
    'kMapObjAppear': 'appear__14TMapObjGeneralFv',
    'kRedSwitchMessage': 'receiveMessage__14TRedCoinSwitchFP9THitActorUl',
    'kSandCastle': 'explode__11TSandCastleFv',
    'kMirrorMessage': 'receiveMessage__11TLeanMirrorFP9THitActorUl',
    'kHanachanDamage': 'execDamage__13TBossHanachanFv',
    'kTinKoopaHit': 'hitParts__9TTinKoopaFv',
    'kEnemyMarioVtable': '__vt__11TEnemyMario',
    'kShineVtable': '__vt__6TShine',
}


def verify(region, path):
    source = (ROOT / 'src/split_events.cpp').read_text()
    rows = {name: (int(address, 16), int(size, 16)) for size, address, name in
            re.findall(r'^  \w{8} (\w{6}) (\w{8})  \d (\S+) ',
                       (ROOT / f'maps/{region}.map').read_text(), re.M)}
    dol = Dol(path)
    checks = []

    def words(name):
        address, size = rows[name]
        return dol.words(address, size // 4)

    def sequence(name, pattern, description):
        body = words(name)
        assert any(body[i:i+len(pattern)] == pattern for i in range(len(body))), description
        checks.append(description)

    def calls(name,target):
        address,_=rows[name]
        destination=rows[target][0]
        for i,word in enumerate(words(name)):
            if word & 0xFC000003 != 0x48000001:continue
            delta=word&0x03FFFFFC
            if delta&0x02000000:delta-=0x04000000
            if address+4*i+delta==destination:return True
        return False

    region_index = ('jp', 'us', 'pal').index(region)
    for constant, symbol in METHODS.items():
        match = re.search(r'const u32 ' + constant +
                          r'\s*=\s*SUSAMUNE_MEM1_ADDR\(([^)]+)\)', source)
        assert match, constant
        addresses = [int(x.strip().rstrip('u'),16) for x in match[1].split(',')]
        assert rows[symbol][0] == addresses[region_index], (region, constant, symbol)
        if not symbol.startswith('__vt__'):
            assert words(symbol)[0] == 0x7C0802A6, (region, constant, 'relocatable mflr')
        checks.append(f'{constant} resolves to {symbol} at {rows[symbol][0]:08X}')

    sequence('setDummyConnectActor__8TBaseNPCFPCQ26JDrama6TActor',
             (0x908301D4,0x80A301D4), 'Accepted dummy NPC connection uses actor field 0x1D4')
    sequence('execDamage__13TBossHanachanFv',
             (0x3803FFFF,0x981F013C), 'Accepted Wiggler damage decrements health byte 0x13C')
    sequence('hitParts__9TTinKoopaFv',
             (0x807D01C8,0x3803FFFF,0x901D01C8),
             'Accepted Mecha-Bowser hit decrements remaining hits at 0x1C8')
    sequence('receiveMessage__11TLeanMirrorFP9THitActorUl',
             (0x807E019C,0x3803FFFF,0x901E019C),
             'Mirror enemy-removal path decrements remaining actors at 0x19C')
    sequence('receiveMessage__11TLeanMirrorFP9THitActorUl',
             (0x28050008,), 'Mirror completion path handles retail message 8')
    sequence('checkEnforceJump__6TMarioFv', (0x38800884,),
             'Floor-enforced launch requests Mario status 0x884')
    sequence('getActiveJumpPower__12TBGCheckDataCFv', (0xA8630002,),
             'Forced launch strength reads the signed floor value at offset 2')
    sequence('fireStreamingMovie__12TMarDirectorFUc', (0x60000100,0xB003004C),
             'Accepted movie queue sets director flag 0x100 at 0x4C')
    sequence('setNextStage__12TMarDirectorFUsPQ26JDrama6TActor',
             (0x7C834670,0x3803FFFF,0x98010038,0x98810039),
             'Encoded stage word decodes area as high byte minus one and episode as low byte')
    movie_body = words('fireStreamingMovie__12TMarDirectorFUc')
    tables = [((hi & 0xffff) << 16) + ((lo & 0xffff) ^ 0x8000) - 0x8000
              for hi, lo in zip(movie_body, movie_body[1:])
              if hi & 0xffff0000 == 0x3c800000 and lo & 0xffff0000 == 0x38840000]
    assert len(tables) == 1, (region, 'movie dispatch table')
    for movie, target in ((7, 0x0e06), (8, 0x0e07)):
        case = dol.words(tables[0] + movie * 4, 1)[0]
        body = dol.words(case, 10)
        assert (0x38800000 | target) in body, (region, movie, 'wrong destination')
        assert any(body[i:i+2] == (0x60000100, 0xb003004c)
                   for i in range(len(body))), (region, movie, 'missing accepted flag')
        checks.append(f'Pinna movie {movie} accepts flag 0x100 and selects stage word {target:04X}')
    for method in ('appearSimple__6TShineFi','appearWithTime__6TShineFiiii'):
        assert calls(method,'appear__14TMapObjGeneralFv'),(region,method,'missing live spawn call')
        assert not calls(method,'appear__5TItemFv'),(region,method,'unexpected out-of-line TItem call')
        checks.append(f'{method} calls hooked TMapObjGeneral::appear with TItem::appear inlined')
    sequence('receiveMessage__14TRedCoinSwitchFP9THitActorUl', (0x28050001,),
             'Red switch receives accepted ground-pound message 1')
    sequence('receiveMessage__14TRedCoinSwitchFP9THitActorUl', (0xB01F00FC,),
             'Accepted red switch press writes the state at 0xFC')
    return {'region':region, 'dol_sha256':hashlib.sha256(dol.data).hexdigest(),
            'checks':checks,'passed':len(checks)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dol-dir',type=Path,required=True,
                        help='Directory containing jp_main.dol, us_main.dol, pal_main.dol')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    results=[verify(region,args.dol_dir/f'{region}_main.dol') for region in ('jp','us','pal')]
    report={'passed':sum(row['passed'] for row in results),'regions':results}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'regions':{r['region']:r['passed'] for r in results}}))
