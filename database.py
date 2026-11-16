from pathlib import Path
from datetime import datetime, date, timezone
from contextlib import closing
import json, sqlite3, os

ROOT=Path(__file__).resolve().parent
DB_PATH=Path(os.environ.get('LMO_DB_PATH',str(ROOT/'instance/ecology.sqlite')))

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect(path=None):
    db=sqlite3.connect(path or DB_PATH,timeout=20)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def initialize(path=None):
    with closing(connect(path)) as db, db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS facility(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,description TEXT);
        CREATE TABLE IF NOT EXISTS plot(id INTEGER PRIMARY KEY,facility_id INTEGER NOT NULL REFERENCES facility(id),code TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('control','experimental','unspecified')),notes TEXT,UNIQUE(facility_id,code));
        CREATE TABLE IF NOT EXISTS survey_event(id INTEGER PRIMARY KEY,facility_id INTEGER REFERENCES facility(id),plot_id INTEGER REFERENCES plot(id),survey_date TEXT NOT NULL,method TEXT,notes TEXT);
        CREATE TABLE IF NOT EXISTS sample(id INTEGER PRIMARY KEY,event_id INTEGER NOT NULL REFERENCES survey_event(id),code TEXT NOT NULL,notes TEXT,UNIQUE(event_id,code));
        CREATE TABLE IF NOT EXISTS observation_context(observation_id INTEGER PRIMARY KEY REFERENCES observation(id),event_id INTEGER NOT NULL REFERENCES survey_event(id),sample_id INTEGER REFERENCES sample(id));
        CREATE TABLE IF NOT EXISTS quality_issue(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES source_file(id),source_column INTEGER,observation_id INTEGER REFERENCES observation(id),code TEXT NOT NULL,description TEXT NOT NULL,affected_count INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reviewed')),note TEXT,reviewed_at TEXT);
        CREATE TABLE IF NOT EXISTS revision_history(id INTEGER PRIMARY KEY,entity_type TEXT NOT NULL,entity_id INTEGER NOT NULL,field_name TEXT NOT NULL,old_json TEXT,new_json TEXT,reason TEXT NOT NULL,changed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS import_file(source_id INTEGER PRIMARY KEY REFERENCES source_file(id),stored_name TEXT,format TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS obs_taxon ON observation(taxon_id);
        CREATE INDEX IF NOT EXISTS obs_source_column ON observation(source_id,source_column);
        CREATE INDEX IF NOT EXISTS obs_time_context ON observation(time_precision,survey_year,survey_month);
        CREATE INDEX IF NOT EXISTS quality_status ON quality_issue(status,code);
        CREATE INDEX IF NOT EXISTS revision_entity ON revision_history(entity_type,entity_id);
        PRAGMA user_version=8;
        ''')
        if not db.execute('SELECT 1 FROM quality_issue LIMIT 1').fetchone():
            db.execute("INSERT INTO quality_issue(source_id,source_column,code,description,affected_count) SELECT source_id,source_column,'date_pending','Exact survey date to be verified',COUNT(*) FROM observation WHERE survey_date IS NULL GROUP BY source_id,source_column")
            db.execute("INSERT INTO quality_issue(source_id,code,description,affected_count) SELECT source_id,'coordinate_unverified','Source coordinates to be verified; not replaced by weather-station coordinates',COUNT(*) FROM observation WHERE coordinate_status='unverified' GROUP BY source_id")
            db.execute("INSERT INTO quality_issue(source_id,code,description,affected_count) SELECT source_id,'unresolved_cell','Source cell with unresolved time context or number format',COUNT(*) FROM unresolved_cell GROUP BY source_id")

def audit(db,kind,ident,field,old,new,reason):
    db.execute('INSERT INTO revision_history(entity_type,entity_id,field_name,old_json,new_json,reason,changed_at) VALUES(?,?,?,?,?,?,?)',
        (kind,ident,field,json.dumps(old,ensure_ascii=False),json.dumps(new,ensure_ascii=False),reason,now()))

def where(params):
    sql=[];values=[]
    for name,column in [('group','t.group_name'),('year','o.survey_year'),('month','o.survey_month'),('source','o.source_id')]:
        if params.get(name): sql.append(column+'=?');values.append(params[name])
    if params.get('q'):
        term='%'+params['q'].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        sql.append("(t.label LIKE ? ESCAPE '\\' OR t.scientific_name LIKE ? ESCAPE '\\' OR t.korean_name LIKE ? ESCAPE '\\')");values.extend([term]*3)
    return (' WHERE '+' AND '.join(sql) if sql else ''),values

def summary(db):
    scalar=lambda query:db.execute(query).fetchone()[0]
    return {'observations':scalar('SELECT COUNT(*) FROM observation'),'taxon_labels':scalar('SELECT COUNT(*) FROM taxon'),
        'sources':scalar('SELECT COUNT(*) FROM source_file'),'unresolved_cells':scalar('SELECT COUNT(*) FROM unresolved_cell'),
        'dated':scalar('SELECT COUNT(*) FROM observation WHERE survey_date IS NOT NULL'),
        'events':scalar('SELECT COUNT(*) FROM survey_event'),'samples':scalar('SELECT COUNT(*) FROM sample'),
        'issues_open':scalar("SELECT COUNT(*) FROM quality_issue WHERE status='open'"),
        'groups':[dict(r) for r in db.execute('SELECT t.group_name,COUNT(*) records,COUNT(DISTINCT o.taxon_id) labels FROM observation o JOIN taxon t ON t.id=o.taxon_id GROUP BY t.group_name')],
        'years':[dict(r) for r in db.execute('SELECT survey_year year,COUNT(*) records FROM observation GROUP BY survey_year ORDER BY survey_year')],
        'time_precision':[dict(r) for r in db.execute('SELECT time_precision precision,COUNT(*) records FROM observation GROUP BY time_precision')],
        'weather':[dict(r) for r in db.execute('SELECT s.station_id,s.name,s.provider,COUNT(*) dates,COUNT(w.temperature_mean_c) mean_temperature_days,COUNT(w.humidity_mean_pct) humidity_days,COUNT(w.precipitation_mm) rain_days FROM weather_daily w JOIN weather_station s USING(station_id) GROUP BY s.station_id')],
        'experiments':scalar('SELECT COUNT(*) FROM experiment'),'measurement_slots':scalar('SELECT COUNT(*) FROM experiment_value'),
        'measured_values':scalar("SELECT COUNT(*) FROM experiment_value WHERE status='measured'")}

def observations(db,params,export=False):
    clause,values=where(params)
    join=' FROM observation o JOIN taxon t ON t.id=o.taxon_id JOIN source_file f ON f.id=o.source_id '
    count=db.execute('SELECT COUNT(*)'+join+clause,values).fetchone()[0]
    page=max(1,int(params.get('page',1)));size=min(100,max(10,int(params.get('size',50))))
    columns='o.*,t.group_name,t.label,t.scientific_name,t.korean_name,t.rank_status,f.name source_name'
    query='SELECT '+columns+join+clause+' ORDER BY o.id'
    if not export:query+=' LIMIT ? OFFSET ?';values=values+[size,(page-1)*size]
    return {'total':count,'page':page,'size':size,'rows':[dict(r) for r in db.execute(query,values)]}

def detail(db,ident):
    r=db.execute('SELECT o.*,t.group_name,t.label,t.scientific_name,t.korean_name,t.rank_status,f.name source_name,f.sha256 source_sha256 FROM observation o JOIN taxon t ON t.id=o.taxon_id JOIN source_file f ON f.id=o.source_id WHERE o.id=?',(ident,)).fetchone()
    if not r: raise ValueError('Observation not found.')
    data=dict(r)
    raw=db.execute('SELECT cells_json FROM raw_row WHERE source_id=? AND row_number=?',(r['source_id'],r['row_number'])).fetchone()
    data['raw_cells']=json.loads(raw[0]) if raw else []
    ctx=db.execute('SELECT c.*,e.survey_date,e.facility_id,e.plot_id,s.code sample_code FROM observation_context c JOIN survey_event e ON e.id=c.event_id LEFT JOIN sample s ON s.id=c.sample_id WHERE c.observation_id=?',(ident,)).fetchone()
    data['context']=dict(ctx) if ctx else None
    data['column_records']=db.execute('SELECT COUNT(*) FROM observation WHERE source_id=? AND source_column=?',(r['source_id'],r['source_column'])).fetchone()[0]
    data['revisions']=[dict(x) for x in db.execute("SELECT * FROM revision_history WHERE entity_type='observation' AND entity_id=? ORDER BY id DESC",(ident,))]
    if r['survey_date']:
        data['weather']=[dict(x) for x in db.execute('SELECT w.*,s.name station_name FROM weather_daily w JOIN weather_station s USING(station_id) WHERE date=?',(r['survey_date'],))]
    elif r['survey_month']:
        data['weather']=[dict(x) for x in db.execute('SELECT w.*,s.name station_name FROM weather_monthly w JOIN weather_station s USING(station_id) WHERE year=? AND month=?',(r['survey_year'],r['survey_month']))]
    else:
        data['weather']=[dict(x) for x in db.execute('SELECT w.*,s.name station_name FROM weather_yearly w JOIN weather_station s USING(station_id) WHERE year=?',(r['survey_year'],))]
    return data

def set_context(db,body):
    ident=int(body['observation_id']);r=db.execute('SELECT * FROM observation WHERE id=?',(ident,)).fetchone()
    if not r:raise ValueError('Observation not found.')
    day=date.fromisoformat(body['survey_date']);reason=str(body.get('reason','')).strip()
    if not reason:raise ValueError('Enter the evidence.')
    column_scope=body.get('scope')=='column'
    if column_scope and r['source_column']==0:raise ValueError('This source does not support linking by sample column. Link individual records.')
    targets=db.execute('SELECT id,survey_year,survey_month,survey_date,time_precision,plot_id FROM observation WHERE '+('source_id=? AND source_column=?' if column_scope else 'id=?'),(r['source_id'],r['source_column']) if column_scope else (ident,)).fetchall()
    if any(x['survey_year']!=day.year or (x['survey_month'] and x['survey_month']!=day.month) for x in targets):
        raise ValueError('The survey date differs from the recorded year or month. Check the source year and month first.')
    fid=int(body['facility_id']) if body.get('facility_id') else None
    pid=int(body['plot_id']) if body.get('plot_id') else None
    if fid and not db.execute('SELECT 1 FROM facility WHERE id=?',(fid,)).fetchone():raise ValueError('Facility not registered.')
    if pid and not db.execute('SELECT 1 FROM plot WHERE id=? AND facility_id=?',(pid,fid)).fetchone():raise ValueError('Check the link between the plot and the facility.')
    eid=db.execute('INSERT INTO survey_event(facility_id,plot_id,survey_date,method,notes) VALUES(?,?,?,?,?)',(fid,pid,day.isoformat(),body.get('method',''),reason)).lastrowid
    sample_id=None
    if str(body.get('sample_code','')).strip():
        sample_id=db.execute('INSERT INTO sample(event_id,code) VALUES(?,?)',(eid,body['sample_code'].strip())).lastrowid
    for x in targets:
        old=dict(x);new={'survey_year':day.year,'survey_month':day.month,'survey_date':day.isoformat(),'time_precision':'day','plot_id':pid,'event_id':eid,'sample_id':sample_id}
        audit(db,'observation',x['id'],'context',old,new,reason)
        db.execute("UPDATE observation SET survey_month=?,survey_date=?,time_precision='day',plot_id=? WHERE id=?",(day.month,day.isoformat(),pid,x['id']))
        db.execute('INSERT OR REPLACE INTO observation_context VALUES(?,?,?)',(x['id'],eid,sample_id))
        db.execute('DELETE FROM observation_weather WHERE observation_id=?',(x['id'],))
        db.execute("INSERT INTO observation_weather SELECT ?,station_id,date,'exact_date_separate_station' FROM weather_daily WHERE date=?",(x['id'],day.isoformat()))
    if column_scope:
        db.execute("UPDATE quality_issue SET status='reviewed',note=?,reviewed_at=? WHERE source_id=? AND source_column=? AND code='date_pending'",(reason,now(),r['source_id'],r['source_column']))
    return {'updated':len(targets),'event_id':eid,'sample_id':sample_id}

def schema(db):
    result=[]
    for r in db.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type,name"):
        name=r['name'];result.append({'name':name,'type':r['type'],'sql':r['sql'],
            'columns':[dict(x) for x in db.execute('PRAGMA table_info("'+name+'")')],
            'foreign_keys':[dict(x) for x in db.execute('PRAGMA foreign_key_list("'+name+'")')]})
    return result
