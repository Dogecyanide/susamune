"""Package source-free standard-Dolphin builds and their offline setup/file tools."""
from __future__ import annotations
import argparse,json,zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from package_timewarp_dolphin import verify_application
from timewarp_emulator_export import export,digest,verify_build,ROOT
from build_dolphin_https import checked_image

FILES={"Apply-ISO.cmd":"tools/dolphin_online/Apply-ISO.cmd", "apply_patch.py":"tools/dolphin_online/apply_patch.py",
       "Setup-Dolphin.cmd":"tools/dolphin_online/Setup-Dolphin.cmd", "setup_dolphin_data.py":"scripts/setup_dolphin_data.py",
       "manage_data.py":"tools/dolphin_online/manage_data.py", "validate_ghost.py":"scripts/validate_ghost.py",
       "licenses/Moonshine.txt":"LICENSE", "licenses/miniz.txt":"vendor/miniz/LICENSE", "licenses/lz4.txt":"vendor/lz4/LICENSE",
       "licenses/BearSSL.txt":"launcher/third_party/bearssl/LICENSE.txt", "licenses/lwIP.txt":"vendor/lwip/COPYING",
       "licenses/Droid.txt":"data/fonts/Droid-LICENSE.txt", "licenses/NotoSansCJK.txt":"launcher/loader/data/OFL-NotoSansCJK.txt"}

README="""Moonshine {release} - standard Dolphin ({language})

No companion or custom Dolphin is required. Every online player, including Wii
players, must use {release} (online protocol 8).

1. Install 64-bit Python 3.10 or newer. Extract this ZIP to a permanent folder.
2. Drag your clean Sunshine ISO onto Apply-ISO.cmd. A separate Moonshine ISO
   is created. Linux/macOS: python3 apply_patch.py "/path/to/clean.iso"
3. In Dolphin select File > Open User Folder, then close Dolphin completely.
   Windows: drag that user folder onto Setup-Dolphin.cmd.
   Linux/macOS:
   python3 setup_dolphin_data.py --user "/path/to/Dolphin user" \
     --data "/path/to/Moonshine data" --dolphin-closed
4. Boot the new ISO. Y+Start opens Moonshine by default.

Setup configures Sunshine's native BBA HLE adapter, 32 MiB physical MEM1 and
Slot B as a dedicated GCI Folder. It preserves Slot A and backs up changed
settings. Existing GCI-folder saves are copied without replacing conflicts.
If your previous Slot B is a RAW memory card, first switch Slot B to GCI Folder
in Dolphin and boot once so Dolphin migrates it, then close and run setup.
Keep the original card as a backup. Do not format or replace Slot A.

Moonshine data holds separate JPN/USA/EUR folders. The .gci files contain your
ghosts, saved states, TAS projects, settings and account link. Keep that working
folder private. Link each game region separately on Delfino Ghosts if needed.

To make a shareable ghost/state/TAS backup, close Dolphin and run:
  python manage_data.py export "Moonshine data" "My Moonshine files"
This makes separate ghosts/states/tas folders and excludes account links,
security seeds and settings. To restore into a working data folder:
  python manage_data.py import "Moonshine data" "My Moonshine files"
Conflicting existing files are preserved and reported; they are never replaced.
To import a website ghost (jp, us or pal is your running game's region):
  python manage_data.py import-ghost "Moonshine data" jp "run.smsghost"
To share a personal ghost as an ordinary website-compatible file:
  python manage_data.py export-ghost "path/to/ghost.gci" "run.smsghost"
The in-game Z / Export help button points to this offline export tool.
No file tool needs to remain running while playing.

Storage limits: standard Dolphin emulates memory-card capacity and speed.
Each regional Slot B has about 16 MiB / 127 files shared by Moonshine data.
Large saved states and TAS projects may take minutes to write. The measured
7.1 MB state saved in 229 seconds and imported in 56 seconds; a new TAS with
that Beginning took 285 seconds. Ordinary in-memory savestates are separate.
Archive unused files outside the working GCI folder to make room, with Dolphin
closed. Moving a TAS requires all its matching project/component files.

Verified in private standard-Dolphin runs: native website browse/download/load,
account linking and authenticated ghost upload, persistent state save/import/restore after restart, and saved
TAS reopen/replay with matching fingerprints. See verification/package.json
for the precise build/acceptance scope. Four-player and Linux/macOS live tests
still need user acceptance. These packages contain no game ISO, personal data,
account credentials, custom launcher music or background.
"""

def checked_acceptance(build, region, runtime, review):
    fixture=json.loads((runtime/'fixture.json').read_text())
    current=verify_build(build,region)[4]
    keys=('manifest_sha256','container_sha256','elf_sha256','pinned_link_receipt_sha256')
    if all(fixture['production_build'][k]==current[k] for k in keys): return fixture
    if not review: raise ValueError(region+' runtime differs from build')
    proof=json.loads(review.read_text())
    if proof.get('passed') is not True or proof['before'][region]!=fixture['production_build'] or proof['after'][region]!=current:
        raise ValueError('Presentation review does not match acceptance/build')
    old=json.loads((runtime/'boot-verification.json').read_text())['source_hashes']
    changed={name for name,sha in old.items() if digest((ROOT/name).read_bytes())!=sha}
    if changed!={'src/menu.cpp','src/ghost_storage.cpp'}: raise ValueError('Change exceeds reviewed export guidance')
    for name in changed:
        row=proof['sources'][name]
        if row['before']!=old[name] or row['after']!=digest((ROOT/name).read_bytes()):
            raise ValueError('Reviewed source changed: '+name)
    live=ROOT/proof['runtime'];live_fixture=json.loads((live/'fixture.json').read_text())
    if live_fixture['production_build']!=verify_build(build,'pal')[4]: raise ValueError('Export-help runtime differs')
    test_path=live/'export-help-verification.json'
    if digest(test_path.read_bytes())!=proof['runtime_receipt_sha256'] or json.loads(test_path.read_text()).get('passed') is not True:
        raise ValueError('Export-help runtime verification missing')
    return fixture

