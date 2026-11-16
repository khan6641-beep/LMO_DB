"""Read-only routes for the experiment-design module and the aerial inventory."""


def _count(db, sql, args=()):
    return db.execute(sql, args).fetchone()[0]


def get(db, path, params):
    if path == '/api/experiments':
        rows = []
        for e in db.execute('SELECT * FROM experiment ORDER BY id'):
            e = dict(e)
            scope = 'FROM experiment_unit_set x WHERE x.experiment_id=?'
            e['unit_sets'] = _count(db, 'SELECT COUNT(*) ' + scope, (e['id'],))
            e['units'] = _count(db, 'SELECT COUNT(*) FROM experimental_unit u JOIN experiment_unit_set x ON x.id=u.unit_set_id WHERE x.experiment_id=?', (e['id'],))
            e['items'] = _count(db, 'SELECT COUNT(*) FROM measurement_item m JOIN experiment_unit_set x ON x.id=m.unit_set_id WHERE x.experiment_id=?', (e['id'],))
            slots = ('FROM experiment_value v JOIN experimental_unit u ON u.id=v.unit_id '
                     'JOIN experiment_unit_set x ON x.id=u.unit_set_id WHERE x.experiment_id=?')
            e['slots'] = _count(db, 'SELECT COUNT(*) ' + slots, (e['id'],))
            e['measured'] = _count(db, 'SELECT COUNT(*) ' + slots + " AND v.status='measured'", (e['id'],))
            rows.append(e)
        shared = [dict(r) for r in db.execute(
            'SELECT m.label, COUNT(DISTINCT s.experiment_id) experiments, GROUP_CONCAT(DISTINCT s.experiment_id) ids '
            'FROM measurement_item m JOIN experiment_unit_set s ON s.id=m.unit_set_id GROUP BY m.label '
            'HAVING COUNT(DISTINCT s.experiment_id)>1 ORDER BY experiments DESC, m.label')]
        return {'experiments': rows, 'shared_labels': shared}
    if path == '/api/experiment':
        e = db.execute('SELECT * FROM experiment WHERE id=?', (params.get('id'),)).fetchone()
        if not e:
            raise ValueError('Experiment not found.')
        e = dict(e)
        e['unit_sets'] = []
        for s in db.execute('SELECT * FROM experiment_unit_set WHERE experiment_id=? ORDER BY id', (e['id'],)).fetchall():
            s = dict(s)
            factors = {}
            for f in db.execute('SELECT factor, level FROM experiment_factor_level WHERE unit_set_id=? ORDER BY factor, level_order', (s['id'],)):
                factors.setdefault(f['factor'], []).append(f['level'])
            s['factors'] = factors
            s['items'] = [r[0] for r in db.execute('SELECT label FROM measurement_item WHERE unit_set_id=? ORDER BY id', (s['id'],))]
            s['units'] = _count(db, 'SELECT COUNT(*) FROM experimental_unit WHERE unit_set_id=?', (s['id'],))
            s['slots'] = _count(db, 'SELECT COUNT(*) FROM experiment_value v JOIN experimental_unit u ON u.id=v.unit_id WHERE u.unit_set_id=?', (s['id'],))
            e['unit_sets'].append(s)
        return e
    if path == '/api/aerial':
        return {'inventory': [dict(r) for r in db.execute('SELECT * FROM aerial_inventory ORDER BY year')],
                'months': [dict(r) for r in db.execute('SELECT * FROM aerial_month ORDER BY year, month')],
                'assets': [dict(r) for r in db.execute('SELECT * FROM aerial_asset ORDER BY year, month')],
                'cutoff': '2026-10-16'}
    raise ValueError('Unknown route.')
