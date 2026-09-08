#!/usr/bin/env python3
"""
Recipe recommender CLI. Thin wrapper over the SQL functions in db/97_recommender.sql.

    python3 recommend.py members                      list members
    python3 recommend.py for Jeff                     recommend for one member
    python3 recommend.py for Jeff --meal Breakfast    one meal slot only
    python3 recommend.py for Jeff --explain "Tofu"    why one recipe scores what it does
    python3 recommend.py household                    whole household, weakest member first

Talks to Postgres through psql, so no Python packages needed. Uses PG*
environment variables; defaults to a local database called mazimeal_full.
"""
import argparse, json, os, subprocess, sys

DB = os.environ.get("PGDATABASE", "mazimeal_full")


def sql(query, *params):
    """Run a query, return rows as lists. Params are interpolated as literals."""
    q = query
    for p in params:
        q = q.replace("?", "NULL" if p is None else "'" + str(p).replace("'", "''") + "'", 1)
    r = subprocess.run(["psql", "-d", DB, "-At", "-F", "\t", "-c", q],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr.strip())
    return [line.split("\t") for line in r.stdout.strip().splitlines() if line]


def member_id(name):
    rows = sql("select member_id from household_members where lower(member_name)=lower(?) and deleted_at is null", name)
    if not rows:
        sys.exit(f"no member called {name!r}. Try: recommend.py members")
    return rows[0][0]


def cmd_members(_):
    for mid, name, hh, age, sex, goal in sql(
        "select member_id, member_name, household_name, age, sex_at_birth, coalesce(goal,'') "
        "from household_members m join households using(household_id) where m.deleted_at is null order by 2"):
        print(f"{name:10} {age:>3} {sex}  {goal:12} {hh}")


def cmd_for(a):
    mid = member_id(a.member)
    if a.explain:
        rid = sql("select recipe_id from recipes where recipe_name ilike ? and deleted_at is null limit 1",
                  f"%{a.explain}%")
        if not rid:
            sys.exit(f"no recipe matching {a.explain!r}")
        print(f"{'nutrient':14} {'target':>8} {'eaten':>8} {'meal gap':>8} {'serving':>8} closes")
        for n, t, c, g, ps, pct in sql("select * from fn_explain(?, ?, current_date, ?)", mid, rid[0][0], a.meal):
            print(f"{n:14} {float(t):8.1f} {float(c):8.1f} {float(g):8.1f} {float(ps):8.1f} {pct:>5}%")
        return

    rows = sql("select recipe_name, score, top_reasons::text, warnings::text from fn_recommend(?, current_date, ?, ?)",
               mid, a.meal, a.limit)
    blocked = sql("select r.recipe_name, b.reason from fn_blocked_recipes(?) b join recipes r using(recipe_id) "
                  "where ? is null or r.meal_category = ?", mid, a.meal, a.meal)
    for name, score, reasons, warns in rows:
        top = ", ".join(f"{x['nutrient']} {x['closes_pct']}%" for x in json.loads(reasons)[:3])
        flag = "  !! " + "; ".join(json.loads(warns)) if warns != "[]" else ""
        print(f"{float(score):5.1f}  {name:45} {top}{flag}")
    for name, reason in blocked:
        print(f"  --   {name:45} blocked: {reason}")


def cmd_household(a):
    rows = sql("select h.household_id from households h where deleted_at is null limit 1")
    if not rows:
        sys.exit("no household found")
    for name, mn, av, per in sql(
        "select recipe_name, min_score, avg_score, per_member::text from fn_recommend_household(?, current_date, ?, ?)",
        rows[0][0], a.meal, a.limit):
        members = "  ".join(f"{k} {v}" for k, v in json.loads(per).items())
        print(f"{float(mn):5.1f}  {name:45} {members}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("members").set_defaults(fn=cmd_members)
    f = sub.add_parser("for"); f.add_argument("member"); f.add_argument("--explain"); f.add_argument("--limit", type=int, default=10)
    f.add_argument("--meal", choices=["Breakfast", "Lunch", "Dinner", "Snack"]); f.set_defaults(fn=cmd_for)
    h = sub.add_parser("household"); h.add_argument("--limit", type=int, default=10)
    h.add_argument("--meal", choices=["Breakfast", "Lunch", "Dinner", "Snack"]); h.set_defaults(fn=cmd_household)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
