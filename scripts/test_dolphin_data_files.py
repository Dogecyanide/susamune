"""Portable copies must exclude credentials and preserve conflicting existing saves."""
import sys,json,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools/dolphin_online"))
import manage_data as m

class Files(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.data=self.root/"data";self.out=self.root/"export"
 def file(self,name,payload=b"payload",kind="JPN"):
  p=self.data/kind/(name+".gci");m.private_write(p,m.wrap("jp",name.encode(),payload));return p
 def test_export_separates_types_and_excludes_account_seed_and_settings(self):
  for n in ("ms_p0_0000000000000001","ms_state_00000001","ms_t00000001_project","ms_t00000001_s00000002","ms_delfino_link","ms_tls_seed","ms_settings"):self.file(n)
  self.assertEqual(m.export_files(self.data,self.out),4)
  names=[x.relative_to(self.out).as_posix() for x in self.out.rglob("*.gci")]
  self.assertTrue(any("/ghosts/" in x for x in names));self.assertTrue(any("/states/" in x for x in names));self.assertTrue(any("/tas/" in x for x in names))
  self.assertFalse(any("link" in x or "seed" in x or "settings" in x for x in names))
 def test_copy_and_repeat_import_preserves_original(self):
  original=self.file("ms_state_00000001");m.export_files(self.data,self.out);target=self.root/"target"
  self.assertEqual(m.import_files(target,self.out),1);self.assertEqual(m.import_files(target,self.out),0)
  self.assertEqual(next((target/"JPN").glob("*.gci")).read_bytes(),original.read_bytes())
 def test_conflict_preflights_all_files(self):
  self.file("ms_state_00000001");self.file("ms_state_00000002");m.export_files(self.data,self.out)
  target=self.root/"target";bad=target/"JPN"/"existing.gci";m.private_write(bad,m.wrap("jp",b"ms_state_00000002",b"other"))
  before=bad.read_bytes()
  with self.assertRaises(ValueError):m.import_files(target,self.out)
  self.assertEqual(list((target/"JPN").glob("*.gci")),[bad]);self.assertEqual(bad.read_bytes(),before)
 def test_modified_bundle_rejected_before_import(self):
  self.file("ms_state_00000001");m.export_files(self.data,self.out);p=next(self.out.rglob("*.gci"));p.write_bytes(p.read_bytes()[:-1]+b"x")
  with self.assertRaises(ValueError):m.import_files(self.root/"target",self.out)
 def test_traversal_rejected(self):
  self.file("ms_state_00000001");m.export_files(self.data,self.out);p=self.out/"moonshine-files.json";v=json.loads(p.read_text());v["files"][0]["path"]="../JPN/state.gci";p.write_text(json.dumps(v))
  with self.assertRaises(ValueError):m.import_files(self.root/"target",self.out)
 def test_bad_ghost_and_private_gci_cannot_be_exported(self):
  private=self.file("ms_delfino_link")
  with self.assertRaises(ValueError):m.export_ghost(private,self.root/"bad.smsghost")
  bad=self.root/"bad.smsghost";bad.write_bytes(b"bad")
  with self.assertRaises(ValueError):m.import_ghost(self.data,"jp",bad)
 def test_capacity_preflight(self):
  folder=self.root/"full";folder.mkdir()
  raw=m.wrap("jp",b"ms_state_00000001",bytes(2043*m.BLOCK));m.private_write(folder/"full.gci",raw)
  with self.assertRaises(ValueError):m.check_room(folder,[m.wrap("jp",b"ms_state_00000002",b"x")])

if __name__=="__main__":unittest.main()
