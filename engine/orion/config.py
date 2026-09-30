"""Static configuration for ORION.

Everything that is an *assumption* (costs, lags, thresholds, weights) lives here so it can be
reviewed in one place and cited in the methodology document.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Instruments (OANDA v20 symbols). Prices come from OANDA mid candles, daily, aligned to 17:00 New York.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    asset_class: str  # fx | commodity
    base: str
    quote: str
    themes: tuple[str, ...]
    spread_bps: float  # assumed typical bid/ask spread, round trip is 1x spread
    slippage_bps: float  # assumed per-side slippage
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


INSTRUMENTS: dict[str, Instrument] = {
    i.symbol: i
    for i in [
        Instrument("USD_JPY", "USD/JPY", "fx", "USD", "JPY",
                   ("US-Japan rate differential", "carry", "risk sentiment", "BoJ"), 1.2, 0.5,
                   ("US CPI", "FOMC communication", "BoJ policy meetings", "US Treasury auctions"),
                   ("Sharp fall in US yields", "BoJ policy surprise", "MoF intervention", "Broad risk-off / carry unwind")),
        Instrument("EUR_USD", "EUR/USD", "fx", "EUR", "USD",
                   ("US-Euro area rate differential", "ECB vs Fed", "growth"), 1.0, 0.5,
                   ("ECB meetings", "FOMC", "Euro area PMI and HICP", "US payrolls"),
                   ("Diverging growth surprises", "Energy price shock", "Political risk in the euro area")),
        Instrument("AUD_USD", "AUD/USD", "fx", "AUD", "USD",
                   ("China / global growth", "industrial metals", "RBA vs Fed", "risk sentiment"), 1.5, 0.5,
                   ("RBA meetings", "China activity data", "Australian CPI", "US payrolls"),
                   ("China growth disappointment", "Risk-off episode", "Commodity price reversal")),
        Instrument("USD_CAD", "USD/CAD", "fx", "USD", "CAD",
                   ("Oil prices", "US-Canada rate differential", "risk sentiment"), 1.8, 0.5,
                   ("BoC meetings", "Canadian employment", "OPEC+ decisions", "US CPI"),
                   ("Oil supply shock", "BoC policy surprise", "US-Canada trade policy")),
        Instrument("XAU_USD", "Gold", "commodity", "XAU", "USD",
                   ("US real yields", "USD", "inflation expectations", "safe-haven demand"), 2.5, 1.0,
                   ("US CPI", "FOMC", "US real yield moves", "Geopolitical events"),
                   ("Rising real yields", "Strong USD", "Positioning unwind")),
        Instrument("BCO_USD", "Brent crude", "commodity", "BCO", "USD",
                   ("inventories", "term structure", "global activity", "USD"), 4.0, 1.5,
                   ("OPEC+ meetings", "EIA weekly inventories", "China activity data"),
                   ("OPEC+ supply increase", "Demand slowdown", "Inventory builds")),
        Instrument("XCU_USD", "Copper", "commodity", "XCU", "USD",
                   ("China / global manufacturing", "USD", "inventories"), 8.0, 2.0,
                   ("China PMI and credit data", "US manufacturing data", "LME/COMEX stock reports"),
                   ("China property weakness", "Strong USD", "Global manufacturing slowdown")),
    ]
}

# ---------------------------------------------------------------------------
# Macro series. `lag_days` is the release lag assumption used to build point-in-time data:
# a value observed on date d is only usable from d + lag_days (calendar days) onwards.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Series:
    id: str
    name: str
    provider: str
    source_key: str  # provider-specific id
    frequency: str
    units: str
    lag_days: int
    url: str
    license: str
    optional: bool = False
    notes: str = ""


FRED_TERMS = ("FRED terms of use: data may be used with attribution to the original source; "
              "some series are third-party copyrighted (noted per series).")

SERIES: dict[str, Series] = {
    s.id: s
    for s in [
        Series("US2Y", "US Treasury 2Y constant maturity yield", "fred", "DGS2", "daily", "%", 1,
               "https://fred.stlouisfed.org/series/DGS2", "Public domain (Federal Reserve H.15), via FRED"),
        Series("US10Y", "US Treasury 10Y constant maturity yield", "fred", "DGS10", "daily", "%", 1,
               "https://fred.stlouisfed.org/series/DGS10", "Public domain (Federal Reserve H.15), via FRED"),
        Series("US10Y_REAL", "US 10Y TIPS real yield", "fred", "DFII10", "daily", "%", 1,
               "https://fred.stlouisfed.org/series/DFII10", "Public domain (Federal Reserve H.15), via FRED"),
        Series("US10Y_BE", "US 10Y breakeven inflation", "fred", "T10YIE", "daily", "%", 1,
               "https://fred.stlouisfed.org/series/T10YIE", "Federal Reserve Bank of St. Louis, via FRED (cite source)"),
        Series("VIX", "CBOE Volatility Index close", "fred", "VIXCLS", "daily", "index", 1,
               "https://fred.stlouisfed.org/series/VIXCLS",
               "Copyright Chicago Board Options Exchange; redistributed by FRED with permission. Cite CBOE.",
               notes="Third-party copyrighted series; shown with attribution only."),
        Series("USD_BROAD", "Nominal Broad US Dollar Index", "fred", "DTWEXBGS", "daily", "index", 1,
               "https://fred.stlouisfed.org/series/DTWEXBGS", "Public domain (Federal Reserve H.10), via FRED",
               notes="Used instead of ICE DXY, which is proprietary."),
        Series("CFNAI_MA3", "Chicago Fed National Activity Index, 3-month average", "fred", "CFNAIMA3", "monthly",
               "index", 55, "https://fred.stlouisfed.org/series/CFNAIMA3",
               "Federal Reserve Bank of Chicago, via FRED (cite source)",
               notes="Growth proxy. Used instead of ISM/S&P Global PMIs, which are proprietary."),
        Series("US_CPI", "US CPI, all urban consumers (SA)", "fred", "CPIAUCSL", "monthly", "index", 45,
               "https://fred.stlouisfed.org/series/CPIAUCSL", "Public domain (BLS), via FRED"),
        Series("JP2Y", "Japan Government Bond 2Y yield", "mof_japan", "2Y", "daily", "%", 0,
               "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm",
               "Ministry of Finance Japan. Government of Japan Standard Terms of Use (CC BY 4.0 compatible); cite MoF.", optional=True),
        Series("EU2Y", "Euro area AAA govt yield curve, 2Y spot", "ecb", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",
               "daily", "%", 1, "https://data.ecb.europa.eu/data/datasets/YC",
               "ECB Data Portal; reuse permitted with source attribution.", optional=True),
        Series("AU2Y", "Australian Government 2Y bond yield", "rba", "FCMYGBAG2", "daily", "%", 1,
               "https://www.rba.gov.au/statistics/tables/#interest-rates",
               "Reserve Bank of Australia, CC BY 4.0; cite RBA.", optional=True),
        Series("CA2Y", "Government of Canada 2Y benchmark bond yield", "boc", "BD.CDN.2YR.DQ.YLD", "daily", "%", 1,
               "https://www.bankofcanada.ca/rates/interest-rates/canadian-bonds/",
               "Bank of Canada; free reuse with attribution per BoC terms.", optional=True),
        Series("WTI_C1", "NYMEX WTI futures, contract 1", "eia", "RCLC1", "daily", "USD/bbl", 1,
               "https://www.eia.gov/dnav/pet/pet_pri_fut_s1_d.htm", "U.S. EIA, public domain",
               optional=True, notes="Needs free EIA API key. Proxy for oil curve shape (ICE Brent curve is proprietary)."),
        Series("WTI_C2", "NYMEX WTI futures, contract 2", "eia", "RCLC2", "daily", "USD/bbl", 1,
               "https://www.eia.gov/dnav/pet/pet_pri_fut_s1_d.htm", "U.S. EIA, public domain", optional=True),
        Series("WTI_C4", "NYMEX WTI futures, contract 4", "eia", "RCLC4", "daily", "USD/bbl", 1,
               "https://www.eia.gov/dnav/pet/pet_pri_fut_s1_d.htm", "U.S. EIA, public domain", optional=True),
        Series("US_CRUDE_STOCKS", "US commercial crude inventories ex-SPR", "eia", "WCESTUS1", "weekly",
               "thousand bbl", 5, "https://www.eia.gov/petroleum/supply/weekly/", "U.S. EIA, public domain",
               optional=True, notes="Week ending Friday, released the following Wednesday."),
    ]
}

# ---------------------------------------------------------------------------
# Signal engine parameters
# ---------------------------------------------------------------------------
Z_WINDOW = 252          # 1 trading year: long enough to be stable, short enough to adapt to regime shifts
Z_WINDOW_LONG = 756     # 3 years for slow-moving levels (carry)
Z_MIN_PERIODS = 126
CHANGE_WINDOW = 20      # ~1 month change for rate differentials / macro impulses
Z_CLIP = 3.0
NEUTRAL_BAND = 0.25     # |composite| below this is labelled Neutral
MIN_COMPLETENESS = 0.6  # share of component weight that must have data for a composite to be published


@dataclass
class StrategyParams:
    entry_threshold: float = 0.5
    exit_threshold: float = 0.0
    stop_atr_multiple: float = 2.5
    atr_window: int = 20
    risk_per_trade: float = 0.005
    max_position_weight: float = 1.0      # |notional| / NAV per instrument
    max_gross_leverage: float = 3.0
    financing_markup_annual: float = 0.015  # broker markup on financing, assumption
    min_holding_days: int = 1
    grid: dict = field(default_factory=lambda: {
        "entry_threshold": [0.25, 0.5, 0.75],
        "stop_atr_multiple": [2.0, 3.0],
    })


START_DATE = "2010-01-01"
HOLDOUT_DAYS = 365
MIN_TRAIN_YEARS = 4
