"""Local, read-only Moonshine memory monitor using the ordinary room-code protocol."""
from __future__ import annotations
import argparse, ctypes as C, ipaddress, json, secrets, socket, struct, threading, time, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
class NativePeer:
    def __init__(self, path, *, host=True, pin=1234, nonce=None, remote=("0.0.0.0",0)):
        self.dll=C.CDLL(str(Path(path).resolve()))
        signatures={"mm_create":([C.c_uint]*7,C.c_void_p),"mm_destroy":([C.c_void_p],None),
            "mm_code":([C.c_uint,C.c_uint,C.c_uint,C.c_void_p],C.c_int),
            "mm_decode":([C.c_char_p,C.POINTER(C.c_uint),C.POINTER(C.c_uint)],C.c_uint),
            "mm_state":([C.c_void_p],C.c_uint),"mm_ping":([C.c_void_p],C.c_uint),
            "mm_name":([C.c_void_p,C.c_void_p],None),"mm_tick":([C.c_void_p,C.c_uint],None),
            "mm_pop":([C.c_void_p,C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.c_void_p],C.c_uint),
            "mm_report":([C.c_void_p,C.c_uint,C.c_void_p],C.c_uint),
            "mm_receive":([C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint],C.c_int),
            "mm_test_report":([C.c_void_p,C.c_void_p],C.c_int),
            "mm_detail":([C.c_void_p,C.c_void_p],C.c_uint),
            "mm_detail_dropped":([C.c_void_p],C.c_uint),
            "mm_command":([C.c_void_p,C.c_uint,C.c_uint],C.c_int)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.dll,name);fn.argtypes=args;fn.restype=result
        hi,lo=nonce or (secrets.randbits(32) or 1,secrets.randbits(32) or 1)
        self.handle=self.dll.mm_create(host,pin,hi,lo,int(ipaddress.IPv4Address(remote[0])),remote[1],0)
        if not self.handle:raise RuntimeError("Could not create monitor session")
        self.pin=pin;self.generation=0
    def code(self,ip,port):
        out=C.create_string_buffer(32)
        if not self.dll.mm_code(int(ipaddress.IPv4Address(ip)),port,self.pin,out):raise ValueError("Invalid monitor address")
        return out.value.decode("ascii")
    def tick(self,now):self.dll.mm_tick(self.handle,now&0xffffffff)
    def receive(self,data,source,now):
        return self.dll.mm_receive(self.handle,int(ipaddress.IPv4Address(source[0])),source[1],data,len(data),now&0xffffffff)
    def outgoing(self):
        out=C.create_string_buffer(256);ip=C.c_uint();port=C.c_uint()
        while (n:=self.dll.mm_pop(self.handle,C.byref(ip),C.byref(port),out)):
            yield out.raw[:n],(str(ipaddress.IPv4Address(ip.value)),port.value)
    def report(self):
        out=C.create_string_buffer(64);generation=self.dll.mm_report(self.handle,self.generation,out)
        if generation==self.generation:return None
        self.generation=generation;return out.raw
    def details(self):
        out=C.create_string_buffer(64)
        while self.dll.mm_detail(self.handle,out):yield out.raw
    def command(self,identifier,operation):return bool(self.dll.mm_command(self.handle,identifier,operation))
    def state(self):return self.dll.mm_state(self.handle)
    def name(self):
        out=C.create_string_buffer(17);self.dll.mm_name(self.handle,out);return out.value.decode("ascii","replace")
    def close(self):
        if self.handle:
            self.dll.mm_destroy(self.handle);self.handle=None
            if sys.platform=="win32":
                from _ctypes import FreeLibrary
                FreeLibrary(self.dll._handle)
            self.dll=None
