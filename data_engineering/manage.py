#!/usr/bin/env python3
"""Reproducible local import and read-only data handoff for the current team schema."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'api'))
from recipe_facts import build_recipe_facts
from detect_rules import detect_rules_from_facts
from evaluate_rules import evaluate_recipe_rules
from app.seed_list import external_ids

MIGRATION = 'schema/migrations/005_data_readiness.sql'
BASE = [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'schema').glob('[0-9][0-9]_*.sql'))]
SEEDS = [f'schema/seed/{name}.sql' for name in (
    'foodcom_400','usda_nutrition','ingredient_sources','ingredient_grams',
    'business_rules','rule_codes','ingredient_rule_tags')]


def encode(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def rows(conn, query, params=()):
    cur = conn.execute(query, params)
    return [dict(zip([c.name for c in cur.description], row)) for row in cur.fetchall()]


def connection_settings():
    # No implicit use of a production connection. Explicit environment wins.
    if os.environ.get('MAZIMEAL_DSN'):
        return os.environ['MAZIMEAL_DSN']
    env_file = ROOT / 'data_engineering/.env'
    if env_file.exists():
        settings = dict(line.split('=', 1) for line in env_file.read_text().splitlines()
                        if '=' in line and not line.startswith('#'))
        if settings.get('MAZIMEAL_DSN'):
            return settings['MAZIMEAL_DSN']
    raise ValueError('Run configure for local development or explicitly set MAZIMEAL_DSN.')


def configure():
    target = ROOT / 'data_engineering/.env'
    secret = secrets.token_hex(24)
    # Exclusive creation preserves an existing password/connection file.
    with target.open('x') as handle:
        os.chmod(target, 0o600)
        handle.write(f'MAZIMEAL_DEV_PASSWORD={secret}\n')
        handle.write(f'MAZIMEAL_DSN=postgresql://mazimeal_integration:{secret}@127.0.0.1:5434/mazimeal_integration\n')
    return {'configured': True, 'connection': 'Local PostgreSQL on port 5434; credentials remain in ignored .env'}


def execute_sql_file(conn, relative):
    # Caller owns the transaction; strip only top-level seed transaction markers.
    statement = re.sub(r'^(?:BEGIN|COMMIT);\s*$', '', (ROOT / relative).read_text(), flags=re.M)
    conn.execute(statement, prepare=False)


def bootstrap(conn):
    if conn.info.host not in ('localhost', '127.0.0.1', '::1') or conn.info.dbname != 'mazimeal_integration':
        raise ValueError('bootstrap is restricted to local mazimeal_integration, never a shared database.')
    if conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:
        raise ValueError('bootstrap requires an EMPTY database. Existing data was not changed.')
    with conn.transaction():
        for path in BASE + SEEDS + [MIGRATION]:
            execute_sql_file(conn, path)
        checks = rows(conn, 'SELECT * FROM validate_week1()')
        if any(row['status'] == 'FAIL' for row in checks):
            raise ValueError('Seed validation failed; the entire bootstrap was rolled back.')
        paths = BASE + SEEDS + [MIGRATION, 'docs/MaziMeal_50_Recipes_Culture_Optimized.csv']
        manifest = {'basis': 'Current repository schema/ and committed seeds',
            'team_baseline_commit': 'e67a499b7cd3019cc2720155d4f1183362bc4008',
            'sample_csv_imported': False, 'user_data_imported': False,
            'sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}
        conn.execute('INSERT INTO de_dataset_releases (release_id,manifest) VALUES (%s,%s)',
                     ('team-seed-2026-11-05', Jsonb(manifest)))
    return {'bootstrapped': True, 'validation': checks, 'review_status': 'pending; estimates were not approved'}


def recipe_packet(conn, recipe_id):
    facts = build_recipe_facts(conn, recipe_id)
    return {'contract_version': '2.0', 'facts': facts.as_dict(),
        'candidate_rules': [c.as_dict() for c in detect_rules_from_facts(conn, facts)],
        'evaluations': [e.as_dict() for e in evaluate_recipe_rules(conn, recipe_id)],
        'data_readiness': rows(conn, 'SELECT * FROM de_recipe_readiness WHERE recipe_id=%s', (recipe_id,))[0],
        'ingredient_details': rows(conn, 'SELECT * FROM de_ingredient_line_readiness WHERE recipe_id=%s ORDER BY ingredient_name', (recipe_id,)),
        'nutrient_readiness': rows(conn, 'SELECT * FROM de_recipe_nutrient_readiness WHERE recipe_id=%s ORDER BY nutrient_id', (recipe_id,)),
        'interpretation': 'Candidates are not approved changes. Published nutrition stays separate. Only ready nutrient rows expose verified_per_serving. This does not enforce user allergies or preferences.'}


def write_json(path, value):
    path.write_text(json.dumps(value, default=encode, indent=2) + '\n')


def write_csv(path, values):
    with path.open('w', newline='') as handle:
        if values:
            writer = csv.DictWriter(handle, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)


def report(conn, output, scope='seed'):
    ids = external_ids()
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('The shared seed CSV must contain distinct external IDs.')
    where = 'WHERE external_source_id = ANY(%s)' if scope == 'seed' else ''
    params = (ids,) if scope == 'seed' else ()
    readiness = rows(conn, f'SELECT * FROM de_recipe_readiness {where} ORDER BY recipe_name', params)
    found = {r['external_source_id'] for r in readiness}
    recipe_ids = [r['recipe_id'] for r in readiness]
    mappings = rows(conn, '''SELECT DISTINCT i.ingredient_id,i.ingredient_name,m.source_id,
        m.source_record_id,m.source_description,m.match_score,m.matched_by,
        coalesce(mr.review_status,'pending_review') AS review_status,mr.review_note
        FROM recipe_ingredients ri JOIN ingredients i USING(ingredient_id)
        LEFT JOIN ingredient_source_map m USING(ingredient_id)
        LEFT JOIN de_mapping_reviews mr ON mr.ingredient_id=m.ingredient_id AND mr.source_id=m.source_id
        WHERE ri.recipe_id=ANY(%s) ORDER BY i.ingredient_name,m.source_id''', (recipe_ids,))
    quantities = rows(conn, '''SELECT r.external_source_id,r.recipe_name,l.* FROM de_ingredient_line_readiness l
        JOIN recipes r USING(recipe_id) WHERE l.recipe_id=ANY(%s) AND NOT l.quantity_ready
        ORDER BY r.recipe_name,l.ingredient_name''', (recipe_ids,))
    nutrients = rows(conn, '''SELECT n.* FROM de_recipe_nutrient_readiness n WHERE n.recipe_id=ANY(%s)
        ORDER BY n.recipe_name,n.nutrient_id''', (recipe_ids,))
    # Only public recipe-review facts, not reviewer identities or user/profile data.
    ui_reviews = []
    if conn.execute("SELECT to_regclass('public.recipe_nutrition_reviews')").fetchone()[0]:
        ui_reviews = rows(conn, '''SELECT DISTINCT ON(recipe_id) recipe_id,verdict,reason,energy_ratio,flags,reviewed_at
            FROM recipe_nutrition_reviews WHERE recipe_id=ANY(%s) ORDER BY recipe_id,reviewed_at DESC,review_id DESC''', (recipe_ids,))
    candidates = rows(conn, '''SELECT br.rule_id,br.trigger_code,count(DISTINCT ri.recipe_id) AS recipe_count
        FROM business_rules br JOIN ingredient_rule_tags t ON t.rule_code=br.trigger_code
        JOIN recipe_ingredients ri USING(ingredient_id) WHERE br.is_active AND ri.recipe_id=ANY(%s)
        GROUP BY br.rule_id,br.trigger_code ORDER BY br.rule_id''', (recipe_ids,))
    summary = {'scope': scope, 'scope_source': 'docs/MaziMeal_50_Recipes_Culture_Optimized.csv' if scope=='seed' else 'All active local recipes',
        'expected_seed_recipes': len(ids), 'recipes_reported': len(readiness),
        'missing_seed_external_ids': sorted(set(ids)-found),
        'ingredient_lines': sum(r['ingredient_lines'] for r in readiness),
        'lines_missing_grams': sum(r['lines_missing_grams'] for r in readiness),
        'lines_quantity_unreviewed': sum(r['lines_quantity_unreviewed'] for r in readiness),
        'ready_nutrient_rows': sum(r['ready'] for r in nutrients),
        'candidate_rule_coverage': candidates,
        'scope_note': 'Ingredient tags indicate candidates only; nutrient readiness is separate from clinical validity and user suitability.'}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'summary.json',summary)
    for name, values in [('recipe_ids',readiness),('mapping_review',mappings),('quantity_review',quantities),('nutrient_coverage',nutrients)]:
        write_csv(output/f'{name}.csv',values)
    write_json(output/'nutrition_review_queue.json',ui_reviews)
    write_json(output/'dataset_releases.json',rows(conn,'SELECT * FROM de_dataset_releases ORDER BY imported_at'))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['configure','bootstrap','report','recipe'])
    parser.add_argument('--scope',choices=['seed','all'],default='seed')
    parser.add_argument('--recipe-id')
    parser.add_argument('--out',type=Path,default=ROOT/'data_engineering/local_results')
    args = parser.parse_args()
    try:
        if args.command == 'configure':
            result = configure()
        else:
            # Read paths are read-only at connection level, including after rollback.
            options = '-c statement_timeout=60000'
            if args.command != 'bootstrap':
                options += ' -c default_transaction_read_only=on'
            with psycopg.connect(connection_settings(), options=options, autocommit=True) as conn:
                if args.command == 'bootstrap':
                    result = bootstrap(conn)
                else:
                    with conn.transaction():
                        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                        if args.command == 'recipe':
                            if not args.recipe_id:
                                parser.error('--recipe-id is required; get it from recipe_ids.csv')
                            result = recipe_packet(conn,str(UUID(args.recipe_id)))
                        else:
                            result = report(conn,args.out,args.scope)
        print(json.dumps(result,default=encode,indent=2))
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
