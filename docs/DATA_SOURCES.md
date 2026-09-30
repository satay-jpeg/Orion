# Data sources

Selection rule: official or primary sources with free, documented access and terms that allow this kind of use. Proprietary benchmarks are replaced with public proxies, and each substitution is stated.

| ID | Series | Provider / access | Freq. | Lag used | Licence / terms | Notes |
|---|---|---|---|---|---|---|
| prices | FX + CFD mid candles, 17:00 NY | OANDA v20 API (practice) | daily | 0 (complete candles only) | OANDA account terms: personal use | **Raw levels stay admin-only.** Public pages show % changes, percentiles and a rebased index |
| US2Y, US10Y | Treasury constant maturity | FRED `DGS2`, `DGS10` (Fed H.15) | daily | 1d | Public domain | |
| US10Y_REAL | 10Y TIPS yield | FRED `DFII10` | daily | 1d | Public domain | |
| US10Y_BE | 10Y breakeven | FRED `T10YIE` | daily | 1d | FRED, cite St. Louis Fed | |
| VIX | CBOE VIX close | FRED `VIXCLS` | daily | 1d | © CBOE, redistributed by FRED; attribute CBOE | Third-party copyrighted |
| USD_BROAD | Nominal broad dollar index | FRED `DTWEXBGS` (Fed H.10) | daily | 1d | Public domain | Replaces ICE DXY (proprietary) |
| CFNAI_MA3 | Chicago Fed National Activity Index, 3m | FRED `CFNAIMA3` | monthly | 55d | Cite Chicago Fed | Replaces ISM / S&P Global PMIs (proprietary) |
| US_CPI | CPI-U SA | FRED `CPIAUCSL` (BLS) | monthly | 45d | Public domain | |
| JP2Y | JGB 2Y | Ministry of Finance Japan CSV | daily | 0d | Govt of Japan Standard Terms of Use (CC BY 4.0 compatible); cite MoF | Tokyo close is before NY close |
| EU2Y | Euro area AAA curve, 2Y spot | ECB Data Portal `YC` | daily | 1d | Reuse allowed with attribution | |
| AU2Y | Australian govt 2Y | RBA table F2 CSV | daily | 1d | CC BY 4.0; cite RBA | |
| CA2Y | GoC 2Y benchmark | Bank of Canada Valet API | daily | 1d | Free reuse with attribution | |
| WTI_C1/C2/C4 | NYMEX WTI futures 1, 2, 4 | EIA API v2 | daily | 1d | Public domain (US govt) | Optional. Proxy for oil curve (ICE Brent curve is proprietary) |
| US_CRUDE_STOCKS | Commercial crude ex-SPR | EIA API v2 `WCESTUS1` | weekly | 5d | Public domain | Optional |

## Deliberately not used

* **Yahoo Finance / yfinance:** no licence for this kind of reuse.
* **S&P Global / ISM PMIs, LME copper stocks, ICE Brent curve, ICE DXY:** proprietary. Proxies are listed above.
* **Scraped news:** the "What changed?" feed is built from computed numbers only.

## Point-in-time handling

Every value is stored with `available_on = observation date + lag`, and the panel is built with an as-of join on `available_on`. Values older than 10 days (daily), 21 days (weekly) or 100 days (monthly) count as missing rather than being carried forward indefinitely.

**Known gap:** FRED returns the latest revised vintage. CPI and CFNAI get revised, so history is slightly cleaner than what a trader saw at the time. The fix is ALFRED vintage data, which is on the roadmap.

## Time zones

* Prices: the daily bar closes at 17:00 America/New_York and is labelled with the NY date of the close.
* The pipeline runs at 23:20 UTC, after the NY close and the energy CFD daily break.
* Macro dates are observation dates in the source's local convention. The 1-day lag covers publication timing.
