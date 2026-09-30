"""Single-user loopback workspace. Put authenticated infrastructure in front for a pilot."""
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import secrets
import threading
from urllib.parse import urlsplit
from .catalog import ROOT,SLUGS,catalog
from .common import InputError,loads,obj
from .__main__ import execute


def make_server(port=8765):
    nonce=secrets.token_urlsafe(32)
    slots=threading.BoundedSemaphore(2)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass  # Input, project output and URLs are not retained by the workspace.

        def send(self,status,body,mime='application/json'):
            raw=json.dumps(body).encode() if mime=='application/json' else body
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers();self.wfile.write(raw)

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                return self.send(403,{'error':'Unexpected host'})
            path=urlsplit(self.path).path
            if path=='/api/projects':
                return self.send(200,catalog())
            if path.startswith('/api/example/'):
                slug=path.removeprefix('/api/example/')
                if slug not in SLUGS:
                    return self.send(404,{'error':'Unknown project'})
                try:
                    data=loads((ROOT/'projects'/slug/'examples/input.json').read_bytes())
                except (OSError,InputError):
                    return self.send(404,{'error':'Example unavailable'})
                return self.send(200,data)
            assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if path not in assets:
                return self.send(404,{'error':'Not found'})
            filename,mime=assets[path]
            raw=(ROOT/'enterprise_ai/web'/filename).read_bytes().replace(b'__SESSION_NONCE__',nonce.encode())
            self.send(200,raw,mime)

        def do_POST(self):
            if not self.valid_host():
                return self.send(403,{'error':'Unexpected host'})
            origin=self.headers.get('Origin')
            allowed=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
            if origin is not None and origin not in allowed:
                return self.send(403,{'error':'Cross-origin requests are forbidden'})
            token=self.headers.get('X-Workspace-Token','')
            if not token.isascii() or not hmac.compare_digest(token,nonce):
                return self.send(403,{'error':'Open the workspace to establish a local session'})
            if urlsplit(self.path).path!='/api/run':
                return self.send(404,{'error':'Not found'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json' or self.headers.get('Transfer-Encoding'):
                return self.send(415,{'error':'Send bounded application/json'})
            try:
                length=int(self.headers.get('Content-Length','0'))
            except ValueError:
                length=0
            if not 0<length<=500000:
                return self.send(413,{'error':'Input must be between 1 and 500000 bytes'})
            if not slots.acquire(blocking=False):
                return self.send(429,{'error':'Two workflows are running. Try again after one completes.'})
            try:
                self.connection.settimeout(10)
                raw=self.rfile.read(length)
                if len(raw)!=length:
                    raise InputError('Incomplete request')
                request=obj(loads(raw),['project','mode','input'])
                slug=request['project']
                if slug not in SLUGS or request['mode'] not in ('live','replay'):
                    raise InputError('Unknown project or execution mode')
                responses=None
                if request['mode']=='replay':
                    example=loads((ROOT/'projects'/slug/'examples/input.json').read_bytes())
                    if request['input']!=example:
                        raise InputError('Example replay requires the unchanged example. Reload it, or choose live AI for edited data.')
                    responses=loads((ROOT/'projects'/slug/'examples/responses.json').read_bytes())
                output=execute(slug,request['input'],request['mode'],responses)
                self.send(200,output)
            except (InputError,ValueError,TypeError,KeyError,OSError,RecursionError) as exc:
                message=str(exc) if isinstance(exc,InputError) else 'Invalid input or unavailable workflow; no result produced'
                self.send(400,{'error':message})
            finally:
                slots.release()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def serve(port):
    server=make_server(port)
    print(f'Enterprise AI workspace: http://127.0.0.1:{server.server_port}',flush=True)
    print('Single-user local preview. No input or output is retained by this server.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
