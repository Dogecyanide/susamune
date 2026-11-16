"""V10 context admission through the production ARM and independent host readers."""
import ctypes
import struct
import unittest
import zlib

import validate_ghost as ghost
import test_ghost_camera_storage as camera_fixture
from test_ghost_camera_storage import camera_file
from test_ghost_initial_rng import rng_file, seal_table
from test_ghost_format import build_ghost
from test_ghost_kernel_paging import IMPORT
from test_ghost_storage import rechecksum_ghost
from test_ghost_teaching import teaching_file


def settings():
    out = bytearray(64)
    struct.pack_into('>f', out, 48, 60.0)
    return out


def event(qf=100, index=0, serial=1, move=0, director=0, seed=0,
          segment=0, kind=1, flags=0, yaw=0, mode=0, snapshot=None):
    return struct.pack('>6IHBBhH', qf, index, serial, move, director, seed,
                       segment, kind, flags, yaw, mode) + bytes(settings() if snapshot is None else snapshot)


def context_file(records=None, flags=0, base=None):
    base = bytearray(rng_file() if base is None else base)
    start = struct.unpack_from('>I',base,56)[0]
    teaching = 0x900 + struct.unpack_from('>I',base,68)[0]*16
    inputs,splits = struct.unpack_from('>II',base,teaching+8)
    for i in range(inputs):
        at=teaching+32+i*24
        qf=struct.unpack_from('>I',base,at)[0];relative=qf-start
        struct.pack_into('>HH',base,at,relative&65535,0)
        base[at+15]=((relative>>16)<<7)|127
    struct.pack_into('>H',base,teaching+4,4)
    struct.pack_into('>I',base,teaching+20,zlib.crc32(base[teaching+32:teaching+32+inputs*24+splits*12]))
    body = b''.join([event()] if records is None else records)
    head = struct.pack('>IHHIIIHHII', 0x53474358, 1, 32, len(body)//96, flags,
                       zlib.crc32(body), 96, 1, 0, 0)
    out = bytearray(base + head + body)
    struct.pack_into('>H', out, 4, 10)
    struct.pack_into('>I', out, 8, len(out))
    struct.pack_into('>I', out, 24, 127)
    struct.pack_into('>I', out, 72, len(out)-256)
    return rechecksum_ghost(out)


def context_offset(data):
    pose = 0x900 + struct.unpack_from('>I', data, 68)[0]*16
    inputs, splits = struct.unpack_from('>II', data, pose+8)
    camera = pose + 32 + inputs*24 + splits*12
    return camera + 32 + struct.unpack_from('>I', data, camera+8)[0]*24


def changed(data, offset, value, seal=True):
    out = bytearray(data);begin = context_offset(out)
    out[begin+offset:begin+offset+len(value)] = value
    if seal:struct.pack_into('>I', out, begin+16, zlib.crc32(out[begin+32:]))
    return rechecksum_ghost(out)


def changed_input(data, index, *, relative=None, yaw=None, mode=None, teaching_version=None):
    out=bytearray(data);teaching=0x900+struct.unpack_from('>I',out,68)[0]*16
    count,splits=struct.unpack_from('>II',out,teaching+8)
    if teaching_version is not None:struct.pack_into('>H',out,teaching+4,teaching_version)
    if index is not None:
        at=teaching+32+index*24
        if relative is not None:
            struct.pack_into('>H',out,at,relative&65535)
            out[at+15]=(out[at+15]&127)|((relative>>16)<<7)
        if yaw is not None:struct.pack_into('>h',out,at+2,yaw)
        if mode is not None:out[at+15]=(out[at+15]&128)|mode
    struct.pack_into('>I',out,teaching+20,zlib.crc32(out[teaching+32:teaching+32+count*24+splits*12]))
    return rechecksum_ghost(out)


def complete_camera(base, count):
    keys = b''.join(struct.pack('>I',100+i)+bytes(9)+struct.pack('>4hHB',0,0,0,32767,45*256,64 if not i else 0)
                    for i in range(count))
    head=struct.pack('>IHH6I',0x53474341,1,32,count,0,zlib.crc32(keys),0,0,0)
    out=bytearray(base+head+keys)
    struct.pack_into('>H',out,4,8);struct.pack_into('>I',out,24,31)
    struct.pack_into('>I',out,8,len(out));struct.pack_into('>I',out,72,len(out)-256)
    return rechecksum_ghost(out)


