#!/usr/bin/env python3
"""Loopback-only conversation dashboard for Noobia coding agents."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from plugins import PLUGINS
import foreman_control as foreman

ROOT = Path(__file__).resolve().parent
HOST = '127.0.0.1'
PORT = int(os.environ.get('NOOBIA_DUSHICH_WEB_PORT', '8765'))


class Handler(BaseHTTPRequestHandler):
    def _allowed_host(self) -> bool:
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')

    def _json(self, status: int, data: object) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name: str, kind: str) -> None:
        body = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._allowed_host():
            self._json(403, {'error': 'Invalid host'})
            return
        route = urlsplit(self.path)
        try:
            if route.path == '/':
                self._file('index.html', 'text/html; charset=utf-8')
            elif route.path == '/status':
                self._file('status.html', 'text/html; charset=utf-8')
            elif route.path == '/app.css':
                self._file('app.css', 'text/css; charset=utf-8')
            elif route.path == '/home.css':
                self._file('home.css', 'text/css; charset=utf-8')
            elif route.path == '/app.js':
                self._file('app.js', 'text/javascript; charset=utf-8')
            elif route.path == '/home.js':
                self._file('home.js', 'text/javascript; charset=utf-8')
            elif route.path == '/api/foreman':
                self._json(200, foreman.snapshot())
            elif route.path == '/api/active-projects':
                self._json(200, foreman.active_conversations())
            elif route.path == '/api/agents':
                self._json(200, [{'id': p.id, 'name': p.name, 'color': p.color,
                                  'has_tokens': getattr(p, 'has_tokens', False)}
                                 for p in PLUGINS.values()])
            elif route.path == '/api/tokens':
                query = parse_qs(route.query)
                name = query.get('agent', [''])[0]
                ident = query.get('conversation', [''])[0]
                agent = PLUGINS.get(name)
                if not agent or not getattr(agent, 'has_tokens', False):
                    self._json(200, {'supported': False})
                else:
                    info = agent.tokens(ident) if hasattr(agent, 'tokens') else None
                    if info is None:
                        self._json(200, {'supported': True, 'available': False})
                    else:
                        self._json(200, {'supported': True, 'available': True, **info})
            elif route.path == '/api/conversations':
                name = parse_qs(route.query).get('agent', [''])[0]
                self._json(200, PLUGINS[name].conversations())
            elif route.path == '/api/timeline':
                query = parse_qs(route.query)
                name = query.get('agent', [''])[0]
                ident = query.get('conversation', [''])[0]
                self._json(200, PLUGINS[name].timeline(ident))
            else:
                self._json(404, {'error': 'Not found'})
        except (KeyError, ValueError) as exc:
            self._json(400, {'error': str(exc)})
        except Exception as exc:
            self._json(500, {'error': f'{type(exc).__name__}: {exc}'})

    def do_POST(self) -> None:
        self._json(405, {'error': 'This page is read-only; use a terminal agent.'})


if __name__ == '__main__':
    print(f'Dushich dashboard: http://{HOST}:{PORT}/', flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
