import unittest
from timewarp_cold_cluster import native_storage_pointer,NATIVE_STORAGE_CALLBACKS
class Tests(unittest.TestCase):
 def setUp(self):
  self.source={'owners':['dolphin_ghost_account.cpp'],'symbols':['dolphinStorageCallbacks__0'],'kind':'rodata','attribution':'exclusive'}
  self.symbols=[{'name':'dolphinStorageCallbacks__0','address':0x80001000,'size':84}]
  self.r={'site':0x80001000,'type':1,'addend':0,'symbol':NATIVE_STORAGE_CALLBACKS[0]}
 def test_exact_service_abi(self):
  for i,name in enumerate(NATIVE_STORAGE_CALLBACKS):
   self.assertTrue(native_storage_pointer(self.source,{**self.r,'site':0x80001000+4*i,'symbol':name},self.symbols,'emu'))
 def test_wrong_owner_shape_target_or_offset_rejected(self):
  for key,value in [('owners',['else.cpp']),('kind','code'),('attribution','shared'),('symbols',['other'])]:
   self.assertFalse(native_storage_pointer({**self.source,key:value},self.r,self.symbols,'emu'))
  for key,value in [('site',0x80001001),('site',0x80001038),('symbol',NATIVE_STORAGE_CALLBACKS[1]),('addend',4),('type',10)]:
   self.assertFalse(native_storage_pointer(self.source,{**self.r,key:value},self.symbols,'emu'))
  self.assertFalse(native_storage_pointer(self.source,self.r,self.symbols,'console'))
  self.assertFalse(native_storage_pointer(self.source,self.r,[{**self.symbols[0],'size':60}],'emu'))
if __name__=='__main__':unittest.main()
