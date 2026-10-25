"""Retire the actual ARM workers at every reachable transaction boundary."""
import ctypes as C
import struct
import unittest

import test_ghost_kernel_paging as ghost
import test_state_storage_kernel as state
import test_tas_storage_kernel as tas


def tracked_fixture(text):
    open_name = 'fixture_open' if 'static int fixture_open(' in text else 'f_open_char'
    for name in (open_name, 'f_opendir_char', 'f_close', 'f_closedir'):
        text = text.replace('static int ' + name + '(', 'static int tracked_' + name + '(')
    return text + r'''
static u32 liveFiles,liveDirs,closeCalls,dirCloseCalls,closeFault,dirCloseFault,trackingError;
static int f_close(FIL *file) {
 ++closeCalls;
 if(closeFault==closeCalls || closeFault==0xffffffffu)return FR_DISK_ERR;
 if(liveFiles)--liveFiles;else trackingError=1;
 return tracked_f_close(file);
}
static int f_closedir(DIR *dir) {
 ++dirCloseCalls;
 if(dirCloseFault==dirCloseCalls || dirCloseFault==0xffffffffu)return FR_DISK_ERR;
 if(liveDirs)--liveDirs;else trackingError=1;
 return tracked_f_closedir(dir);
}
static int f_opendir_char(DIR *dir,const char *path) {
 int result=tracked_f_opendir_char(dir,path);if(result==FR_OK)++liveDirs;return result;
}
''' + f'''
static int {open_name}(FIL *file,const char *path,u32 flags) {{
 int result=tracked_{open_name}(file,path,flags);if(result==FR_OK)++liveFiles;return result;
}}
'''


BRIDGE = r'''
__declspec(dllexport) u32 phase(void){return Phase;}
__declspec(dllexport) u32 handles(void){return liveFiles+liveDirs;}
__declspec(dllexport) u32 handleErrors(void){return trackingError;}
__declspec(dllexport) void closeFailure(u32 file,u32 dir){
 closeFault=file?closeCalls+file:0;dirCloseFault=dir?dirCloseCalls+dir:0;
}
__declspec(dllexport) u32 entries(void){return testCount;}
__declspec(dllexport) const char *entryPath(u32 i){return testFiles[i].live?testFiles[i].path:0;}
__declspec(dllexport) const void *entryBytes(u32 i){return testFiles[i].bytes;}
__declspec(dllexport) u32 entrySize(u32 i){return testFiles[i].size;}
__declspec(dllexport) void hardReset(void){
 Retiring=CloseFailed=false;Phase=0;
 HANDLE_RESET
 liveFiles=liveDirs=closeCalls=dirCloseCalls=closeFault=dirCloseFault=trackingError=0;reset();
}
__declspec(dllexport) u32 retire(void){return WORKER_Retire();}
__declspec(dllexport) u32 quiet(void){return WORKER_Quiescent();}
__declspec(dllexport) u32 failed(void){return WORKER_RetireFailed();}
__declspec(dllexport) void initAgain(void){WORKER_Init();}
__declspec(dllexport) void service(void){WORKER_Service();}
__declspec(dllexport) u32 pending(void){return WORKER_Pending();}
'''

GHOST_BRIDGE = BRIDGE.replace('WORKER_', 'SusamuneGhost').replace(
    'HANDLE_RESET', 'IoFileOpen=ImportDirOpen=false;') + r'''
__declspec(dllexport) void reservedPattern(void){
 memset((u8*)&testMailbox+64,0xC7,sizeof(testMailbox)-64);
}
__declspec(dllexport) u32 reservedIntact(void){
 for(u32 i=64;i<sizeof(testMailbox);++i)if(((u8*)&testMailbox)[i]!=0xC7)return 0;return 1;
}
__declspec(dllexport) const void *mailbox(void){return &testMailbox;}
'''

STATE_BRIDGE = BRIDGE.replace('WORKER_', 'SusamuneStateStorage').replace(
    'HANDLE_RESET', 'FileOpen=DirOpen=false;')


