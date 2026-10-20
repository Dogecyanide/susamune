"""One actual-PPC replay replacement using the captured maximum staging deficit."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from timewarp_pool_ppc import ROOT, PoolPilot, build, sha
from timewarp_store_ppc import produced


def captured(receipt, name):
    row=next(row for group in receipt['sets'] for row in group['slots'] if row['name']==name)
    raw=Path(row['raw_path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row['raw_sha256']
    offset,size=row['raw_offset'],row['free_bytes']
    raw=raw[:offset]+bytes(size)+raw[offset+size:]
    assert hashlib.sha256(raw).hexdigest()==row['filtered_raw_sha256']
    packed=Path(row['packed_path']).read_bytes()
    assert hashlib.sha256(packed).hexdigest()==row['packed_sha256']
    return {'raw':raw,'packed':packed,'input':row}


def stats(pilot):
    names=('cached_bytes','spilled_blocks','replayed_raw_bytes','moved_bytes','scratch_bytes','encode_calls')
    return dict(zip(names,struct.unpack('>6I',pilot.read(pilot.CONTROL+96,24))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dolphin',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();folder=args.output.resolve()
    if folder.exists() or not folder.is_relative_to((ROOT/'build').resolve()):
        parser.error('Use a fresh private build directory')
    folder.mkdir(parents=True)
    gap=ROOT/'build/timewarp-heap-gap-measure/receipt.json'
    previous=ROOT/'build/timewarp-capacity-canonical-summary-1/receipt.json'
    inputs=json.loads(gap.read_text())
    deficit=next(row for row in json.loads(previous.read_text())['replacement_projection']
                 if row['baseline']=='worst' and row['candidate']=='bianco5/slot3' and row['slot']==0)
    states=[captured(inputs,name) for name in inputs['known_capacity_failure']['names']]
    candidate=captured(inputs,'bianco5/slot3')
    files=['src/state_codec.cpp','src/state_crc.cpp','src/state_store.cpp','src/state_import.cpp','src/state_quick_replay.cpp',
           'src/qft_timer.cpp','scripts/timewarp/ppc_pool_bench.cpp','scripts/timewarp/ppc_store_bench.cpp',
           'scripts/timewarp_replay_ppc.py','scripts/timewarp_pool_ppc.py','scripts/timewarp_store_ppc.py']
    files += [str(path.relative_to(ROOT)).replace('\\','/') for path in (ROOT/'include/susamune').glob('state_*.h*')]
    before={name:sha(ROOT/name) for name in files}
    report={'passed':False,'scope':'One actual-PPC prepared-codec/replay-planner replacement in an owned game-free Dolphin process. Immutable captured input and synthetic admission; not game/Wii lifecycle or latency proof.',
            'source_sha256':before,'inputs':{str(gap):sha(gap),str(previous):sha(previous)},
            'previous_staging_failure':deficit,'baseline':[state['input'] for state in states],
            'candidate':candidate['input'],'target_slot':0,'saves':[]}
    pilot=None
    try:
        source=folder/'replay_bench.cpp'
        source.write_text('#define TIMEWARP_QUICK_REPLAY 1\n#include "'+
                          (ROOT/'scripts/timewarp/ppc_store_bench.cpp').as_posix()+'"\n')
        dol,report['build']=build(folder,source)
        pilot=PoolPilot(args.dolphin,folder,dol,report,1);report['runtime']=pilot.evidence
        with pilot:
            pilot.command(1)
            for slot,state in enumerate(states):
                row={'produce':produced(pilot,slot,state),'commit':pilot.command(4,slot)}
                report['saves'].append(row)
                print(json.dumps({'seed_slot':slot,'occupied':row['commit']['occupied']}),flush=True)
            assert report['saves'][-1]['commit']['occupied']==deficit['occupied_bytes']
            pilot.write(pilot.INPUT,candidate['raw'])
            prepared=pilot.command(11,0,len(candidate['raw']))
            assert prepared['packed']==len(candidate['packed'])
            assert prepared['raw']==len(candidate['raw'])
            assert prepared['adler']==zlib.adler32(candidate['raw'])
            assert prepared['crc']==zlib.crc32(candidate['packed'])
            report['prepare']={'command':prepared,'stats':stats(pilot)}
            report['old_roots_exact_before_commit']=[pilot.encoded(i,state) for i,state in enumerate(states)]
            assert pilot.read(pilot.INPUT,len(candidate['raw']))==candidate['raw']
            report['source_unchanged_through_preparation']=True
            committed=pilot.command(12,0)
            report['commit']={'command':committed,'stats':stats(pilot)}
            assert committed['generations'][1:]==report['saves'][-1]['commit']['generations'][1:]
            assert report['commit']['stats']['encode_calls']-report['prepare']['stats']['encode_calls']==report['prepare']['stats']['spilled_blocks']
            final=[candidate,*states[1:]]
            report['final_roots']=[{'encoded':pilot.encoded(i,state),'protected_decode':pilot.decode(i,state,True)}
                                   for i,state in enumerate(final)]
            report['all_boundary_canaries_intact']=True
            report['final_free_bytes']=sum((0xff0000,0x200000,0xc2000,0x13e000))-committed['occupied']
            print(json.dumps({'replacement_passed':True,'prepare':report['prepare']['stats'],
                              'final_occupied':committed['occupied'],'final_free':report['final_free_bytes']}),flush=True)
        assert before=={name:sha(ROOT/name) for name in files}
        report['passed']=True
    finally:
        if pilot and pilot.process and pilot.process.poll() is None:pilot.__exit__()
        report['owned_process_stopped']=bool(pilot and pilot.process and pilot.process.poll() is not None)
        (folder/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'receipt':str(folder/'receipt.json')}),flush=True)


if __name__=='__main__':main()