AREA_NAMES={0:"Airstrip",1:"Delfino Plaza",2:"Bianco Hills",3:"Ricco Harbor",4:"Gelato Beach",5:"Pinna Beach",6:"Sirena Beach",7:"Hotel Delfino",8:"Pianta Village",9:"Noki Bay",13:"Pinna Park",14:"Casino",15:"Title / file select",16:"Noki underwater",20:"Plaza secret",29:"Pinna secret",30:"Ricco secret",31:"Noki 6 secret",32:"Gelato secret",33:"Gelato secret",40:"Sirena secret",41:"Casino secret",42:"Pianta secret",44:"Noki secret",46:"Bianco secret",47:"Bianco secret",50:"Corona Mountain"}
def decode_report(raw):
    if len(raw)!=64:raise ValueError("Wrong telemetry length")
    v=struct.unpack(">16I",raw)
    if not 0x4d4d5431<=v[0]<=0x4d4d5435 or v[3]&~7 or v[2]>>24>2:raise ValueError("Unsupported telemetry")
    result={"page":v[0]-0x4d4d5431,"sample":v[1],"region":("JP","US","PAL")[v[2]>>24],"context":v[2]>>16&255,
        "area":v[2]>>8&255,"episode":v[2]&255,"flags":v[3],"sample_ticks":v[14],"wii_ms":v[15]}
    result["level"]=AREA_NAMES.get(result["area"],f"Area {result['area']}")+f"  /  episode {result['episode']+1}"
    if result["page"]==4:
        phase,error,produced,written,queued,peak,records,capture_us,write_ticks,frames,capabilities=v[4:15]
        if phase>6 or error>7 or produced>0x7f000000 or written>0x7f000000 or queued>0x100000 or peak>0x100000 or capabilities&~0xffffff:
            raise ValueError("Invalid SD capture report")
        result["trace"]={"phase":phase,"error":error,"status":("Off","Starting","Recording","Finishing","Saved","Discarded","Failed")[phase],
            "produced":produced,"written":written,"queued":queued,"peak":peak,"records":records,"capture_us":capture_us,
            "write_ms":write_ticks*1000/1898437,"frames":frames,"capabilities":capabilities}
        return result
    if result["page"]==3:
        flags,error,upper,aram,progress,total,passes,bad,expected,observed,phase=v[4:15]
        if flags&~31 or error>7 or upper!=0x1e0000 or aram!=0x60000 or total!=upper+aram or progress>total or phase>2:
            raise ValueError("Invalid memory-reservation report")
        errors={1:"Launcher grant unavailable",2:"Memory grant rejected",3:"Address mapping unavailable",4:"Waiting for native ARAM space",5:"Unexpected ARAM allocation",6:"ARAM ownership changed",7:"Memory pattern mismatch"}
        label=errors.get(error,"Waiting for a ready stage") if flags&3!=3 or flags&16 else "Memory reserved for capture" if flags&4 else "Writing test pattern" if phase==1 else "Checks passing" if passes else "Verifying test pattern"
        result["memory_test"]={"flags":flags,"error":error,"status":label,"upper_bytes":upper,"aram_bytes":aram,"progress_bytes":progress,"total_bytes":total,"passes":passes,"bad_address":bad,"expected":expected,"observed":observed,"phase":phase,"capture_available":bool(v[3]&2)}
        return result
    if result["page"]==1:
        if result["flags"]&1:
            cap,extent,one,two,three,used=v[4:10]
            if not 0<cap<=32*1048576 or not used<=extent<=cap or max(one,two,three)>32*1048576:raise ValueError("Invalid state pool")
            result["states"]={"capacity":cap,"used":used,"free":cap-used,"tail_free":cap-extent,"extent":extent,"slots":[one,two,three]}
        else:result["states"]=None
        if result["flags"]&2:
            if any(n>2*1048576 for n in v[10:14]):raise ValueError("Invalid ghost payload usage")
            result["ghosts"]={"record_poses":v[10],"record_inputs":v[11],"playback_poses":v[12],"playback_inputs":v[13]}
        else:result["ghosts"]=None
        return result
    names=("audio","archives","stage") if not result["page"] else ("root","system","audio_mem1")
    for name,index,flag in ((names[0],4,1),(names[1],8,2)):
        cap,used,largest,tail=v[index:index+4]
        if result["flags"]&flag:
            limit=(16 if not result["page"] else 24)*1048576
            if not 0<cap<=limit or used>cap or largest>cap-used:raise ValueError("Invalid pool measurements")
            if not result["page"] and not used<=tail<=cap:raise ValueError("Invalid tail extent")
            result[name]={"capacity":cap,"used":used,"free":cap-used,"largest_free":largest}
            if not result["page"]:result[name]["tail_extent"]=tail
        else:result[name]=None
    cap,free=v[12:14]
    if result["flags"]&4:
        if not 0<cap<=24*1048576 or free>cap:raise ValueError("Invalid solid heap")
        result[names[2]]={"capacity":cap,"used":cap-free,"free":free}
    else:result[names[2]]=None
    return result