class RetirementChecks:
    fixture_transform = staticmethod(tracked_fixture)

    def setup_bridge(self):
        self.lib.entryPath.restype = C.c_char_p
        self.lib.entryBytes.restype = C.c_void_p
        self.lib.mailbox.restype = C.c_void_p
        self.lib.hardReset()
        self.buffers = []

    def disk(self):
        return {self.lib.entryPath(i).decode(): C.string_at(self.lib.entryBytes(i), self.lib.entrySize(i))
                for i in range(self.lib.entries()) if self.lib.entryPath(i)}

    def drain(self):
        for _ in range(20000):
            if self.lib.retire():
                break
            self.assertFalse(self.lib.failed(), 'Unexpected failed close')
        else:
            self.fail('Retirement did not reach quiescence')
        self.assertTrue(self.lib.quiet())
        self.assertEqual(self.lib.handles(), 0)
        self.assertEqual(self.lib.handleErrors(), 0)
        before = self.disk(), self.receipt()
        for _ in range(3):
            self.assertTrue(self.lib.retire())
            self.lib.service()
        self.assertFalse(self.lib.pending())
        self.assertEqual((self.disk(), self.receipt()), before)

    def advance_to(self, phase):
        for _ in range(20000):
            if self.lib.phase() == phase:
                return
            self.assertTrue(self.lib.pending(), 'Transaction finished before requested boundary')
            self.lib.service()
        self.fail('Transaction did not reach requested boundary')

    def all_boundaries(self, prepare, required):
        self.lib.hardReset(); self.buffers = []; prepare()
        phases = []
        while self.lib.pending():
            phases.append(self.lib.phase())
            self.lib.service()
            self.assertLess(len(phases), 20000)
        expected = self.disk(), self.receipt()
        self.assertEqual(self.status(), 0)
        self.assertTrue(required <= set(phases), (required, set(phases)))
        for stop in range(1, len(phases) + 1):
            with self.subTest(stop=stop, phase=phases[stop-1]):
                self.lib.hardReset(); self.buffers = []; prepare()
                for _ in range(stop):
                    self.lib.service()
                if self.lib.phase():
                    # Calling Init while active may not drop handles or requests.
                    before = self.lib.phase(), self.lib.handles(), self.receipt()
                    self.lib.initAgain()
                    self.assertEqual((self.lib.phase(), self.lib.handles(), self.receipt()), before)
                self.drain()
                self.assertEqual((self.disk(), self.receipt()), expected)
        return phases


