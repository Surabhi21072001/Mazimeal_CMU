"""Local read-only viewer for the saved development database; no write routes."""
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from uuid import UUID

import psycopg
from psycopg import sql

HERE = Path(__file__).resolve().parent
TEAM = HERE.parent
sys.path.insert(0, str(TEAM / 'data_engineering'))
from manage import rows, encode, recipe_packet, connection_settings

DSN = connection_settings()

TABLES = {
    'recipes': 'One record per recipe, with its stable database ID and source.',
    'ingredients': 'Shared ingredient names used across recipes.',
    'recipe_ingredients': 'Connects recipes to ingredients and their source quantities.',
    'recipe_steps': 'Cooking instructions in step order.',
    'recipe_nutrition': 'Source-published nutrition per serving, not recalculated totals.',
    'ingredient_nutrition': 'Mapped USDA nutrient values per 100 g; usable recipe grams are still needed.',
    'business_rules': 'Optimization rules, conditions, evidence and automation limits.',
    'rule_codes': 'Vocabulary used to connect ingredients and rules.',
    'ingredient_rule_tags': 'Ingredient-to-rule-code connections; a match is only a candidate.',
    'ingredient_source_map': 'Ingredient-to-USDA matches and source descriptions.',
    'data_sources': 'Origin and attribution of imported data.',
    'de_mapping_reviews': 'Human review status for ingredient matches.',
    'de_line_reviews': 'Human review status for quantities.',
    'de_recipe_readiness': 'Per-recipe coverage and missing-data checks.',
    'de_ingredient_line_readiness': 'Per-ingredient coverage, mappings and calculation readiness.',
    'de_dataset_releases': 'Import date and source-file fingerprints.',
    'de_recipe_reviews': 'Ingredient completeness, preparation and serving review.',
    'de_recipe_nutrient_readiness': 'Coverage and reviewed totals for each nutrient.',
    'de_line_provenance': 'Original source text and positions, when recorded.',
}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, data, kind='application/json', status=200):
        body = data if isinstance(data, bytes) else json.dumps(data, default=encode).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get('Host') not in ('127.0.0.1:7211', 'localhost:7211'):
            return self.send({'error': 'Local access only'}, status=403)
        url = urlparse(self.path)
        args = parse_qs(url.query)
        if url.path == '/':
            return self.send((HERE / 'viewer.html').read_bytes(), 'text/html')
        if not url.path.startswith('/api/'):
            return self.send({'error': 'Not found'}, status=404)
        try:
            with psycopg.connect(DSN, options='-c default_transaction_read_only=on -c statement_timeout=10000', connect_timeout=5) as conn:
                if url.path == '/api/overview':
                    counts = {t: conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(t))).fetchone()[0] for t in TABLES}
                    data = {'counts': counts, 'tables': TABLES, 'checked_at': datetime.now(timezone.utc).isoformat(),
                        'readiness': rows(conn, 'SELECT sum(ingredient_lines) AS lines, sum(lines_with_nutrition) AS with_nutrition, sum(lines_missing_grams) AS missing_grams, sum(ingredient_lines-lines_quantity_unreviewed) AS ready FROM de_recipe_readiness')[0],
                        'reviews': rows(conn, '''SELECT i.ingredient_name,m.source_description,r.review_note,r.review_status FROM de_mapping_reviews r JOIN ingredients i USING(ingredient_id) JOIN ingredient_source_map m USING(ingredient_id,source_id) WHERE r.review_status <> 'approved' ORDER BY (r.review_note IS NULL),m.match_score,i.ingredient_name LIMIT 12'''),
                        'releases': rows(conn, 'SELECT release_id,imported_at FROM de_dataset_releases ORDER BY imported_at'),
                        'recipes': rows(conn, 'SELECT recipe_id,recipe_name FROM recipes WHERE deleted_at IS NULL ORDER BY recipe_name')}
                elif url.path == '/api/table':
                    name = args.get('name', ['recipes'])[0]
                    if name not in TABLES:
                        return self.send({'error': 'Unknown table'}, status=400)
                    offset = max(0, int(args.get('offset', ['0'])[0]))
                    columns = rows(conn, 'SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=%s ORDER BY ordinal_position', (name,))
                    primary = {'recipes':'recipe_name','ingredients':'ingredient_name','business_rules':'rule_id','rule_codes':'code','de_recipe_readiness':'recipe_name'}.get(name, columns[0]['column_name'])
                    query = sql.SQL('SELECT * FROM {} ORDER BY {} LIMIT 50 OFFSET %s').format(sql.Identifier(name),sql.Identifier(primary))
                    data = {'rows': rows(conn, query, (offset,)), 'columns': columns, 'description': TABLES[name], 'count': conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name))).fetchone()[0]}
                elif url.path == '/api/recipe':
                    recipe_id = str(UUID(args.get('id', [''])[0]))
                    data = recipe_packet(conn, recipe_id)
                    data['recipe'] = rows(conn, 'SELECT * FROM recipes WHERE recipe_id=%s', (recipe_id,))[0]
                    data['steps'] = rows(conn, 'SELECT step_number,instruction FROM recipe_steps WHERE recipe_id=%s ORDER BY step_number', (recipe_id,))
                    data['published_nutrition'] = rows(conn, 'SELECT nutrient_id,per_serving,unit,source FROM recipe_nutrition WHERE recipe_id=%s ORDER BY nutrient_id', (recipe_id,))
                else:
                    return self.send({'error': 'Not found'}, status=404)
            self.send(data)
        except (ValueError, IndexError):
            self.send({'error': 'Invalid request or missing record'}, status=400)
        except Exception:
            self.send({'error': 'Database query failed. Check the local PostgreSQL container.'}, status=503)

if __name__ == '__main__':
    print('Read-only MaziMeal viewer: http://127.0.0.1:7211', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 7211), Handler).serve_forever()
