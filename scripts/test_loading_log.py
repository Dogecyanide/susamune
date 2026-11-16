import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('loading_log',Path(__file__).resolve().parents[1]/'tools/loading_trace/inspect.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def marker(phase,tick,hz=40500000,lost=0):return f'10 load p={phase} t={tick} hz={hz} s=0603 a=1540 lost={lost} iso=2/4096/3/2'
class LoadingLogTests(unittest.TestCase):
 def test_intervals_and_canceled_attempts_are_separate(self):
  r=module.inspect('\n'.join([marker(1,0),marker(3,40500000),marker(7,81000000),marker(1,0),marker(8,4050000)]))
  self.assertEqual(len(r['loads']),2);self.assertEqual([x['ms'] for x in r['loads'][0]['intervals']],[1000,1000]);self.assertEqual(r['loads'][1]['intervals'][0]['ms'],100)
 def test_tick_wrap_and_dropped_markers_remain_visible(self):
  r=module.inspect(marker(1,0xfffffff0,1000)+'\n'+marker(7,0x10,1000,2));self.assertEqual(r['loads'][0]['intervals'][0]['ms'],32);self.assertEqual(r['loads'][0]['dropped'],2)
 def test_clock_change_is_not_reported_as_a_duration(self):
  r=module.inspect(marker(1,0)+'\n'+marker(7,10000,60750000));self.assertIsNone(r['loads'][0]['intervals'][0]['ms'])
 def test_compact_iso_counters_do_not_invent_a_maximum(self):
  text=marker(7,1000).rsplit('/',1)[0];r=module.inspect(text)
  self.assertIsNone(r['loads'][0]['events'][0]['iso_max_ms'])
 def test_io_times_are_retained_separately(self):
  r=module.inspect('22 io ghost id=7 p=1 n=256 ms=94 r=0');self.assertEqual(r['io'][0]['ms'],94);self.assertEqual(r['loads'],[])
if __name__=='__main__':unittest.main()