class GhostRetirementTests(RetirementChecks, unittest.TestCase):
    bridge_source = GHOST_BRIDGE
    setUpClass = classmethod(ghost.GhostKernelPagingTests.setUpClass.__func__)
    add = ghost.GhostKernelPagingTests.add

    def setUp(self):
        self.lib = self.dll
        self.setup_bridge()

    def receipt(self):
        return C.string_at(self.lib.response(), 32)

    def status(self):
        return struct.unpack_from('<i', self.receipt(), 12)[0]

    def submit(self, command, slot=3, payload=b'', generation=0, profile=0):
        self.lib.submit(command, profile, slot, payload, len(payload), generation)

    def test_save_share_and_delete_drain_at_every_phase(self):
        raw = ghost.build_ghost()

        def save():
            self.submit(1, payload=raw)

        def share():
            self.add(ghost.PERSONAL+'g03a.sgh', ghost.envelope(raw, slot=3))
            self.submit(5, generation=1)

        def delete():
            self.add(ghost.PERSONAL+'g03a.sgh', ghost.envelope(raw, slot=3))
            self.submit(3, generation=1)

        # Numeric phase values are the real worker's operation enum.
        self.all_boundaries(save, {1, 4, 5, 6, 7, 8, 9, 10})
        self.all_boundaries(share, {11, 12, 13, 14, 15, 16, 17, 18, 19})
        self.all_boundaries(delete, {25, 26, 27})

    def test_imported_delete_and_open_directory_retire(self):
        raw = ghost.build_ghost()

        def delete():
            self.add(ghost.IMPORT+'chosen.smsghost', raw)
            self.submit(3, payload=b'chosen.smsghost'.ljust(96, b'\0'), profile=4,
                        generation=struct.unpack_from('>I', raw, 12)[0])

        def catalog():
            for i in range(3):
                self.add(ghost.IMPORT+f'run{i}.smsghost', raw)
            self.submit(6, slot=0, profile=4)

        self.all_boundaries(delete, {28})
        self.all_boundaries(catalog, {20, 21, 22, 23, 24})

    def test_unaccepted_doorbell_is_dropped_and_reserved_lines_survive_init(self):
        self.lib.reservedPattern()
        self.submit(1, payload=ghost.build_ghost())
        before = self.disk(), self.receipt()
        self.drain()
        self.assertEqual((self.disk(), self.receipt()), before)
        self.submit(1, payload=ghost.build_ghost())
        self.lib.service()
        self.assertEqual((self.disk(), self.receipt()), before)
        self.lib.initAgain()
        self.assertTrue(self.lib.reservedIntact())
        self.submit(1, payload=ghost.build_ghost())
        self.assertGreaterEqual(self.lib.run(10000), 0)
        self.assertEqual(self.status(), 0)

    def test_failed_file_and_directory_closes_block_retirement(self):
        for directory in (False, True):
            with self.subTest(directory=directory):
                self.lib.hardReset()
                if directory:
                    self.submit(6, slot=0, profile=4)
                else:
                    self.submit(1, payload=ghost.build_ghost())
                self.lib.service()
                self.lib.closeFailure(not directory, directory)
                for _ in range(10000):
                    if self.lib.failed(): break
                    self.assertFalse(self.lib.retire())
                self.assertTrue(self.lib.failed())
                self.assertGreater(self.lib.handles(), 0)
                before = self.receipt()
                self.lib.initAgain()
                for _ in range(3):
                    self.assertFalse(self.lib.retire())
                    self.assertFalse(self.lib.quiet())
                self.assertEqual(self.receipt(), before)

    def test_missing_files_and_failed_writes_do_not_fake_a_close_failure(self):
        self.submit(2, generation=1)
        self.assertGreaterEqual(self.lib.run(10000), 0)
        self.assertEqual(self.status(), -9)
        self.assertFalse(self.lib.failed())
        self.drain()
        self.lib.hardReset()
        self.submit(1, payload=ghost.build_ghost())
        self.lib.service()
        self.lib.writeFailure(0, 0)
        self.drain()
        self.assertNotEqual(self.status(), 0)
        self.assertFalse(self.lib.failed())

    def test_stack_local_envelope_close_blocks_retirement(self):
        self.add(ghost.PERSONAL+'g03a.sgh', ghost.envelope(ghost.build_ghost(), slot=3))
        self.submit(2, generation=1)
        self.advance_to(4)
        self.lib.closeFailure(1, 0)
        self.assertFalse(self.lib.retire())
        self.assertTrue(self.lib.failed())
        self.assertFalse(self.lib.quiet())
        self.assertGreater(self.lib.handles(), 0)


