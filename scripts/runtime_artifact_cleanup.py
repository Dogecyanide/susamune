"""Discard verified temporary disc copies after an owned emulator has stopped."""
from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parents[1]
LOG_LIMIT=64*1024*1024

def cleanup(folder, evidence, *, stopped, keep_iso=False):
    folder=Path(folder).resolve()
    if not stopped or not folder.is_relative_to((ROOT/'build').resolve()): return []
    removed=[]
    image=folder/'input.iso'
    expected=evidence.get('source_iso_sha256')
    source=Path(evidence.get('source_iso','')).resolve()
    if (not keep_iso and expected and image.is_file() and not image.is_symlink()
            and image.resolve()==source and image.parent==folder and (folder/'fixture.json').is_file()):
        digest=hashlib.sha256()
        with image.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        if digest.hexdigest()==expected:
            size=image.stat().st_size;image.unlink();removed.append({'path':str(image),'bytes':size})
    profile=Path(evidence.get('profile','')).resolve()
    if profile.is_relative_to(folder):
        log=profile/'Logs/dolphin.log'
        if log.is_file() and not log.is_symlink() and log.resolve().is_relative_to(folder) and log.stat().st_size>LOG_LIMIT:
            size=log.stat().st_size
            with log.open('rb') as stream:
                head=stream.read(1024*1024);stream.seek(-(LOG_LIMIT-len(head)),2);tail=stream.read()
            log.write_bytes(head+b'\n[Middle omitted by owned test log limit]\n'+tail)
            removed.append({'path':str(log),'bytes':size-log.stat().st_size,'action':'bounded log'})
    (folder/'artifact-cleanup.json').write_text(json.dumps({'stopped':True,'removed':removed,'evidence_kept':True},indent=2)+'\n')
    return removed
