#!/usr/bin/env python3
import http.server
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

Handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
    *args, directory=str(ROOT), **kwargs
)

socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("127.0.0.1", 8000), Handler) as httpd:
    print("Serving on http://localhost:8000/site/")
    httpd.serve_forever()
