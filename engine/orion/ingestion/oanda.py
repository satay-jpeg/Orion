"""OANDA v20 REST client (practice environment by default).

Only the endpoints ORION needs: daily candles, account summary, instruments, open positions,
market orders with a stop loss attached, and closing positions.
Docs: https://developer.oanda.com/rest-live-v20/introduction/
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests

PRACTICE_URL = "https://api-fxpractice.oanda.com"
NY = ZoneInfo("America/New_York")


class OandaError(RuntimeError):
    pass


class Oanda:
    def __init__(self, token: str | None = None, account_id: str | None = None, environment: str | None = None):
        self.token = token or os.environ.get("OANDA_API_TOKEN")
        self.account_id = account_id or os.environ.get("OANDA_ACCOUNT_ID")
        env = (environment or os.environ.get("OANDA_ENV", "practice")).lower()
        if env != "practice":
            # Deliberate: this project is a paper-trading project. Refuse to talk to a live account.
            raise OandaError("ORION only supports the OANDA practice environment.")
        self.base = PRACTICE_URL
        if not self.token:
            raise OandaError("OANDA_API_TOKEN is not set")
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        })

    # -- low level ---------------------------------------------------------
    def _req(self, method: str, path: str, **kw) -> dict:
        url = f"{self.base}{path}"
        for attempt in range(4):
            r = self.s.request(method, url, timeout=30, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise OandaError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
            return r.json()
        raise OandaError(f"{method} {path} failed after retries")

    # -- market data ---------------------------------------------------------
    def candles_daily(self, instrument: str, start: str = "2010-01-01") -> pd.DataFrame:
        """Mid-price daily candles aligned to 17:00 New York. Pages forward 4,000 candles at a time.

        Returned index is the *close date* in New York (a candle that opens Sunday 17:00 NY
        and closes Monday 17:00 NY is labelled Monday).
        """
        rows = []
        cursor = pd.Timestamp(start, tz="UTC")
        now = pd.Timestamp.now(tz="UTC")
        while cursor < now:
            params = {
                "price": "M",
                "granularity": "D",
                "dailyAlignment": 17,
                "alignmentTimezone": "America/New_York",
                "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "count": 4000,
            }
            data = self._req("GET", f"/v3/instruments/{instrument}/candles", params=params)
            candles = data.get("candles", [])
            if not candles:
                break
            for c in candles:
                if not c.get("complete"):
                    continue  # never use the still-forming candle
                t = pd.Timestamp(c["time"]).tz_convert(NY)
                close_date = (t + timedelta(days=1)).date()
                m = c["mid"]
                rows.append((close_date, float(m["o"]), float(m["h"]), float(m["l"]), float(m["c"]), int(c["volume"])))
            last = pd.Timestamp(candles[-1]["time"])
            if len(candles) < 4000:
                break
            cursor = last + pd.Timedelta(seconds=1)
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).drop_duplicates("date")
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    def prices(self, instruments: list[str]) -> dict[str, dict]:
        data = self._req("GET", f"/v3/accounts/{self.account_id}/pricing",
                         params={"instruments": ",".join(instruments)})
        out = {}
        for p in data.get("prices", []):
            bid = float(p["bids"][0]["price"])
            ask = float(p["asks"][0]["price"])
            out[p["instrument"]] = {"bid": bid, "ask": ask, "mid": (bid + ask) / 2, "tradeable": p.get("tradeable", True)}
        return out

    # -- account -------------------------------------------------------------
    def summary(self) -> dict:
        return self._req("GET", f"/v3/accounts/{self.account_id}/summary")["account"]

    def instruments(self, symbols: list[str]) -> dict[str, dict]:
        data = self._req("GET", f"/v3/accounts/{self.account_id}/instruments",
                         params={"instruments": ",".join(symbols)})
        return {i["name"]: i for i in data.get("instruments", [])}

    def open_positions(self) -> dict[str, dict]:
        data = self._req("GET", f"/v3/accounts/{self.account_id}/openPositions")
        out = {}
        for p in data.get("positions", []):
            long_u = float(p["long"]["units"])
            short_u = float(p["short"]["units"])
            units = long_u + short_u  # short units are negative
            side = p["long"] if long_u != 0 else p["short"]
            out[p["instrument"]] = {
                "units": units,
                "avg_price": float(side.get("averagePrice", 0) or 0),
                "unrealized_pl": float(p.get("unrealizedPL", 0)),
                "margin_used": float(p.get("marginUsed", 0)),
                "trade_ids": side.get("tradeIDs", []),
            }
        return out

    def open_trades(self) -> list[dict]:
        return self._req("GET", f"/v3/accounts/{self.account_id}/openTrades").get("trades", [])

    # -- orders --------------------------------------------------------------
    def market_order(self, instrument: str, units: float, stop_price: str | None, client_tag: str) -> dict:
        order = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "clientExtensions": {"tag": "orion", "comment": client_tag[:128]},
        }
        if stop_price is not None:
            order["stopLossOnFill"] = {"price": stop_price, "timeInForce": "GTC"}
        return self._req("POST", f"/v3/accounts/{self.account_id}/orders", json={"order": order})

    def close_position(self, instrument: str, units: float) -> dict:
        body = {"longUnits": "ALL"} if units > 0 else {"shortUnits": "ALL"}
        return self._req("PUT", f"/v3/accounts/{self.account_id}/positions/{instrument}/close", json=body)

    def set_trade_stop(self, trade_id: str, stop_price: str) -> dict:
        return self._req("PUT", f"/v3/accounts/{self.account_id}/trades/{trade_id}/orders",
                         json={"stopLoss": {"price": stop_price, "timeInForce": "GTC"}})


def fetch_all_prices(symbols: list[str], start: str, log=print) -> dict[str, pd.DataFrame]:
    """Instruments your OANDA division does not offer are skipped (and logged) rather than failing the run."""
    client = Oanda()
    out = {}
    for s in symbols:
        try:
            out[s] = client.candles_daily(s, start)
            log(f"  price {s:<8} {len(out[s]):>5} bars  last={out[s].index[-1].date()}")
        except OandaError as e:
            log(f"  price {s:<8} SKIP: {str(e)[:160]}")
    if len(out) < 3:
        raise OandaError("fewer than 3 instruments available from OANDA; check token / account")
    return out


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