class ContextTests(unittest.TestCase):
    setUpClass=classmethod(camera_fixture.CameraStorageTests.setUpClass.__func__)
    setUp=camera_fixture.CameraStorageTests.setUp
    add=camera_fixture.CameraStorageTests.add
    file=camera_fixture.CameraStorageTests.file
    request=camera_fixture.CameraStorageTests.request
    page=camera_fixture.CameraStorageTests.page
    accepted=camera_fixture.CameraStorageTests.accepted
    rejected=camera_fixture.CameraStorageTests.rejected

    def test_legacy_versions_keep_their_semantics(self):
        files=[build_ghost(version=3),build_ghost(version=4),teaching_file(),
               teaching_file(fludd=[bytes(8)]*3),teaching_file(fludd=[bytes(8)]*3,extended=True),
               camera_file(),rng_file()]
        for version,data in enumerate(files,3):
            self.dll.reset();result=self.accepted(data)
            self.assertEqual(result['version'],version);self.assertIsNone(result['context'])
        bad=bytearray(rng_file());struct.pack_into('>II',bad,0x138,1,1)
        self.rejected(seal_table(bad))

    def test_empty_full_and_unknown_context_round_trip(self):
        for records in ([],[event()], [event(flags=7,seed=0xffffffff,move=0xffffffff,director=42,yaw=-32768,mode=73)],
                        [event()]+[event(kind=2,serial=i) for i in range(1,169)]):
            self.dll.reset();result=self.accepted(context_file(records,flags=int(len(records)==169)))
            self.assertEqual(result['context']['record_count'],len(records))
            self.assertEqual(result['initial_rng']['provenance'],'first_recorded_pose')
        self.accepted(context_file([event(flags=64)]))

    def test_header_extents_schema_and_unknown_flags(self):
        data=context_file()
        edits=[(0,b'BAD!'),(5,b'\x02'),(7,b'\x21'),(8,struct.pack('>I',170)),
               (8,struct.pack('>I',0xffffffff)),(12,struct.pack('>I',2)),
               (20,struct.pack('>H',95)),(22,struct.pack('>H',2)),(24,b'\x01'),(28,b'\x01')]
        for offset,value in edits:
            with self.subTest(offset=offset,value=value):self.rejected(changed(data,offset,value))
        for amount in (1,32,96,128):
            bad=bytearray(data[:-amount]);struct.pack_into('>I',bad,8,len(bad));struct.pack_into('>I',bad,72,len(bad)-256)
            self.rejected(rechecksum_ghost(bad))
        bad=bytearray(data+b'\0'*96);struct.pack_into('>I',bad,8,len(bad));struct.pack_into('>I',bad,72,len(bad)-256)
        self.rejected(rechecksum_ghost(bad))
        for version,required in ((9,63),(10,63),(10,255)):
            bad=bytearray(data);struct.pack_into('>H',bad,4,version);struct.pack_into('>I',bad,24,required)
            self.rejected(rechecksum_ghost(bad))

    def test_record_unknown_fields_identity_and_settings(self):
        variants=[event(qf=99),event(qf=105),event(index=1),event(segment=1),event(kind=0),event(kind=7),
                  event(flags=128),event(seed=1),event(move=1),event(director=1),event(yaw=1),event(mode=1),
                  event(flags=8),event(kind=2,flags=16),event(kind=4),event(kind=5,qf=100),event(flags=4,mode=74)]
        for data in variants:
            with self.subTest(data=data[:32]):self.rejected(context_file([data]))
        for offset,value in [(0,2),(1,3),(16,4),(40,1),(46,2),(47,1),(56,1)]:
            snapshot=settings();snapshot[offset]=value
            self.rejected(context_file([event(snapshot=snapshot)]))
        for value in (0.0,-1.0,float('nan'),float('inf'),240.01):
            snapshot=settings();struct.pack_into('>f',snapshot,48,value)
            self.rejected(context_file([event(snapshot=snapshot)]))
        snapshot=settings();struct.pack_into('>I',snapshot,52,2)
        self.rejected(context_file([event(snapshot=snapshot)]))
        snapshot=settings();snapshot[46]=255
        self.assertIsNone(self.accepted(context_file([event(snapshot=snapshot)]))['context']['records'][0]['settings']['pineapple_removed'])

    def test_order_duplicate_segments_restore_and_terminal_events(self):
        accepted=[[event(),event(kind=2),event(kind=3),event(kind=4,flags=32,serial=0),event(qf=104,kind=5)],
                  [event(qf=102,flags=16),event(qf=104,kind=6)]]
        for rows in accepted:self.accepted(context_file(rows))
        rejected=[[event(),event()], [event(kind=2),event()],
                  [event(qf=102),event(qf=101,kind=2)],
                  [event(qf=104,kind=5),event(qf=104,kind=2)],
                  [event(qf=104,kind=6),event(qf=104,kind=5)]]
        for rows in rejected:self.rejected(context_file(rows))
        # A valid second segment need not have context when unavailable/truncated.
        base=bytearray(rng_file(base=camera_file(0)))
        struct.pack_into('>H',base,184,2);struct.pack_into('>I',base,0x104,1);struct.pack_into('>I',base,0x10c,100)
        struct.pack_into('>4Ii4B2I',base,0x120,1,1,104,104,0,2,0,255,0,0,0);struct.pack_into('>H',base,0x912,0)
        base=seal_table(base)
        self.accepted(context_file([event(),event(qf=104,segment=1)],base=base))
        self.accepted(context_file([event()],flags=1,base=base))
        self.rejected(context_file([event(qf=104,segment=1),event()],base=base))

    def test_all_segments_and_input_index_rebasing_rules(self):
        route={'area':2,'episode':0,'parent_area':255,'flags':0,'variant':0}
        segments=[{'first_sample':i,'sample_count':1,'start_qf':100+4*i,'end_qf':100+4*i,'route':route} for i in range(64)]
        base=build_ghost(version=4,samples=[(0,0,0,0,0,0,0)]*64,segments=segments,end_qf=352)
        base=teaching_file(inputs=[],splits=[],base=base,fludd=[],extended=True)
        base=rng_file(base=complete_camera(base,0))
        data=context_file([event(qf=100+4*i,segment=i,serial=i) for i in range(64)],base=base)
        self.assertEqual(self.accepted(data)['context']['record_count'],64)
        self.rejected(changed(data,32+63*96+24,struct.pack('>H',64)))
        base=rng_file(base=complete_camera(teaching_file(fludd=[bytes(8)]*3,extended=True),3))
        self.accepted(context_file([event(index=2),event(qf=102,index=1,kind=4,flags=32),event(qf=104,index=1,kind=2)],base=base))
        self.rejected(context_file([event(index=2),event(qf=104,index=1,kind=2)],base=base))
        self.rejected(context_file([event(index=1,flags=64)],base=base))
        self.accepted(context_file([event(flags=64),event(qf=104,index=3,kind=2)],base=base))

    def test_context_checksums_and_import_preservation(self):
        data=context_file([event(flags=7,seed=0x12345678,yaw=-123,mode=73)])
        self.rejected(changed(data,32+20,b'\x22',seal=False))
        repaired=changed(data,32+20,b'\x22')
        self.assertEqual(self.accepted(repaired)['context']['records'][0]['pre_setup_seed'],0x22345678)
        self.add(IMPORT+'context.smsghost',data);rows,total,_,_=self.page(profile=4)
        self.assertEqual(total,1)
        result=self.request(2,rows[0][0],profile=4,generation=rows[0][1],payload=b'context.smsghost'.ljust(96,b'\0'))
        self.assertEqual(result['status'],0)
        self.assertEqual(ctypes.string_at(self.dll.payload(),result['size']),data)
        self.assertLessEqual(self.dll.maximumRead(),0x4000)

    def test_steering_packing_boundaries_controller_bytes_and_version_pair(self):
        base=build_ghost(version=4,start_qf=0x7fffffff-71928,
            samples=[(0,0,0,0,0,0,0)]+[(0,0,0,0,4,0,0)]*17982)
        start=0x7fffffff-71928
        records=[(start+r,0x1f7f,-128,127,-127,126,255,254,253,252,-3,0) for r in (0,65535,65536,71928)]
        visuals=[bytes([0x18,127,128,255,0,0,0,255])]*4
        base=teaching_file(inputs=records,splits=[],base=base,fludd=visuals,extended=True)
        base=rng_file(base=complete_camera(base,0))
        data=context_file([],base=base)
        for i,yaw in enumerate((-32768,-1,0,32767)):data=changed_input(data,i,yaw=yaw,mode=73)
        result=self.accepted(data)
        self.assertTrue(result['teaching']['camera_steering'])
        teaching=0x900+17983*16
        for i,record in enumerate(records):
            at=teaching+32+i*24
            self.assertEqual(data[at+4:at+15],struct.pack('>HbbbbBBBBbB',*record[1:])[:11])
            self.assertEqual(data[at+16:at+24],visuals[i])
        for kwargs in ({'relative':71929},{'relative':131071},{'mode':74},{'mode':126},{'mode':127,'yaw':1}):
            self.rejected(changed_input(data,3,**kwargs))
        self.rejected(changed_input(data,2,relative=65535))
        self.rejected(changed_input(data,None,teaching_version=3))
        self.accepted(changed_input(data,3,mode=127,yaw=0))
        # Previous formats must still reject SGTI4 and their reserved controller flag byte.
        legacy=bytearray(rng_file());at=0x900+struct.unpack_from('>I',legacy,68)[0]*16
        struct.pack_into('>H',legacy,at+4,4);self.rejected(rechecksum_ghost(legacy))

    def test_maximum_file_and_record_boundary_within_existing_ceiling(self):
        poses=[(0,0,0,0,0,0,0)]+[(0,0,0,0,4,0,0)]*17982
        base=build_ghost(version=4,samples=poses)
        inputs=[(100+i,0,0,0,0,0,0,0,0,0,0,0) for i in range(36000)]
        splits=[(100+i,1,0,i,0) for i in range(8)]
        base=teaching_file(inputs=inputs,splits=splits,base=base,fludd=[bytes(8)]*36000,extended=True)
        base=rng_file(base=complete_camera(base,5312))
        data=context_file([event()]+[event(kind=2,serial=i) for i in range(1,169)],base=base)
        self.assertEqual(len(data),1297936)
        self.assertLessEqual(len(data),1298016)
        self.assertEqual(self.accepted(data)['context']['record_count'],169)
        self.assertLessEqual(self.dll.maximumRead(),0x4000)
        self.assertGreater(self.passes,100)


if __name__=='__main__':unittest.main()