def package(build, output, release, language, isos, runtime, upload_runtime, presentation_review=None):
    if not release.replace('-','').isalnum(): raise ValueError('Invalid release label')
    if output.exists(): raise FileExistsError(output)
    _,native=checked_image(build/'dolphin-native')
    proofs={}
    for name in ('account-verification.json','archive-restart-verification.json','tas-recording-verification.json','moved-library-verification.json'):
        path=runtime/name;row=json.loads(path.read_text())
        if row.get('passed') is not True: raise ValueError('Acceptance incomplete: '+name)
        proofs[name]=digest(path.read_bytes())
    fixture=checked_acceptance(build,'jp',runtime,presentation_review)
    live=json.loads((runtime/'live.json').read_text())
    if not live['runtime'].get('native_service_image_verified'): raise ValueError('Native runtime not verified')
    if fixture['production_bootstrap']['native_https_sha256']!=native['sha256']:
        raise ValueError('Runtime native image differs from the current build')
    upload_path=upload_runtime/'approved-upload-verification.json'
    if json.loads(upload_path.read_text()).get('passed') is not True: raise ValueError('Native authenticated upload is incomplete')
    pal_fixture=checked_acceptance(build,'pal',upload_runtime,presentation_review)
    if pal_fixture['production_bootstrap']['native_https_sha256']!=native['sha256']: raise ValueError('PAL native image differs')
    proofs['approved-upload-verification.json']=digest(upload_path.read_bytes())
    output.mkdir(parents=True)
    def prepare(item):
        region,iso=item;patch=output/'patches'/('moonshine_'+region+'.bps')
        export(iso,build,region,patch,language)
        return region,verify_application(iso,build,patch,region,output/('verify-'+region+'.iso'))
    with ThreadPoolExecutor(max_workers=min(3,len(isos))) as workers: applied=dict(workers.map(prepare,isos.items()))
    label='Japanese' if language=='ja' else 'English';prefix='Moonshine_'+release+'_Dolphin_'+label
    files={name:(ROOT/path).read_bytes() for name,path in FILES.items()}
    files['README.txt']=README.format(release=release,language=label).encode()
    for region in isos:
        for suffix in ('.bps','.bps.json'):
            name='moonshine_'+region+suffix
            files[('patches/' if suffix=='.bps' else 'verification/')+name]=(output/'patches'/name).read_bytes()
    proof={'passed':True,'release':release,'language':label,'regions':list(isos),'native_sha256':native['sha256'],
           'scope':'Patch application and unchanged retail content verified for every included region. Native runtime acceptance is JP; authenticated upload has its own PAL receipt. This does not establish four-player or Linux/macOS acceptance.',
           'runtime_receipt_hashes':proofs,'patch_application':applied}
    if presentation_review:
        proof['presentation_revision']=json.loads(presentation_review.read_text())
        proof['scope']+=' Final Dolphin export guidance was checked separately; storage/upload acceptance precedes that two-source UI-only revision.'
    files['verification/package.json']=(json.dumps(proof,indent=2)+'\n').encode()
    archive=output/('Moonshine-'+release+'-Dolphin-'+label+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(files.items()):z.writestr(prefix+'/'+name,data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or set(z.namelist())!={prefix+'/'+n for n in files} or any(z.read(prefix+'/'+n)!=v for n,v in files.items()): raise ValueError('Package verification failed')
    proof.update(zip_sha256=digest(archive.read_bytes()),zip_bytes=archive.stat().st_size)
    archive.with_suffix('.zip.sha256').write_text(proof['zip_sha256']+'  '+archive.name+'\n')
    (output/'receipt.json').write_text(json.dumps(proof,indent=2)+'\n');print(archive,proof['zip_bytes'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--release',required=True);p.add_argument('--language',choices=('en','ja'),default='en');p.add_argument('--runtime',type=Path,required=True);p.add_argument('--upload-runtime',type=Path,required=True);p.add_argument('--presentation-review',type=Path)
    for region in ('jp','us','pal'):p.add_argument('--'+region,type=Path)
    a=p.parse_args();isos={r:getattr(a,r).resolve() for r in ('jp','us','pal') if getattr(a,r)}
    if not isos or (a.language=='ja' and list(isos)!=['jp']):p.error('Provide JP only for Japanese, or the desired regional ISOs for English')
    package(a.build.resolve(),a.output.resolve(),a.release,a.language,isos,a.runtime.resolve(),a.upload_runtime.resolve(),a.presentation_review.resolve() if a.presentation_review else None)
if __name__=='__main__':main()
