from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from datetime import date
from contextlib import closing
import base64,csv,io,json,mimetypes,os,secrets,sqlite3,tempfile,urllib.parse,webbrowser,threading
import database as store
import extensions
from importer import ingest

TOKEN=secrets.token_urlsafe(32)
PUBLIC=store.ROOT/'public'

def csv_safe(value):
    value='' if value is None else str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,payload,status=200,ctype='application/json; charset=utf-8',filename=None):
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8') if ctype.startswith('application/json') else payload
        self.send_response(status)
        self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'")
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers();self.wfile.write(raw)
    def checked_host(self):
        host=self.headers.get('Host','')
        if host not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
            raise ValueError('Open the application from the local address.')
    def do_GET(self):
        try:
            self.checked_host();parsed=urllib.parse.urlsplit(self.path);path=parsed.path
            params={k:v[-1] for k,v in urllib.parse.parse_qs(parsed.query).items()}
            if not path.startswith('/api/'):
                names={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js'}
                if path not in names:return self.send({'error':'Path not found.'},404)
                file=PUBLIC/names[path];return self.send(file.read_bytes(),ctype=(mimetypes.guess_type(file.name)[0] or 'application/octet-stream')+'; charset=utf-8')
            with closing(store.connect()) as db, db:
                if path=='/api/bootstrap':
                    payload={'token':TOKEN,'version':'8.0','sources':[dict(r) for r in db.execute('SELECT id,name,sha256,encoding FROM source_file')],
                        'facilities':[dict(r) for r in db.execute('SELECT * FROM facility')],'plots':[dict(r) for r in db.execute('SELECT * FROM plot')],
                        'stations':[dict(r) for r in db.execute('SELECT * FROM weather_station')],
                        'years':[r[0] for r in db.execute('SELECT DISTINCT survey_year FROM observation ORDER BY survey_year')]}
                elif path in ('/api/experiments','/api/experiment','/api/aerial'):payload=extensions.get(db,path,params)
                elif path=='/api/summary':payload=store.summary(db)
                elif path=='/api/observations':payload=store.observations(db,params)
                elif path=='/api/observation':payload=store.detail(db,int(params['id']))
                elif path=='/api/schema':payload=store.schema(db)
                elif path=='/api/issues':
                    page=max(1,int(params.get('page',1)));status=params.get('status','open')
                    if status not in ('open','reviewed'):raise ValueError('Check the review status.')
                    total=db.execute('SELECT COUNT(*) FROM quality_issue WHERE status=?',(status,)).fetchone()[0]
                    payload={'total':total,'page':page,'rows':[dict(r) for r in db.execute('SELECT q.*,f.name source_name FROM quality_issue q LEFT JOIN source_file f ON f.id=q.source_id WHERE q.status=? ORDER BY q.id LIMIT 30 OFFSET ?',(status,(page-1)*30))]}
                elif path=='/api/unresolved':
                    sid=int(params['source']);payload=[dict(r) for r in db.execute('SELECT * FROM unresolved_cell WHERE source_id=? LIMIT 500',(sid,))]
                elif path=='/api/weather':
                    year=int(params.get('year',2026));sid=params.get('station','614')
                    if not 2019<=year<=2026:raise ValueError('Weather data cover 2019–2026.')
                    payload={'station':dict(db.execute('SELECT * FROM weather_station WHERE station_id=?',(sid,)).fetchone() or {}),
                        'rows':[dict(r) for r in db.execute('SELECT * FROM weather_daily WHERE station_id=? AND date>=? AND date<=? ORDER BY date',(sid,f'{year}-01-01',f'{year}-12-31'))],
                        'monthly':[dict(r) for r in db.execute('SELECT * FROM weather_monthly WHERE station_id=? AND year=? ORDER BY month',(sid,year))]}
                elif path=='/api/history':payload=[dict(r) for r in db.execute('SELECT * FROM revision_history ORDER BY id DESC LIMIT 100')]
                elif path=='/api/export':
                    data=store.observations(db,params,True)['rows'];buff=io.StringIO(newline='')
                    columns=['id','group_name','label','scientific_name','korean_name','survey_year','survey_month','survey_date','time_precision','measurement_type','value','unit','source_name','row_number','source_column']
                    writer=csv.writer(buff);writer.writerow(columns)
                    for r in data:writer.writerow([csv_safe(r[k]) for k in columns])
                    return self.send(buff.getvalue().encode('utf-8-sig'),ctype='text/csv; charset=utf-8',filename='observations.csv')
                elif path=='/api/backup':
                    fd,tmp=tempfile.mkstemp(suffix='.sqlite');os.close(fd)
                    try:
                        backup=sqlite3.connect(tmp);db.backup(backup);backup.close()
                        raw=Path(tmp).read_bytes()
                    finally:Path(tmp).unlink(missing_ok=True)
                    return self.send(raw,ctype='application/vnd.sqlite3',filename='lmo_ecology_backup.sqlite')
                else:return self.send({'error':'Path not found.'},404)
                self.send(payload)
        except (ValueError,KeyError,TypeError) as error:self.send({'error':str(error)},400)
        except Exception:self.send({'error':'The request could not be completed. Check the input and the database.'},500)
    def do_POST(self):
        try:
            self.checked_host()
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                return self.send({'error':'Requests from other sites are not accepted.'},403)
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),TOKEN):return self.send({'error':'Reload the page and try again.'},403)
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>35*1024*1024:raise ValueError('Input is limited to files of 25 MB or smaller.')
            if self.headers.get_content_type()!='application/json':raise ValueError('A JSON request is required.')
            body=json.loads(self.rfile.read(size));path=urllib.parse.urlsplit(self.path).path
            with closing(store.connect()) as db, db:
                if path=='/api/context':payload=store.set_context(db,body)
                elif path=='/api/facility':
                    name=str(body.get('name','')).strip()
                    if not name:raise ValueError('Enter the facility name.')
                    ident=db.execute('INSERT INTO facility(name,description) VALUES(?,?)',(name,body.get('description',''))).lastrowid
                    store.audit(db,'facility',ident,'create',None,body,'registered by user');payload={'id':ident}
                elif path=='/api/plot':
                    code=str(body.get('code','')).strip();role=body.get('role','unspecified')
                    if not code or role not in ('control','experimental','unspecified'):raise ValueError('Check the plot code and role.')
                    ident=db.execute('INSERT INTO plot(facility_id,code,role,notes) VALUES(?,?,?,?)',(int(body['facility_id']),code,role,body.get('notes',''))).lastrowid
                    store.audit(db,'plot',ident,'create',None,body,'registered by user');payload={'id':ident}
                elif path=='/api/taxon':
                    ident=int(body['id']);old=db.execute('SELECT * FROM taxon WHERE id=?',(ident,)).fetchone()
                    if not old:raise ValueError('Taxon not found.')
                    reason=str(body.get('reason','')).strip()
                    if not reason:raise ValueError('Enter the evidence for the name verification.')
                    sci=str(body.get('scientific_name','')).strip() or None;kor=str(body.get('korean_name','')).strip() or None
                    rank=str(body.get('rank_status','')).strip()
                    if not rank:raise ValueError('Enter the rank or verification status.')
                    new={'scientific_name':sci,'korean_name':kor,'rank_status':rank}
                    db.execute('UPDATE taxon SET scientific_name=?,korean_name=?,rank_status=? WHERE id=?',(sci,kor,rank,ident))
                    store.audit(db,'taxon',ident,'names_and_rank',dict(old),new,reason);payload={'updated':1}
                elif path=='/api/review':
                    ident=int(body['id']);note=str(body.get('note','')).strip()
                    if not note:raise ValueError('Enter the review note.')
                    old=db.execute('SELECT * FROM quality_issue WHERE id=?',(ident,)).fetchone()
                    if not old:raise ValueError('Review item not found.')
                    db.execute("UPDATE quality_issue SET status='reviewed',note=?,reviewed_at=? WHERE id=?",(note,store.now(),ident))
                    store.audit(db,'quality_issue',ident,'review',dict(old),{'status':'reviewed','note':note},note);payload={'updated':1}
                elif path=='/api/import':
                    content=base64.b64decode(body['content'],validate=True)
                    if len(content)>25*1024*1024:raise ValueError('The file must be 25 MB or smaller.')
                    payload=ingest(db,body['filename'],content,body.get('group',''),body.get('year',''))
                else:return self.send({'error':'Path not found.'},404)
            self.send(payload)
        except sqlite3.IntegrityError:self.send({'error':'The item already exists or the linked record is not valid.'},400)
        except (ValueError,KeyError,TypeError) as error:self.send({'error':str(error)},400)
        except Exception:self.send({'error':'The request could not be completed. The database was not changed.'},500)

def main():
    if not store.DB_PATH.exists():raise SystemExit('instance/ecology.sqlite is missing. Extract the whole distribution folder.')
    store.initialize()
    port=int(os.environ.get('LMO_PORT','5083'));server=None
    for p in range(port,port+10):
        try:server=ThreadingHTTPServer(('127.0.0.1',p),Handler);break
        except OSError:continue
    if not server:raise SystemExit('No free port is available.')
    url=f'http://127.0.0.1:{server.server_port}'
    print('LMO confined field ecological database 8.0 — '+url,flush=True)
    if os.environ.get('LMO_NO_BROWSER')!='1':threading.Timer(.7,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
