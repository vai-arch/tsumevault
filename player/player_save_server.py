"""
save_server.py - Servidor local para guardar ficheros JSON desde el navegador.

Uso:
    python save_server.py [carpeta_player] [puerto]

Ejemplos:
    python save_server.py
    python save_server.py "D:\\GoVideos\\Guo Juan\\player"
    python save_server.py "D:\\GoVideos\\Guo Juan\\player" 3001

Por defecto:
    carpeta_player : directorio donde está este script
    puerto         : 3001

Endpoint:
    POST http://localhost:3001/save
    Body: JSON { "filename": "study_stats.json", "data": { ... } }

Ficheros permitidos (whitelist):
    study_stats.json, studied.json, recorded.json
"""

import sys
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Config ──────────────────────────────────────────────────────
PLAYER_DIR = os.path.dirname(os.path.abspath(__file__))
PORT       = 3001
ALLOWED    = {'study_stats.json', 'studied.json', 'recorded.json'}

if len(sys.argv) >= 2:
    PLAYER_DIR = sys.argv[1]
if len(sys.argv) >= 3:
    PORT = int(sys.argv[2])
# ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if self.path != '/save':
            self.send_response(404)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        length = int(self.headers.get('Content-Length', 0))
        body   = self.rfile.read(length)

        try:
            payload  = json.loads(body)
            filename = payload.get('filename', '')
            data     = payload.get('data')

            if filename not in ALLOWED:
                self._respond(400, {'error': f'Filename not allowed: {filename}'})
                return

            dest = os.path.join(PLAYER_DIR, filename)
            with open(dest, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f'[OK] Saved {dest}')
            self._respond(200, {'ok': True, 'path': dest})

        except Exception as e:
            print(f'[ERROR] {e}')
            self._respond(500, {'error': str(e)})

    def _respond(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silenciar log por defecto

if __name__ == '__main__':
    if not os.path.isdir(PLAYER_DIR):
        print(f'Error: "{PLAYER_DIR}" no es una carpeta válida.')
        sys.exit(1)

    print(f'Save server → {PLAYER_DIR}')
    print(f'Escuchando en http://localhost:{PORT}/save')
    print('Ctrl+C para detener\n')

    HTTPServer(('localhost', PORT), Handler).serve_forever()