def apply_measurement(state, measurement, now):
    state["latest"] = {**(state["latest"] or {}), **measurement}
    state["pages_seen"][str(measurement["page"])] = measurement["received_unix"]
    state["last_received"] = measurement["received_unix"]
    state["samples"] += 1
    for pool in ("audio", "archives", "stage", "states", "root", "system", "audio_mem1"):
        if pool not in measurement:
            continue
        current = measurement[pool]
        if current is None:
            state["invalid_pool_samples"] += 1
            continue
        state["observed_peaks"][pool] = max(state["observed_peaks"].get(pool, 0), current["used"])
        key = f"{measurement['region']}:{measurement['area']}:{measurement['episode']}"
        peaks = state["stage_peaks"].setdefault(key, {"level": measurement["level"]})
        peaks[pool] = max(peaks.get(pool, 0), current["used"])
    if measurement["page"] == 0:
        state["history"].append({"t": now / 1000, **{
            key: measurement[key]["used"] if measurement[key] else None
            for key in ("audio", "archives", "stage")}})
        del state["history"][:-1200]


def decode_detail(raw):
    if len(raw)!=64:raise ValueError("Invalid capture length")
    v=struct.unpack(">12I",raw[:48]);magic,identifier,index,count=v[:4]
    if magic!=0x4d4d4431 or not identifier or not 1<=count<=64 or index>=count or v[4]>7:raise ValueError("Invalid capture header")
    name=raw[48:64].split(b"\0",1)[0]
    if len(name)>15 or any(c<32 or c>126 for c in name):raise ValueError("Invalid allocation name")
    row=dict(zip(("kind","object","address","bytes","used","children","parent","flags"),v[4:]))
    row["name"]=name.decode("ascii")
    return identifier,index,count,row

