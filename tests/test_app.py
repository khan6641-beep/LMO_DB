"""Tests against a temporary copy of the bundled database.

Run from the package root: python -m unittest discover -s tests
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import database as store  # noqa: E402
from importer import ingest  # noqa: E402
import app  # noqa: E402

SEED = store.DB_PATH


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'test.sqlite'
        src = sqlite3.connect(SEED); dst = sqlite3.connect(self.path); src.backup(dst); src.close(); dst.close()
        self.db = store.connect(self.path)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()


class DatabaseTests(Base):
    def test_seed_integrity(self):
        s = store.summary(self.db)
        self.assertEqual(s['observations'], 588)
        self.assertEqual(s['taxon_labels'], 292)
        self.assertEqual({g['group_name']: g['records'] for g in s['groups']}, {'arthropods': 472, 'plants': 116})
        self.assertEqual(s['experiments'], 21)
        self.assertEqual(s['measurement_slots'], 12808)
        self.assertEqual(s['measured_values'], 0)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())

    def test_slots_follow_design(self):
        for row in self.db.execute('SELECT * FROM experiment_inventory'):
            if row['value_slots']:
                species_items = self.db.execute(
                    "SELECT COUNT(*) FROM measurement_item m JOIN experiment_unit_set s ON s.id=m.unit_set_id "
                    "WHERE s.experiment_id=? AND s.name=? AND (m.label LIKE '%by species%' OR m.label LIKE '%by taxon%')",
                    (row['experiment_id'], row['unit_set'])).fetchone()[0]
                self.assertEqual(row['value_slots'], row['units'] * (row['items'] - species_items))

    def test_import_exact_headers_and_duplicate(self):
        content = b'Scientific Name,Year,Presence\nNasonia test,2020,Y\n'
        with self.db:
            r = ingest(self.db, 'test.csv', content, 'arthropods')
        row = self.db.execute('SELECT * FROM observation WHERE source_id=?', (r['source_ids'][0],)).fetchone()
        self.assertIsNone(row['value'])
        self.assertEqual(row['measurement_type'], 'presence_label')
        self.assertEqual(row['time_precision'], 'year')
        with self.db:
            self.assertTrue(ingest(self.db, 'renamed.csv', content, 'arthropods')['duplicate'])

    def test_import_rejects_bad_input(self):
        for content, group in ((b'Name,Year\nx,2020\n', 'plants'), (b'Scientific Name,Year\nx,2020\n', 'bacteria'),
                               (b'taxon_label,survey_year,measurement_type,value,unit\nx,2020,individual_count,1.5,count\n', 'plants')):
            with self.assertRaises(ValueError):
                with self.db:
                    ingest(self.db, 'bad.csv', content, group)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observation').fetchone()[0], 588)

    def test_date_link_keeps_history_and_weather(self):
        oid = self.db.execute("SELECT o.id FROM observation o JOIN taxon t ON t.id=o.taxon_id WHERE t.group_name='plants' AND o.survey_year=2020").fetchone()[0]
        with self.db:
            with self.assertRaises(ValueError):
                store.set_context(self.db, {'observation_id': oid, 'survey_date': '2021-05-12', 'reason': 'wrong year'})
            r = store.set_context(self.db, {'observation_id': oid, 'survey_date': '2020-05-12', 'reason': 'field note'})
        self.assertEqual(r['updated'], 1)
        d = store.detail(self.db, oid)
        self.assertEqual(d['time_precision'], 'day')
        self.assertEqual(len(d['weather']), 2)
        self.assertEqual(len(d['revisions']), 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observation_weather WHERE observation_id=?', (oid,)).fetchone()[0], 2)


class HttpTests(Base):
    def setUp(self):
        super().setUp()
        self.old = store.DB_PATH
        store.DB_PATH = self.path
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        store.DB_PATH = self.old
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=20) as r:
            return r.status, r.headers.get_content_type(), r.read()

    def test_pages_and_read_routes(self):
        for path in ('/', '/style.css', '/app.js'):
            self.assertEqual(self.get(path)[0], 200)
        boot = json.loads(self.get('/api/bootstrap')[2])
        self.assertEqual(boot['version'], '8.0')
        self.assertEqual(boot['years'], [2019, 2020, 2021, 2022])
        obs = json.loads(self.get('/api/observations?group=plants&year=2020')[2])
        self.assertEqual(obs['total'], 37)
        self.assertEqual(json.loads(self.get('/api/observations?q=Leucauge')[2])['total'], 6)
        detail = json.loads(self.get('/api/observation?id=%d' % obs['rows'][0]['id'])[2])
        self.assertTrue(detail['raw_cells'])
        exps = json.loads(self.get('/api/experiments')[2])
        self.assertEqual(len(exps['experiments']), 21)
        self.assertEqual(sum(e['slots'] for e in exps['experiments']), 12808)
        e04 = json.loads(self.get('/api/experiment?id=E04')[2])
        self.assertEqual(len(e04['unit_sets']), 5)
        weather = json.loads(self.get('/api/weather?station=614&year=2020')[2])
        self.assertEqual(len(weather['rows']), 366)
        self.assertEqual(len(json.loads(self.get('/api/aerial')[2])['months']), 96)
        self.assertGreater(len(json.loads(self.get('/api/schema')[2])), 25)
        self.assertEqual(json.loads(self.get('/api/issues?status=open')[2])['total'], 6)
        status, ctype, body = self.get('/api/export?group=arthropods')
        self.assertEqual(ctype, 'text/csv')
        self.assertEqual(body.decode('utf-8-sig').count('\n'), 473)

    def test_write_needs_token(self):
        req = urllib.request.Request(self.base + '/api/facility', data=json.dumps({'name': 'x'}).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=20)
        self.assertEqual(ctx.exception.code, 403)
        token = json.loads(self.get('/api/bootstrap')[2])['token']
        req.add_header('X-CSRF-Token', token)
        with urllib.request.urlopen(req, timeout=20) as r:
            self.assertEqual(r.status, 200)
        self.assertEqual(len(json.loads(self.get('/api/history')[2])), 100)

    def test_unknown_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get('/api/assays')
        self.assertEqual(ctx.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
