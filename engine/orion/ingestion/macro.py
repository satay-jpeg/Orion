"""Macro / rates data from official, free sources.

Each fetcher returns a pd.Series indexed by observation date (DatetimeIndex, naive) with float values.
Parsers are deliberately defensive because official CSV layouts change occasionally; if a layout
changes the fetcher raises with a clear message rather than silently returning garbage.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import requests

from ..config import SERIES, Series

UA = {"User-Agent": "ORION research pipeline (personal, non-commercial; github.com)"}


class SourceError(RuntimeError):
    pass


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=60, **kw)
    if r.status_code != 200:
        raise SourceError(f"GET {url} -> {r.status_code}")
    return r


def _clean(s: pd.Series, name: str) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.name = name
    if s.empty:
        raise SourceError(f"{name}: no observations parsed")
    return s


# ---------------------------------------------------------------------------
def fred(series_id: str, start: str) -> pd.Series:
    """FRED graph CSV endpoint (no key needed). If FRED_API_KEY is set, uses the official API instead."""
    key = os.environ.get("FRED_API_KEY")
    if key:
        r = _get("https://api.stlouisfed.org/fred/series/observations",
                 params={"series_id": series_id, "api_key": key, "file_type": "json", "observation_start": start})
        obs = r.json()["observations"]
        s = pd.Series({o["date"]: o["value"] for o in obs})
        return _clean(s.replace(".", None), series_id)
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id, "cosd": start})
    df = pd.read_csv(io.StringIO(r.text))
    date_col = df.columns[0]  # 'observation_date' (current) or 'DATE' (older)
    val_col = series_id if series_id in df.columns else df.columns[1]
    s = df.set_index(date_col)[val_col].replace(".", None)
    return _clean(s, series_id)


def mof_japan(tenor: str, start: str) -> pd.Series:
    """Japan MoF JGB benchmark yields. Historical file (1974-) + current-month file, western dates."""
    frames = []
    for url in ("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
                "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"):
        text = _get(url).content.decode("utf-8", errors="replace")
        lines = text.splitlines()
        hdr = next((i for i, l in enumerate(lines) if l.strip().lower().startswith("date")), None)
        if hdr is None:
            raise SourceError(f"MoF CSV layout changed: no 'Date' header in {url}")
        df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
        df.columns = [c.strip() for c in df.columns]
        if tenor not in df.columns:
            raise SourceError(f"MoF CSV has no {tenor} column; columns={list(df.columns)[:8]}")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        frames.append(df.dropna(subset=["Date"]).set_index("Date")[tenor].replace("-", None))
    s = pd.concat(frames)
    s = _clean(s, f"JGB{tenor}")
    return s[s.index >= pd.Timestamp(start)]


def ecb(key: str, start: str) -> pd.Series:
    flow, series_key = key.split("/", 1)
    r = _get(f"https://data-api.ecb.europa.eu/service/data/{flow}/{series_key}",
             params={"startPeriod": start, "format": "csvdata"})
    df = pd.read_csv(io.StringIO(r.text))
    if not {"TIME_PERIOD", "OBS_VALUE"} <= set(df.columns):
        raise SourceError("ECB CSV layout changed")
    return _clean(df.set_index("TIME_PERIOD")["OBS_VALUE"], key)


def rba(series_code: str, start: str) -> pd.Series:
    """RBA statistical table F2 (daily government bond yields). Finds the 'Series ID' row for the header."""
    text = _get("https://www.rba.gov.au/statistics/tables/csv/f2-data.csv").content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    sid = next((i for i, l in enumerate(lines) if l.lower().startswith("series id")), None)
    if sid is None:
        raise SourceError("RBA F2 layout changed: no 'Series ID' row")
    df = pd.read_csv(io.StringIO("\n".join(lines[sid:])))
    df = df.rename(columns={df.columns[0]: "date"})
    if series_code not in df.columns:
        raise SourceError(f"RBA F2 has no {series_code}")
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce", format="mixed")
    s = _clean(df.dropna(subset=["date"]).set_index("date")[series_code], series_code)
    return s[s.index >= pd.Timestamp(start)]


def boc(series_code: str, start: str) -> pd.Series:
    r = _get(f"https://www.bankofcanada.ca/valet/observations/{series_code}/json", params={"start_date": start})
    obs = r.json().get("observations", [])
    s = pd.Series({o["d"]: (o.get(series_code) or {}).get("v") for o in obs})
    return _clean(s, series_code)


def eia(series_code: str, start: str) -> pd.Series:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise SourceError("EIA_API_KEY not set (optional source skipped)")
    route = "petroleum/pri/fut" if series_code.startswith("RCL") else "petroleum/stoc/wstk"
    freq = "daily" if series_code.startswith("RCL") else "weekly"
    rows, offset = [], 0
    while True:
        r = _get(f"https://api.eia.gov/v2/{route}/data/", params={
            "api_key": key, "frequency": freq, "data[0]": "value", "facets[series][]": series_code,
            "start": start, "sort[0][column]": "period", "sort[0][direction]": "asc",
            "offset": offset, "length": 5000})
        data = r.json().get("response", {}).get("data", [])
        rows += data
        if len(data) < 5000:
            break
        offset += 5000
    s = pd.Series({d["period"]: d["value"] for d in rows})
    return _clean(s, series_code)


FETCHERS = {"fred": fred, "mof_japan": mof_japan, "ecb": ecb, "rba": rba, "boc": boc, "eia": eia}


def fetch_series(spec: Series, start: str) -> pd.Series:
    s = FETCHERS[spec.provider](spec.source_key, start)
    s.name = spec.id
    return s


def fetch_all_macro(start: str, log=print) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for sid, spec in SERIES.items():
        try:
            out[sid] = fetch_series(spec, start)
            log(f"  macro {sid:<16} {len(out[sid]):>6} obs  last={out[sid].index[-1].date()}")
        except Exception as e:  # noqa: BLE001 - we want to continue and report
            # Optional sources degrade gracefully: dependent components drop out and the composite
            # renormalises (subject to the minimum-completeness rule).
            level = "skip" if spec.optional else "FAIL"
            log(f"  macro {sid:<16} {level}: {e}")
            if not spec.optional:
                raise
    return out


def point_in_time(s: pd.Series, lag_days: int) -> pd.DataFrame:
    """Attach the date each observation became usable (observation date + release lag)."""
    df = s.to_frame("value")
    df["available_on"] = df.index + pd.Timedelta(days=lag_days)
    return df