def collect_detail(capture, raw):
    identifier,index,count,row=decode_detail(raw)
    if capture.get("id")!=identifier:
        raise ValueError("Capture belongs to another request")
    if capture.get("total") not in (None,count):raise ValueError("Capture length changed")
    capture["total"]=count
    rows=capture.setdefault("rows",{})
    if str(index) in rows and rows[str(index)]!=row:raise ValueError("Conflicting capture row")
    rows[str(index)]=row
    capture["status"]="Receiving allocation map"
    if len(rows)==count:
        header=rows["0"]
        if header["kind"]!=0:raise ValueError("Missing allocation-map header")
        capture["status"]="Capture failed" if header["flags"]&2 else "Complete with unavailable sections" if header["flags"] else "Complete"
        capture["complete"]=True
    return capture.get("complete",False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native",type=Path,required=True)
    parser.add_argument("--bind",required=True)
    parser.add_argument("--allow-ip",required=True)
    parser.add_argument("--port",type=int,default=48223)
    parser.add_argument("--http-port",type=int,default=8768)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--resume-code")
    args=parser.parse_args()
    for value in (args.bind,args.allow_ip):
        address=ipaddress.IPv4Address(value)
        if not address.is_private or address.is_unspecified or address.is_multicast:parser.error("Use explicit local-network IPv4 addresses")
    args.output.mkdir(parents=True,exist_ok=True)
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind((args.bind,args.port));udp.setblocking(False)
    peer=NativePeer(args.native,pin=secrets.randbelow(8191)+1)
    if args.resume_code:
        ip=C.c_uint();port=C.c_uint()
        pin=peer.dll.mm_decode(args.resume_code.encode("ascii"),C.byref(ip),C.byref(port))
        if not pin or str(ipaddress.IPv4Address(ip.value))!=args.bind or port.value!=udp.getsockname()[1]:
            peer.close();udp.close();parser.error("Resume code must match this local address and port")
        peer.close();peer=NativePeer(args.native,pin=pin)
    code=peer.code(args.bind,udp.getsockname()[1])
    lock=threading.Lock();state={"code":code,"state":"Waiting for Wii", "connected":False,"latest":None,"observed_peaks":{},"stage_peaks":{},"history":[],"pages_seen":{},"invalid_pool_samples":0,"capture":{},"command_queue":[],"samples":0,"invalid_packets":0,"last_received":None,"log_directory":str(args.output.resolve())}
    if args.resume_code:
        first=None
        for previous_log in sorted(args.output.glob("samples_*.jsonl")):
            with previous_log.open(encoding="utf-8") as previous:
                for line in previous:
                    try:
                        measurement=json.loads(line)
                        if measurement.get("page") not in (0,1,2,3,4):continue
                        first=measurement["received_unix"] if first is None else first
                        apply_measurement(state,measurement,int((measurement["received_unix"]-first)*1000))
                    except (ValueError,KeyError,TypeError):continue
    if args.resume_code:
        captures=sorted(args.output.glob("allocation_dump_*.json"),key=lambda p:p.stat().st_mtime)
        if captures:
            try:
                old_capture=json.loads(captures[-1].read_text(encoding="utf-8"))
                if old_capture.get("complete"):
                    state["capture"]=old_capture
                    state["capture"]["file"]=str(captures[-1])
            except (ValueError,OSError):pass
    page=Path(__file__).with_name("index.html").read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            if self.path!="/command" or self.headers.get("Host") not in (f"127.0.0.1:{args.http_port}",f"localhost:{args.http_port}") or self.headers.get("Origin") not in (None,f"http://127.0.0.1:{args.http_port}",f"http://localhost:{args.http_port}"):
                self.send_error(403);return
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=128 or self.headers.get_content_type()!="application/json":raise ValueError()
                request=json.loads(self.rfile.read(size))
                if set(request)!={"operation"} or request["operation"] not in ("capture","cancel","record_trace","save_trace","discard_trace"):raise ValueError()
            except (ValueError,TypeError):self.send_error(400);return
            with lock:
                memory_test=(state["latest"] or {}).get("memory_test")
                trace_operation=request["operation"].endswith("trace")
                if not state["connected"] or state["command_queue"] or (trace_operation and time.time()-state["pages_seen"].get("4",0)>10) or (not trace_operation and memory_test and not memory_test["capture_available"] and time.time()-state["pages_seen"].get("3",0)<10):
                    self.send_error(409);return
                identifier=(int(time.time()*1000)&0xffffffff) or 1
                operation={"capture":1,"cancel":2,"record_trace":3,"save_trace":4,"discard_trace":5}[request["operation"]]
                if operation==1 and state["capture"] and not state["capture"].get("complete") and time.time()-state["capture"].get("requested_unix",0)<40:
                    self.send_error(409);return
                state["command_queue"].append((identifier,operation))
                if operation==1:state["capture"]={"id":identifier,"status":"Queued", "requested_unix":time.time(),"rows":{}}
                elif operation==2:state["capture"]["status"]="Cancel requested"
                else:state["trace_request"]={"id":identifier,"operation":request["operation"],"requested_unix":time.time()}
            body=json.dumps({"request_id":identifier,"operation":request["operation"]}).encode()
            self.send_response(202);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.headers.get("Host") not in (f"127.0.0.1:{args.http_port}",f"localhost:{args.http_port}"):
                self.send_error(403);return
            if self.path=="/":body=Path(__file__).with_name("index.html").read_bytes();kind="text/html; charset=utf-8"
            elif self.path=="/status":
                with lock:body=json.dumps(state).encode()
                kind="application/json"
            else:self.send_error(404);return
            self.send_response(200);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(body)
    http=ThreadingHTTPServer(("127.0.0.1",args.http_port),Handler)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    start=time.monotonic();log_number=0;log=None;log_rows=0
    info={"code":code,"udp":f"{args.bind}:{udp.getsockname()[1]}","wii_ip":args.allow_ip,"url":f"http://127.0.0.1:{args.http_port}","started_unix":time.time()}
    (args.output/"session.json").write_text(json.dumps(info,indent=2)+"\n")
    print(json.dumps(info),flush=True)
    try:
        while not (args.output/"stop.request").exists():
            now=int((time.monotonic()-start)*1000)&0xffffffff
            for _ in range(64):
                try:data,address=udp.recvfrom(2048)
                except BlockingIOError:break
                if address[0]!=args.allow_ip or len(data)>256:continue
                peer.receive(data,address,now)
            peer.tick(now)
            with lock:
                if state["command_queue"]:
                    identifier,operation=state["command_queue"][0]
                    if peer.command(identifier,operation):
                        state["command_queue"].pop(0)
                        if operation in (1,2):state["capture"]["status"]="Waiting for paused snapshot" if operation==1 else "Capture cancelled"
                        if operation==2:state["capture"]["complete"]=True
            for data,address in peer.outgoing():
                if address[0]!=args.allow_ip:continue
                try:udp.sendto(data,address)
                except (BlockingIOError,OSError):pass
            raw=peer.report()
            with lock:
                state["connected"]=peer.state()==4
                state["state"]="Connected to "+peer.name() if state["connected"] else "Waiting for Wii"
                state["ping_ms"]=peer.dll.mm_ping(peer.handle)
                for detail in peer.details():
                    try:
                        complete=collect_detail(state["capture"],detail)
                        if complete and not state["capture"].get("file"):
                            capture_path=args.output/f"allocation_dump_{state['capture']['id']:08x}.json"
                            with capture_path.open("x",encoding="utf-8") as saved:
                                json.dump(state["capture"],saved,indent=2);saved.write("\n")
                            state["capture"]["file"]=str(capture_path)
                    except (ValueError,FileExistsError):state["invalid_packets"]+=1
                state["capture_dropped"]=peer.dll.mm_detail_dropped(peer.handle)
                if state["capture"] and not state["capture"].get("complete") and time.time()-state["capture"].get("requested_unix",0)>40:
                    state["capture"]["status"]="Capture timed out; update the Wii test build if needed"
                if raw:
                    try:
                        measurement=decode_report(raw);measurement["received_unix"]=time.time()
                        apply_measurement(state,measurement,now)
                        if log is None or log_rows>=10000:
                            if log:log.close()
                            while (args.output/f"samples_{log_number:03d}.jsonl").exists():log_number+=1
                            log=(args.output/f"samples_{log_number:03d}.jsonl").open("x",buffering=1);log_rows=0
                        log.write(json.dumps(measurement,separators=(",",":"))+"\n");log_rows+=1
                        # Replace one complete snapshot; readers never need the growing log.
                        temporary=args.output/"latest.tmp";temporary.write_text(json.dumps({k:v for k,v in state.items() if k!="history"},indent=2)+"\n");temporary.replace(args.output/"latest.json")
                    except ValueError:state["invalid_packets"]+=1
            time.sleep(.01)
    finally:
        if log:log.close()
        peer.close();udp.close();http.shutdown();http.server_close()
if __name__=="__main__":main()
