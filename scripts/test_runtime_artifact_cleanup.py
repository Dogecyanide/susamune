import hashlib,json,tempfile,unittest
from pathlib import Path
from runtime_artifact_cleanup import cleanup,ROOT
class CleanupTests(unittest.TestCase):
 def test_only_verified_stopped_owned_disc_is_removed(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='cleanup-proof-') as d:
   folder=Path(d);iso=folder/'input.iso';iso.write_bytes(b'test disc');(folder/'fixture.json').write_text('{}')
   user=folder/'Moonshine data';user.mkdir();(user/'saved.gci').write_bytes(b'keep')
   (folder/'proof.json').write_text('{}')
   evidence={'source_iso':str(iso),'source_iso_sha256':hashlib.sha256(iso.read_bytes()).hexdigest()}
   self.assertEqual(cleanup(folder,evidence,stopped=False),[]);self.assertTrue(iso.exists())
   cleanup(folder,evidence,stopped=True,keep_iso=True);self.assertTrue(iso.exists())
   self.assertEqual(cleanup(folder,dict(evidence,source_iso_sha256='bad'),stopped=True),[])
   result=cleanup(folder,evidence,stopped=True);self.assertEqual(result[0]['bytes'],9);self.assertFalse(iso.exists())
   self.assertEqual((user/'saved.gci').read_bytes(),b'keep');self.assertTrue((folder/'proof.json').exists())
 def test_external_source_and_missing_receipt_are_kept(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='cleanup-proof-') as d:
   folder=Path(d);iso=folder/'input.iso';iso.write_bytes(b'test')
   evidence={'source_iso':str(iso),'source_iso_sha256':hashlib.sha256(b'test').hexdigest()}
   cleanup(folder,evidence,stopped=True);self.assertTrue(iso.exists())
   (folder/'fixture.json').write_text('{}');evidence['source_iso']=str(folder.parent/'original.iso')
   cleanup(folder,evidence,stopped=True);self.assertTrue(iso.exists())
if __name__=='__main__':unittest.main()
