"""CSV import with exact-header mapping, duplicate check by content hash and retained source rows."""
from datetime import date, datetime
from pathlib import Path
import csv
import hashlib
import io
import json
import math

from database import now

GROUPS = {'plants', 'arthropods'}
KINDS = ('presence_label', 'individual_count')


def number(value):
    v = float(value)
    if not math.isfinite(v) or v < 0:
        raise ValueError('A measurement must be a finite number of 0 or more.')
    return v


def text(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else '' if v is None else str(v)


def get_taxon(db, group, label, sci=None, kor=None):
    if not label:
        raise ValueError('The taxon label is empty.')
    db.execute('INSERT OR IGNORE INTO taxon(group_name,label,scientific_name,korean_name,rank_status) VALUES(?,?,?,?,?)',
               (group, label, sci, kor, 'source_label_unverified'))
    return db.execute('SELECT id FROM taxon WHERE group_name=? AND label=?', (group, label)).fetchone()[0]


def put(db, sid, row, tid, year, month, kind, value, unit, raw, day=None, coord=None):
    if not 1900 <= year <= 2100:
        raise ValueError('Check the survey year.')
    if month is not None and not 1 <= month <= 12:
        raise ValueError('The survey month must be 1-12.')
    precision = 'day' if day else 'month' if month else 'year'
    return db.execute(
        'INSERT INTO observation(source_id,row_number,source_column,taxon_id,survey_year,survey_month,survey_date,'
        'time_precision,measurement_type,value,unit,raw_value,coordinate_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (sid, row, 0, tid, year, month, day, precision, kind, value, unit, raw, coord)).lastrowid


def flat(db, sid, rows, group, year_hint):
    header = [text(v).strip() for v in rows[0]]
    if len(set(header)) != len(header):
        raise ValueError('Column names are duplicated in the header.')
    cols = {v: i for i, v in enumerate(header)}
    if not {'taxon_label', 'Scientific Name', 'scientific_name'} & set(cols):
        raise ValueError('Unsupported header. Use the standard CSV columns.')
    for i, row in enumerate(rows[1:], 2):
        if not any(text(v).strip() for v in row):
            continue

        def cell(*names):
            for name in names:
                if name in cols and cols[name] < len(row):
                    return text(row[cols[name]]).strip()
            return ''

        rg = cell('group_name') or group
        if rg not in GROUPS:
            raise ValueError('Select the data group.')
        sci = cell('scientific_name', 'Scientific Name')
        kor = cell('korean_name')
        tid = get_taxon(db, rg, cell('taxon_label') or sci or kor, sci or None, kor or None)
        y = cell('survey_year', 'Year') or year_hint
        day = cell('survey_date') or None
        parsed = None
        if day:
            parsed = date.fromisoformat(day)
            if y and int(y) != parsed.year:
                raise ValueError('The survey date and survey year differ.')
            y = parsed.year
        if not y:
            raise ValueError('Give the survey year for a list without a year column.')
        month = int(cell('survey_month')) if cell('survey_month') else None
        if parsed:
            if month and month != parsed.month:
                raise ValueError('The survey date and survey month differ.')
            month = parsed.month
        kind = cell('measurement_type') or 'presence_label'
        if kind not in KINDS:
            raise ValueError('Unsupported measurement type.')
        raw = cell('value') if kind != 'presence_label' else cell('Presence', 'presence', 'raw_value')
        value = number(raw) if raw and kind != 'presence_label' else None
        unit = cell('unit') or ('count' if kind == 'individual_count' else None)
        if kind == 'individual_count' and (value is None or value != int(value) or unit != 'count'):
            raise ValueError('An individual count needs an integer of 0 or more and the unit count.')
        coord = 'unverified' if 'Latitude' in cols or 'Longitude' in cols else 'not_provided'
        put(db, sid, i, tid, int(y), month, kind, value, unit, raw or None, day, coord)


def ingest(db, filename, content, group='', year_hint=''):
    filename = Path(filename.replace('\\', '/')).name
    if Path(filename).suffix.lower() != '.csv':
        raise ValueError('Select a CSV file.')
    digest = hashlib.sha256(content).hexdigest()
    if db.execute('SELECT id FROM source_file WHERE sha256=?', (digest,)).fetchone():
        return {'duplicate': True, 'message': 'The same file is already registered. Nothing was imported.'}
    for enc in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            decoded = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('Check the file encoding.')
    rows = list(csv.reader(io.StringIO(decoded)))
    if not rows:
        raise ValueError('The file is empty.')
    before = db.execute('SELECT COUNT(*) FROM observation').fetchone()[0]
    sid = db.execute('INSERT INTO source_file(name,sha256,encoding) VALUES(?,?,?)', (filename, digest, enc)).lastrowid
    db.executemany('INSERT INTO raw_row VALUES(?,?,?)',
                   [(sid, i, json.dumps([text(x) for x in row], ensure_ascii=False)) for i, row in enumerate(rows, 1)])
    flat(db, sid, rows, group, year_hint)
    db.execute("INSERT INTO quality_issue(source_id,source_column,code,description,affected_count) "
               "SELECT source_id,source_column,'date_pending','Exact survey date to be verified',COUNT(*) FROM observation "
               "WHERE source_id=? AND survey_date IS NULL GROUP BY source_id,source_column", (sid,))
    db.execute('INSERT INTO import_file VALUES(?,?,?,?)', (sid, digest + '.csv', 'csv', now()))
    n = db.execute('SELECT COUNT(*) FROM observation').fetchone()[0] - before
    if not n:
        raise ValueError('No observation could be imported. Check the data group, year and header.')
    folder = Path(db.execute('PRAGMA database_list').fetchone()[2]).parent / 'source_files'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (digest + '.csv')).write_bytes(content)
    return {'duplicate': False, 'inserted': n, 'source_ids': [sid], 'message': f'{n:,} observation records imported.'}
