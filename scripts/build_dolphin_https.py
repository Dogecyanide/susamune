"""Build the self-contained native Dolphin HTTPS image in its unused aperture gap."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import struct
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[1]
def digest(data):return hashlib.sha256(data).hexdigest()
def source_inputs():
    port=ROOT/'native/dolphin_https'
    bear=ROOT/'launcher/third_party/bearssl'
    sources=sorted((bear/'src').rglob('*.c'))+[port/'engine.c',port/'init.c',port/'libc.c',port/'tcp.cpp',port/'catalog.cpp',port/'web.c',port/'account.cpp',port/'library.cpp',port/'storage_host.cpp',port/'archive.cpp',port/'http.cpp',port/'entropy.cpp',ROOT/'launcher/kernel/GhostServiceAccount.c',ROOT/'launcher/kernel/GhostServiceJson.c',ROOT/'launcher/kernel/GhostServiceHttp.c']
    sources += sorted((ROOT/'src').glob('dolphin_lwip_*.cpp'))
    dependencies=list(port.glob('*.inc'))+sorted((bear/'inc').glob('*.h'))+sorted((bear/'src').glob('*.h'))+sorted((port/'port').glob('*.h'))
    dependencies += [ROOT/'launcher/kernel'/n for n in ('GhostServiceAccount.h','GhostServiceTls.c','GhostServiceTls.h','GhostServiceHttp.h','GhostServiceJson.h','GhostCanonical.inc','GhostServiceRoots.inc')]
    dependencies += sorted((ROOT/'vendor/lwip/src').rglob('*.c')) + [ROOT/'include/Dolphin/types.h']
    dependencies += sorted((ROOT/'vendor/lwip/src').rglob('*.h')) + sorted((ROOT/'include/susamune/lwip_port').rglob('*.h'))
    dependencies += [ROOT/'include/susamune'/n for n in ('ghost_catalog_validation.inc','ghost_camera.h','ghost_teaching.h','ghost_fludd.h','practice_input.h','ghost_context.h','ghost_simulation_settings.h','dolphin_web_api.h','dolphin_storage_api.hxx','dolphin_files.hxx','dolphin_http.hxx','dolphin_ghost_library.hxx','dolphin_entropy.hxx','dolphin_archive.hxx','dolphin_http_api.hxx','live_transport.h','ghost_run_flags.h','ghost_state_reference.h','ghost_trace_checkpoint.h','ghost_trace.h','state_storage.h','tas_storage.h','state_pool_memory.h','state_slot_pool.h','ghost_format.h','ghost_storage.h','dolphin_tcp_api.h','dolphin_tcp.hxx','dolphin_https.h','ghost_service.h','kana_text.h','japanese_ui.h','mem2_map.h')]
    return sources, dependencies

def build(out):
    out.mkdir(parents=True,exist_ok=True)
    port=ROOT/'native/dolphin_https'
    bear=ROOT/'launcher/third_party/bearssl'
    sources,dependencies=source_inputs()
    flags=['--target=powerpc-gecko-ibm-kuribo-eabi','-x','c','-std=c99','-Os','-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-fno-unwind-tables','-nostdinc',
           '-DBR_USE_UNIX_TIME=0','-DBR_USE_URANDOM=0','-DBR_USE_WIN32_RAND=0','-DBR_RDRAND=0','-DBR_POWER8=0',
           '-DIS_EMULATOR=1','-DTIMEWARP_LIVE_RACING=1','-DMOONSHINE_LWIP_NATIVE_CORE=1',
           '-I'+str(port/'port'),'-I'+str(ROOT/'include/susamune/lwip_port'),'-I'+str(ROOT/'vendor/lwip/src/include'),'-I'+str(bear/'inc'),'-I'+str(bear/'src'),'-I'+str(ROOT/'include')]
    shared=digest(b''.join(p.read_bytes() for p in dependencies)+json.dumps(flags).encode())
    def compile_one(source):
        name=source.relative_to(ROOT).as_posix().replace('/','_');obj=out/(name+'.o');stamp=obj.with_suffix('.hash')
        value=digest(source.read_bytes()+shared.encode())
        if not obj.exists() or not stamp.exists() or stamp.read_text()!=value:
            options=flags if source.name not in ('tcp.cpp','catalog.cpp','account.cpp','library.cpp','storage_host.cpp','archive.cpp','http.cpp','entropy.cpp') else [f for f in flags if f not in ('-x','c','-std=c99')]+['-x','c++','-std=c++14','-fno-exceptions','-fno-rtti']
            r=subprocess.run([str(ROOT/'toolchain/clang++.exe'),*options,'-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if r.returncode:raise ValueError(source.name+': '+r.stderr[-5000:])
            stamp.write_text(value)
        return obj
    with ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(compile_one,sources))
    script=out/'image.ld'
    script.write_text("ENTRY(moonshine_https_api)\nSECTIONS { . = 0x71B20000; .api : { KEEP(*(.api)) } . = 0x71B20080; .tcpapi : { KEEP(*(.tcpapi)) } . = 0x71B200C0; .webapi : { KEEP(*(.webapi)) } . = 0x71B20100; .storageapi : { KEEP(*(.storageapi)) } . = 0x71B20140; .archiveapi : { KEEP(*(.archiveapi)) } . = 0x71B20180; .httpapi : { KEEP(*(.httpapi)) } .text : { *(.text*) } .rodata : { *(.rodata*) *(.sdata2*) } .data : { *(.data*) *(.sdata*) } .bss 0x71BF3000 (NOLOAD) : { __native_bss_start = .; *(.bss*) *(.sbss*) *(COMMON) __native_bss_end = .; } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n")
    elf=out/'image.elf'
    response=out/'objects.rsp';response.write_text('\n'.join(chr(34)+p.as_posix()+chr(34) for p in objects))
    r=subprocess.run([str(ROOT/'toolchain/powerpc-eabi-ld.exe'),'--gc-sections','-T',str(script),'-Map='+str(out/'image.map'),'-o',str(elf),'@'+str(response)],capture_output=True,text=True)
    if r.returncode:raise ValueError(r.stderr[-6000:])
    with elf.open('rb') as stream:
        e=ELFFile(stream);all_sections=[s for s in e.iter_sections() if s['sh_flags']&2 and s['sh_size']]
        sections=[s for s in all_sections if s['sh_type']!='SHT_NOBITS']
        bss=[s for s in all_sections if s['sh_type']=='SHT_NOBITS']
        if any(s['sh_addr']<0x71BF3000 or s['sh_addr']+s['sh_size']>0x71C00000 for s in bss):raise ValueError('Native TCP globals exceed their existing gap')
        lo=min(s['sh_addr'] for s in sections);hi=max(s['sh_addr']+s['sh_size'] for s in sections)
        if lo!=0x71B20000 or hi>0x71BE0000:raise ValueError('HTTPS image exceeds its fixed gap')
        if struct.unpack('>3I',e.get_section_by_name('.tcpapi').data()[:12])!=(0x4d545031,1,56):raise ValueError('Invalid native TCP ABI')
        data=bytearray((hi-lo+31)&~31)
        for s in sections:data[s['sh_addr']-lo:s['sh_addr']-lo+s['sh_size']]=s.data()
        magic,version,abi,work=struct.unpack_from('>4I',data)
        if (magic,version,abi)!=(0x4d485431,2,40) or work>0x8000:raise ValueError('Invalid native HTTPS ABI')
        symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF'}
    binary=out/'image.bin';binary.write_bytes(data)
    receipt={'base':lo,'bytes':len(data),'work_bytes':work,'api_bytes':abi,'sha256':digest(data),'elf_sha256':digest(elf.read_bytes()),
             'compiler_sha256':digest((ROOT/'toolchain/clang++.exe').read_bytes()),'sources':{p.relative_to(ROOT).as_posix():digest(p.read_bytes()) for p in sources+dependencies},
             'flags':flags,'imports':[],'bss_bytes':sum(s['sh_size'] for s in bss),'symbols':symbols,'builder_sha256':digest(Path(__file__).read_bytes())}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('base','bytes','work_bytes','sha256')},indent=2),flush=True)
    return receipt
def checked_image(folder):
    receipt=json.loads((folder/'receipt.json').read_text());data=(folder/'image.bin').read_bytes()
    if receipt['builder_sha256']!=digest(Path(__file__).read_bytes()):raise ValueError('HTTPS builder changed')
    for name,value in receipt['sources'].items():
        if digest((ROOT/name).read_bytes())!=value:raise ValueError('HTTPS source changed: '+name)
    if receipt['imports'] or len(data)!=receipt['bytes'] or len(data)%32 or digest(data)!=receipt['sha256']:
        raise ValueError('HTTPS image differs from its receipt')
    if receipt['base']!=0x71B20000 or not 40<=len(data)<=0xC0000:raise ValueError('HTTPS image outside its gap')
    magic,version,abi,work,*calls=struct.unpack_from('>10I',data)
    if (magic,version,abi)!=(0x4d485431,2,40) or not 0<work<=0x8000 or any(a&3 or not receipt['base']+40<=a<receipt['base']+len(data) for a in calls):
        raise ValueError('Invalid HTTPS API')
    if struct.unpack_from('>3I',data,0x80)!=(0x4d545031,1,56):raise ValueError('Invalid native TCP API')
    for address in struct.unpack_from('>11I',data,0x8c):
        if address&3 or not receipt['base']+0xb8<=address<receipt['base']+len(data):raise ValueError('TCP API target outside image')
    if struct.unpack_from('>3I',data,0xc0)!=(0x4d574231,3,36):raise ValueError('Invalid native web API')
    for address in struct.unpack_from('>6I',data,0xcc):
        if address&3 or not receipt['base']+0xe4<=address<receipt['base']+len(data):raise ValueError('Web API target outside image')
    if struct.unpack_from('>3I',data,0x100)!=(0x4d535431,2,36):raise ValueError('Invalid native storage API')
    for address in struct.unpack_from('>6I',data,0x10c):
        if address&3 or not receipt['base']+0x124<=address<receipt['base']+len(data):raise ValueError('Storage API target outside image')
    if struct.unpack_from('>3I',data,0x140)!=(0x4d415231,1,20):raise ValueError('Invalid native archive API')
    if struct.unpack_from('>3I',data,0x180)!=(0x4d485431,1,48):raise ValueError('Invalid native HTTP API')
    for address in struct.unpack_from('>2I',data,0x14c):
        if address&3 or not receipt['base']+0x154<=address<receipt['base']+len(data):raise ValueError('Archive API target outside image')
    for address in struct.unpack_from('>9I',data,0x18c):
        if address&3 or not receipt['base']+0x1b0<=address<receipt['base']+len(data):raise ValueError('HTTP API target outside image')
    return bytes(data),receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output',type=Path)
    mode.add_argument('--list-inputs',action='store_true')
    a=p.parse_args()
    if a.list_inputs:
        sources,dependencies=source_inputs()
        print(';'.join(path.resolve().as_posix() for path in sorted(set(sources+dependencies))))
    else:build(a.output.resolve())
