"""Local Cesium dashboard and isolated, repeatable Python simulation jobs."""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
import re
import sys
import threading
import uuid
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from panda_abm.twin.replay import DEFAULTS,record_run,validate_settings,LiveSimulation

WEB=ROOT/'dashboard'
RUNS=WEB/'replays'
POOL=ThreadPoolExecutor(max_workers=1)
JOBS={}
LIVE={}
LOCK=threading.Lock()


def write_replay(path,data):
    payload=json.dumps(data,separators=(',',':'),allow_nan=False).encode()
    temp=path.with_suffix('.tmp')
    temp.write_bytes(gzip.compress(payload,mtime=0))
    temp.replace(path)


def calculate(run_id,settings):
    try:
        with LOCK:JOBS[run_id].update(status='running')
        def progress(seconds):
            with LOCK:JOBS[run_id]['simulation_seconds']=seconds
        data=record_run(settings,progress)
        write_replay(RUNS/f'{run_id}.json.gz',data)
        with LOCK:JOBS[run_id].update(status='complete',summary=data['summary'],duration_s=data['duration_s'])
    except Exception as exc:
        with LOCK:JOBS[run_id].update(status='failed',error=str(exc))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WEB),**kwargs)

    def json_response(self,data,status=200):
        encoded=json.dumps(data,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(encoded)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(encoded)

    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/scene':
            config=json.loads((ROOT/'data/lot_config.json').read_text())
            alignment=json.loads((WEB/'alignment.json').read_text()) if (WEB/'alignment.json').exists() else None
            self.json_response(dict(config=config,alignment=alignment,defaults=DEFAULTS));return
        if path=='/api/runs':
            with LOCK:jobs=[dict(id=k,**v) for k,v in JOBS.items()]
            self.json_response(jobs);return
        match=re.fullmatch(r'/api/runs/(baseline|[a-f0-9]{32})(/data)?',path)
        if match:
            run_id,suffix=match.groups()
            if suffix:
                file=RUNS/f'{run_id}.json.gz'
                if not file.exists():self.json_response(dict(error='Replay not ready'),404);return
                content=file.read_bytes()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Encoding','gzip');self.send_header('Content-Length',str(len(content)))
                self.end_headers();self.wfile.write(content);return
            with LOCK:job=JOBS.get(run_id)
            self.json_response(dict(id=run_id,**job) if job else dict(error='Unknown run'),200 if job else 404);return
        # Replays are only exposed via the API; local-only source/provenance may be served.
        if path.startswith('/replays/') or '..' in path.split('/'):
            self.send_error(404);return
        super().do_GET()

    def do_POST(self):
        # Loopback-only server; reject cross-origin browser requests.
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://{self.headers.get("Host")}':
            self.json_response(dict(error='Cross-origin requests are not allowed'),403);return
        path=urlparse(self.path).path
        live_match=re.fullmatch(r'/api/live/([a-f0-9]{32})',path)
        if path not in ('/api/runs','/api/live') and not live_match:self.json_response(dict(error='Unknown endpoint'),404);return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=4096:raise ValueError('Expected a small JSON scenario')
            payload=json.loads(self.rfile.read(n))
            if live_match:
                with LOCK:session=LIVE.get(live_match[1])
                if not session:self.json_response(dict(error='Live session not found'),404);return
                if payload=={'action':'close'}:
                    with LOCK:LIVE.pop(live_match[1],None)
                    self.json_response(dict(closed=True));return
                if not isinstance(payload,dict) or set(payload)!={'seconds'}:raise ValueError('Expected seconds or close action')
                self.json_response(session.advance(payload['seconds']));return
            settings=validate_settings(payload)
            if path=='/api/live':
                with LOCK:
                    if len(LIVE)>=4:self.json_response(dict(error='Close an existing live session first'),429);return
                    live_id=uuid.uuid4().hex
                    session=LiveSimulation(settings);LIVE[live_id]=session
                self.json_response(dict(id=live_id,**session.describe()),201);return
        except (ValueError,TypeError) as exc:self.json_response(dict(error=str(exc)),400);return
        with LOCK:
            if sum(j['status'] in ('queued','running') for j in JOBS.values())>=4:
                self.json_response(dict(error='Four runs are already queued; wait for completion'),429);return
            run_id=uuid.uuid4().hex
            JOBS[run_id]=dict(status='queued',settings=settings)
        POOL.submit(calculate,run_id,settings)
        self.json_response(dict(id=run_id,status='queued'),202)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--prepare-replay',action='store_true',help='Record default replay; verify archived outcomes if available')
    args=parser.parse_args();RUNS.mkdir(parents=True,exist_ok=True)
    if args.prepare_replay or not (RUNS/'baseline.json.gz').exists():
        print('Recording baseline replay from current ABM...',flush=True)
        archived=(ROOT/'results/parking_information_20261028/checks.json').exists()
        data=record_run(DEFAULTS,verify_archive=archived)
        write_replay(RUNS/'baseline.json.gz',data)
        print('Baseline: '+json.dumps(data['verification'] or data['summary']),flush=True)
    for path in sorted(RUNS.glob('*.json.gz')):
        run_id=path.name.removesuffix('.json.gz')
        if not re.fullmatch(r'baseline|[a-f0-9]{32}',run_id):continue
        data=json.loads(gzip.decompress(path.read_bytes()))
        JOBS[run_id]=dict(status='complete',settings=data['settings'],summary=data['summary'],duration_s=data['duration_s'])
    print(f'PANDA dashboard: http://127.0.0.1:{args.port}',flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=False,cancel_futures=True)


if __name__=='__main__':main()
