"""A tiny stand-in for Supabase (REST + Auth) that serves demo/data/*.jsonl on http://127.0.0.1:54321.

Standard library only. For the local demo ONLY: any email/password signs in as admin, and nothing is
protected. The real security (Row Level Security) lives in supabase/migrations and is not simulated here.
"""
import base64
import glob
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
if not glob.glob(os.path.join(DATA, "*.jsonl")):
    raise SystemExit("No demo data found. Run: python demo/generate_demo_data.py")

T = {}
for f in glob.glob(os.path.join(DATA, "*.jsonl")):
    name = os.path.basename(f)[:-6]
    if name.endswith("__updates"):
        continue
    with open(f) as fh:
        T[name] = [json.loads(l) for l in fh if l.strip()]
for r in T.get("backtest_runs", []):
    r.setdefault("id", "demo")
    r.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ"))
for r in T.get("backtest_series", []) + T.get("backtest_trades", []):
    r["run_id"] = "demo"
for i, r in enumerate(T.get("journal", [])):
    r["id"] = i + 1
for i, r in enumerate(T.get("orders", [])):
    r["id"] = i + 1

USER = {"id": "00000000-0000-0000-0000-000000000001", "aud": "authenticated", "role": "authenticated",
        "email": "demo@orion.local", "app_metadata": {"provider": "email"}, "user_metadata": {},
        "created_at": "2026-01-01T00:00:00Z"}


def b64u(o):
    return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")


def session():
    exp = int(time.time()) + 3600
    jwt = b64u({"alg": "HS256", "typ": "JWT"}) + "." + b64u({"sub": USER["id"], "exp": exp, "role": "authenticated",
                                                            "email": USER["email"], "aud": "authenticated"}) + ".demo"
    return {"access_token": jwt, "token_type": "bearer", "expires_in": 3600, "expires_at": exp,
            "refresh_token": "demo-refresh", "user": USER}


def match(v, op, x):
    if v is None:
        return False
    if isinstance(v, bool):
        v = str(v).lower()
    v = str(v)
    return {"eq": v == x, "gte": v >= x, "lte": v <= x, "gt": v > x, "lt": v < x,
            "in": v in x.strip("()").split(",")}.get(op, True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def reply(self, code, body=None):
        b = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.reply(204)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/auth/v1/user":
            return self.reply(200, USER)
        m = re.match(r"/rest/v1/(\w+)", u.path)
        if not m:
            return self.reply(404, {"message": "not found"})
        rows = list(T.get(m.group(1), []))
        order, limit, offset = None, None, 0
        for k, v in parse_qsl(u.query):
            if k == "select":
                continue
            if k == "order":
                order = v
            elif k == "limit":
                limit = int(v)
            elif k == "offset":
                offset = int(v)
            else:
                op, _, x = v.partition(".")
                rows = [r for r in rows if match(r.get(k), op, x)]
        if order:
            col, _, d = order.split(",")[0].partition(".")
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=d.startswith("desc"))
        rows = rows[offset: offset + limit if limit else None]
        if "vnd.pgrst.object" in self.headers.get("Accept", ""):
            return self.reply(200, rows[0] if rows else {})
        self.reply(200, rows)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        if u.path == "/auth/v1/token":
            return self.reply(200, session())
        if u.path == "/auth/v1/logout":
            return self.reply(204)
        if u.path.endswith("/rpc/is_admin"):
            return self.reply(200, True)
        self.reply(201, [])

    def do_PATCH(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if self.path.startswith("/rest/v1/agent_config") and T.get("agent_config"):
            T["agent_config"][0].update(body)
        self.reply(204)


if __name__ == "__main__":
    print("Mock Supabase (demo data) on http://127.0.0.1:54321  -- Ctrl+C to stop")
    ThreadingHTTPServer(("127.0.0.1", 54321), Handler).serve_forever()
