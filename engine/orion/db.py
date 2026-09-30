"""Minimal Supabase (PostgREST) writer using the service-role key.

The service-role key bypasses RLS, so it is only ever read from the environment of the pipeline
(GitHub Actions secret). It must never be exposed to the browser.

If SUPABASE_URL is not set, writes go to ./out/<table>.jsonl instead (dry run / local development).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path

import numpy as np
import requests


def _clean(v):
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10] if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


class DB:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.local = not (self.url and self.key)
        self.out = Path(os.environ.get("ORION_OUT_DIR", "out"))
        if self.local:
            self.out.mkdir(parents=True, exist_ok=True)
        self.s = requests.Session()
        self.s.headers.update({"apikey": self.key, "Authorization": f"Bearer {self.key}",
                               "Content-Type": "application/json"})

    def upsert(self, table: str, rows: list[dict], on_conflict: str | None = None, chunk: int = 500) -> int:
        rows = [_clean(r) for r in rows]
        if not rows:
            return 0
        # PostgREST bulk inserts require identical keys in every object
        keys = sorted(set().union(*[r.keys() for r in rows]))
        rows = [{k: r.get(k) for k in keys} for r in rows]
        if self.local:
            with open(self.out / f"{table}.jsonl", "a") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            return len(rows)
        params = {"on_conflict": on_conflict} if on_conflict else {}
        headers = {"Prefer": "resolution=merge-duplicates,return=minimal"}
        for i in range(0, len(rows), chunk):
            r = self.s.post(f"{self.url}/rest/v1/{table}", params=params, headers=headers,
                            data=json.dumps(rows[i:i + chunk]), timeout=60)
            if r.status_code >= 300:
                raise RuntimeError(f"upsert {table} -> {r.status_code}: {r.text[:400]}")
        return len(rows)

    def insert_returning(self, table: str, row: dict) -> dict:
        row = _clean(row)
        if self.local:
            self.upsert(table, [row])
            return row
        r = self.s.post(f"{self.url}/rest/v1/{table}", headers={"Prefer": "return=representation"},
                        data=json.dumps(row), timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"insert {table} -> {r.status_code}: {r.text[:400]}")
        return r.json()[0]

    def update(self, table: str, match: dict, values: dict) -> None:
        if self.local:
            self.upsert(table + "__updates", [{"match": match, "values": values}])
            return
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = self.s.patch(f"{self.url}/rest/v1/{table}", params=params, data=json.dumps(_clean(values)), timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"update {table} -> {r.status_code}: {r.text[:400]}")

    def select(self, table: str, params: dict | None = None) -> list[dict]:
        if self.local:
            return []
        r = self.s.get(f"{self.url}/rest/v1/{table}", params=params or {"select": "*"}, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"select {table} -> {r.status_code}: {r.text[:400]}")
        return r.json()
