# Local demo

See every page of ORION on your own computer with **synthetic** data. You don't need any accounts.

**Windows:** double-click `run_demo.bat`.
**macOS / Linux:** `./demo/run_demo.sh`

You need [Python 3.10+](https://www.python.org/downloads/) (on Windows, tick "Add python.exe to PATH") and [Node.js 20 LTS](https://nodejs.org/).

What happens:
1. `generate_demo_data.py` runs the real ORION pipeline (signals, regime, research, walk-forward backtest, agent) on simulated markets and writes `demo/data/*.jsonl`.
2. `mock_supabase.py` serves those files on port 54321, standing in for Supabase.
3. The website starts at http://localhost:3000. A banner marks every page as demo data.

Admin view: go to http://localhost:3000/login and enter **any** email and password.

To stop, close the two windows, or press Ctrl+C in each.

The mock has no security. It exists only to show the UI. The real access control is the Row Level Security in `supabase/migrations`, checked by `supabase/tests/rls_check.py`.
