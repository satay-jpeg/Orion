"""Local RLS check against a throwaway Postgres (pip install pgserver psycopg2-binary).

Applies the migration to a minimal Supabase-like shim and prints what anon, a non-admin user and the
admin can read and write. Expected: anon/other user see only public tables and cannot write anything;
admin reads private tables and can only update agent_config within the CHECK bounds.
"""
import os, shutil, tempfile, uuid
import pgserver, psycopg2
d = tempfile.mkdtemp(prefix="orion-rls-")
MIGRATION = os.path.join(os.path.dirname(__file__), "..", "migrations", "0001_init.sql")
srv=pgserver.get_server(d, cleanup_mode="stop")
conn=psycopg2.connect(srv.get_uri()); conn.autocommit=True; c=conn.cursor()
# Minimal Supabase shim
c.execute("""
create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
create schema auth; grant usage on schema auth to anon, authenticated;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;
""")
c.execute(open(MIGRATION).read())
c.execute(open(MIGRATION).read())  # idempotent
admin, other = uuid.uuid4(), uuid.uuid4()
c.execute("insert into auth.users values (%s),(%s)", (str(admin), str(other)))
c.execute("insert into public.admins values (%s)", (str(admin),))
c.execute("insert into instruments values ('USD_JPY','USD/JPY','fx','USD','JPY','{}')")
c.execute("insert into prices_daily values ('USD_JPY','2026-01-01',1,1,1,150,'oanda')")
c.execute("insert into signals values ('2026-01-01','USD_JPY',1.2,'Positive','{}',1)")
c.execute("insert into equity_snapshots(date,nav) values ('2026-01-01',100000)")
c.execute("insert into performance_public values ('2026-01-01',100,0)")
c.execute("insert into journal(date,action,summary) values ('2026-01-01','hold','x')")

def as_role(role, sub=None):
    c.execute("reset role"); c.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(sub) if sub else '',))
    c.execute(f"set role {role}")

def q(sql):
    try:
        c.execute(sql); return c.fetchall() if c.description else "ok"
    except Exception as e:
        conn.rollback() if not conn.autocommit else None
        return "ERR " + str(e).split("\n")[0][:70]

results = {}
for who, role, sub in [("anon","anon",None),("other user","authenticated",other),("admin","authenticated",admin)]:
    as_role(role, sub)
    results[who] = {
      "signals": q("select count(*) from signals"),
      "perf_public": q("select count(*) from performance_public"),
      "prices_daily": q("select count(*) from prices_daily"),
      "equity": q("select count(*) from equity_snapshots"),
      "journal": q("select count(*) from journal"),
      "insert signal": q("insert into signals values ('2026-01-02','USD_JPY',1,'x','{}',1)"),
      "update cfg trading": q("update agent_config set trading_enabled=true where id=1 returning trading_enabled"),
      "update cfg bad risk": q("update agent_config set risk_per_trade=0.5 where id=1"),
      "insert admin": q(f"insert into admins values ('{other}')"),
      "delete journal": q("delete from journal returning id"),
    }
c.execute("reset role")
for k,v in results.items():
    print("==",k)
    for a,b in v.items(): print(f"   {a:<22} {b}")
srv.cleanup()
