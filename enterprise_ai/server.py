"""Local single-user workspace on the loopback interface. Not an authentication boundary."""
import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .catalog import ROOT, available, catalog
from .common import InputError, loads, obj
from .llm import default_provider_name
from .runner import example_input, example_replay, execute

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def make_server(port=8765):
    nonce = secrets.token_urlsafe(32)
    slots = threading.BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # inputs and results are not logged by the workspace

        def send(self, status, body, mime='application/json'):
            raw = json.dumps(body).encode() if mime == 'application/json' else body
            self.send_response(status)
            for key, value in (('Content-Type', mime), ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
                               ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'), ('Content-Security-Policy', CSP)):
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def local(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.local():
                return self.send(403, {'error': 'Unexpected host'})
            path = urlsplit(self.path).path
            if path == '/api/projects':
                return self.send(200, {'projects': catalog(), 'default_provider': default_provider_name()})
            if path.startswith('/api/example/'):
                slug = path.removeprefix('/api/example/')
                if slug not in available():
                    return self.send(404, {'error': 'Unknown project'})
                try:
                    return self.send(200, example_input(slug))
                except (OSError, ValueError):
                    return self.send(404, {'error': 'Example unavailable'})
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path not in assets:
                return self.send(404, {'error': 'Not found'})
            name, mime = assets[path]
            raw = (ROOT/'enterprise_ai/web'/name).read_bytes().replace(b'__SESSION_NONCE__', nonce.encode())
            self.send(200, raw, mime)

        def do_POST(self):
            if not self.local():
                return self.send(403, {'error': 'Unexpected host'})
            origin = self.headers.get('Origin')
            if origin is not None and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
                return self.send(403, {'error': 'Cross-origin requests are forbidden'})
            token = self.headers.get('X-Workspace-Token', '')
            if not token.isascii() or not hmac.compare_digest(token, nonce):
                return self.send(403, {'error': 'Open the workspace to establish a local session'})
            if urlsplit(self.path).path != '/api/run':
                return self.send(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if not 0 < length <= 1_000_000:
                return self.send(413, {'error': 'Input must be between 1 byte and 1 MB'})
            if not slots.acquire(blocking=False):
                return self.send(429, {'error': 'Two runs are in progress. Try again when one completes.'})
            try:
                self.connection.settimeout(10)
                raw = self.rfile.read(length)
                request = obj(loads(raw), ['project', 'mode', 'input'])
                slug, mode = request['project'], request['mode']
                if slug not in available() or mode not in ('replay', 'anthropic', 'openai'):
                    raise InputError('Unknown project or mode')
                replay = None
                if mode == 'replay':
                    if request['input'] != example_input(slug):
                        raise InputError('Replay needs the unchanged example. Reload it, or choose a live provider for edited data.')
                    replay = example_replay(slug)
                self.connection.settimeout(600)
                output = execute(slug, request['input'], mode, replay=replay)
                self.send(200, output)
            except InputError as exc:
                self.send(400, {'error': str(exc)})
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                self.send(400, {'error': 'Invalid input or unavailable workflow; no result produced'})
            finally:
                slots.release()

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def serve(port):
    server = make_server(port)
    print(f'Enterprise AI workspace: http://127.0.0.1:{server.server_port}', flush=True)
    print('Single-user local preview. Inputs and results are not stored by this server.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