class StateRetirementTests(RetirementChecks, unittest.TestCase):
    bridge_source = STATE_BRIDGE
    setUpClass = classmethod(state.StateStorageKernelTests.setUpClass.__func__)
    buffer = state.StateStorageKernelTests.buffer
    export = state.StateStorageKernelTests.export
    finish = state.StateStorageKernelTests.finish
    file = state.StateStorageKernelTests.file
    command = state.StateStorageKernelTests.command

    def setUp(self):
        self.setup_bridge()

    def receipt(self):
        return C.string_at(self.lib.mailbox()+32, 64)

    def status(self):
        return C.c_uint.from_address(self.lib.mailbox()+44).value

    def test_export_rename_delete_and_catalog_drain_at_every_phase(self):
        def export():
            data, metadata = b'retired export' * 3000, b'metadata'
            self.lib.prepare(self.buffer(data), len(data), 32, self.buffer(metadata), len(metadata))
            self.command(state.EXPORT, offset=32, size=len(data))

        def mutate(command):
            archive, _, _ = self.export()
            self.lib.requestName(b'Retired rename')
            self.command(command, 1, crc=state.Header.from_buffer_copy(archive).headerCrc)

        def catalog():
            self.export()
            self.command(state.CATALOG)

        self.all_boundaries(export, set(range(1, 10)))
        self.all_boundaries(lambda: mutate(state.RENAME), {2, 3, 12})
        self.all_boundaries(lambda: mutate(state.DELETE), {2, 3, 12})
        self.all_boundaries(catalog, {10, 11})

    def test_changed_cancel_doorbell_cannot_abort_accepted_export_during_retirement(self):
        data, metadata = b'commit me' * 4000, b'metadata'
        self.lib.prepare(self.buffer(data), len(data), 32, self.buffer(metadata), len(metadata))
        self.command(state.EXPORT, offset=32, size=len(data))
        self.advance_to(6)
        seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.command(state.CANCEL)
        self.drain()
        self.assertEqual(self.status(), 0)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+40).value, seq)
        self.assertEqual(self.file()[96+len(metadata):], data)

    def test_unaccepted_requests_are_dropped_without_fabricating_receipt(self):
        self.command(state.CATALOG)
        before = self.disk(), self.receipt()
        self.drain()
        self.assertEqual((self.disk(), self.receipt()), before)
        self.command(state.CATALOG)
        self.lib.service()
        self.assertEqual((self.disk(), self.receipt()), before)
        self.lib.initAgain()
        self.command(state.CATALOG)
        self.assertEqual(self.finish(), state.OK)

    def test_failed_close_blocks_retirement_and_init_even_if_old_open_flags_clear(self):
        self.export()
        self.command(state.CATALOG)
        self.lib.service()
        self.lib.closeFailure(0, 1)
        while not self.lib.failed():
            self.assertFalse(self.lib.retire())
        self.assertEqual(self.lib.phase(), 0)
        self.assertGreater(self.lib.handles(), 0)
        receipt = self.receipt()
        self.lib.initAgain()
        self.assertFalse(self.lib.quiet())
        self.assertFalse(self.lib.retire())
        self.assertEqual(self.receipt(), receipt)

    def test_stack_local_name_close_is_included_in_the_failure_latch(self):
        archive, _, _ = self.export()
        crc = state.Header.from_buffer_copy(archive).headerCrc
        self.lib.requestName(b'Name')
        self.command(state.RENAME, 1, crc=crc)
        self.advance_to(12)
        self.lib.closeFailure(1, 0)
        self.assertFalse(self.lib.retire())
        self.assertTrue(self.lib.failed())
        self.assertFalse(self.lib.quiet())
        self.assertEqual(self.status(), state.IO)

    def test_unopened_missing_file_and_write_errors_still_retire(self):
        archive, _, _ = self.export()
        header = state.Header.from_buffer_copy(archive)
        self.command(state.IMPORT, 2, size=header.packedSize, crc=header.headerCrc)
        self.lib.service()
        self.drain()
        self.assertEqual(self.status(), 5)
        self.assertFalse(self.lib.failed())
        self.lib.hardReset()
        data, meta = b'write fault' * 2000, b'meta'
        self.lib.prepare(self.buffer(data), len(data), 32, self.buffer(meta), len(meta))
        self.command(state.EXPORT, offset=32, size=len(data))
        self.lib.service()
        self.lib.failures(0, 0, 0)
        self.drain()
        self.assertNotEqual(self.status(), state.OK)
        self.assertFalse(self.lib.failed())


class TasRetirementTests(RetirementChecks, unittest.TestCase):
    bridge_source = STATE_BRIDGE
    setUpClass = classmethod(state.StateStorageKernelTests.setUpClass.__func__)
    buffer = tas.TasStorageKernelTests.buffer
    finish = tas.TasStorageKernelTests.finish
    context = tas.TasStorageKernelTests.context
    command = tas.TasStorageKernelTests.command
    result_id = tas.TasStorageKernelTests.result_id
    returned = tas.TasStorageKernelTests.returned
    path = tas.TasStorageKernelTests.path
    file = tas.TasStorageKernelTests.file
    begin = tas.TasStorageKernelTests.begin
    export_component = tas.TasStorageKernelTests.export_component
    export_tape = tas.TasStorageKernelTests.export_tape
    unpublished = tas.TasStorageKernelTests.unpublished
    published = tas.TasStorageKernelTests.published
    receipt = StateRetirementTests.receipt
    status = StateRetirementTests.status

    def setUp(self):
        self.setup_bridge()

    def test_project_commit_rename_and_delete_drain_at_every_phase(self):
        def commit():
            project = self.unpublished()
            self.command(tas.COMMIT, project.id, project=project)

        def mutate(command):
            project = self.published()
            self.command(command, project.id, project.checksum, name=b'Retired project')

        self.all_boundaries(commit, {32, 36, 37, 38, 39, 40, 41, 42, 43, 45})
        self.all_boundaries(lambda: mutate(tas.RENAME), {32, 40, 41, 42, 43, 45})
        self.all_boundaries(lambda: mutate(tas.DELETE), {32, 40, 41, 42, 43, 44})


if __name__ == '__main__':
    unittest.main()
