"""Check standalone versus parent-required capture summaries against shared headers."""
from pathlib import Path
import importlib.util,re,struct,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
from ghost_trace_branch_admission_fixture import branch_graph,capture,fnv,tag_header
from test_ghost_trace_reader import capture as ordinary_capture,record
spec=importlib.util.spec_from_file_location('branch_inspector',ROOT/'tools/ghost_trace/inspect_trace.py')
inspector=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspector)

class InspectorBranchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='msgt-inspect-branch-');self.addCleanup(self.temp.cleanup)
  self.folder=Path(self.temp.name);self.path=self.folder/'capture.msgt'
 def inspect(self,data):self.path.write_bytes(data);return inspector.inspect(self.path)
 def change(self,data,offset,value):
  out=bytearray(data);struct.pack_into('>I',out,offset,value);struct.pack_into('>I',out,60,fnv(out[:60]));return bytes(out)
 def test_constants_match_the_shared_wire_header(self):
  header=(ROOT/'include/susamune/ghost_trace_checkpoint.h').read_text()
  for name,value in [('MS_TRACE_BRANCH_HEADER_TAG',inspector.BRANCH_HEADER_TAG),('MS_TRACE_BRANCH_HEADER_FLAGS',inspector.BRANCH_HEADER_FLAGS)]:
   self.assertEqual(int(re.search(r'#define '+name+r' (0x[0-9a-fA-F]+)u',header).group(1),16),value)
  caps=(ROOT/'include/susamune/ghost_trace.h').read_text()
  self.assertEqual(int(re.search(r'MS_TRACE_HAS_CONTINUATION\s*=\s*(\d+)',caps).group(1)),inspector.CONTINUATION_CAPABILITY)
 def test_legacy_zero_headers_remain_standalone(self):
  for version in (1,2,3):
   with self.subTest(version=version):
    summary=self.inspect(ordinary_capture([record(body=b'future optional')],version=version))
    self.assertTrue(summary['complete']);self.assertTrue(summary['standalone_replay']);self.assertFalse(summary['requires_parent'])
    self.assertEqual([summary[k] for k in ('parent_nonce','parent_run','parent_chunk')],[0,0,0])
    self.assertFalse(summary['full_world_replay_proven'])
 def test_complete_raw_child_reports_exact_parent_but_is_not_standalone(self):
  child,parent,edge=branch_graph();summary=self.inspect(child)
  self.assertTrue(summary['complete']);self.assertTrue(summary['requires_parent']);self.assertFalse(summary['standalone_replay'])
  self.assertEqual([summary[k] for k in ('parent_nonce','parent_run','parent_chunk')],[0x87654321,6,1])
  self.assertTrue(summary['tas']);self.assertFalse(summary['full_world_replay_proven'])
  (self.folder/'parent.msgt').write_bytes(parent);(self.folder/'parent.msgb').write_bytes(edge)
  self.assertFalse(inspector.inspect(self.path)['standalone_replay'])
 def test_unknown_partial_self_and_unclassified_parent_headers_fail(self):
  child,_,_=branch_graph()
  for offset,value in ((44,0),(44,0x12345678),(48,0),(52,0),(56,0),(36,0),(36,0x21),(40,0),(40,0x12345678),(28,0x1fffff),(52,7)):
   with self.subTest(offset=offset,value=value):
    with self.assertRaisesRegex(ValueError,'parent header'):self.inspect(self.change(child,offset,value))
  ordinary=ordinary_capture([record()])
  for offset in (48,52,56):
   with self.assertRaisesRegex(ValueError,'parent header'):self.inspect(self.change(ordinary,offset,1))
 def test_parent_fields_remain_covered_by_the_header_checksum(self):
  child,_,_=branch_graph();bad=bytearray(child);bad[59]^=1
  with self.assertRaisesRegex(ValueError,'MSTR header'):self.inspect(bytes(bad))
 def test_flattened_zero_dependency_header_is_standalone(self):
  child,parent,_=branch_graph();payload=parent[96:-32]+child[96:-32]
  flattened=tag_header(capture(0x12345678,77,payload),0,0,0,tag=0)
  summary=self.inspect(flattened)
  self.assertTrue(summary['complete']);self.assertFalse(summary['requires_parent']);self.assertTrue(summary['standalone_replay']);self.assertTrue(summary['tas'])
  self.assertEqual([summary[k] for k in ('parent_nonce','parent_run','parent_chunk')],[0,0,0])
 def test_failed_producer_completion_is_not_standalone(self):
  summary=self.inspect(ordinary_capture([record()],error=3))
  self.assertFalse(summary['complete']);self.assertFalse(summary['requires_parent']);self.assertFalse(summary['standalone_replay'])
 def test_unpack_preserves_required_parent_and_refuses_overwrite(self):
  child,_,_=branch_graph();self.path.write_bytes(child);out=self.folder/'unpacked.msgt'
  summary=inspector.unpack_to_v2(self.path,out)
  self.assertEqual(summary['version'],2);self.assertTrue(summary['complete']);self.assertTrue(summary['requires_parent']);self.assertFalse(summary['standalone_replay'])
  self.assertEqual(out.read_bytes()[44:60],child[44:60])
  with self.assertRaises(FileExistsError):inspector.unpack_to_v2(self.path,out)

if __name__=='__main__':unittest.main()
