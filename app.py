from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import os, hashlib, math, threading

app = Flask(__name__)
app.secret_key = 'cxmedia-secret-2024'
app.config['PERMANENT_SESSION_LIFETIME'] = __import__('datetime').timedelta(days=30)
app.config['SESSION_PERMANENT'] = True

def get_belgian_holidays(year):
    from datetime import date, timedelta
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25;g=(b-f+1)//3
    h=(19*a+b-d-g+15)%30;i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    month=(h+l-7*m+114)//31;day=((h+l-7*m+114)%31)+1
    easter=date(year,month,day)
    return [date(year,1,1),easter+timedelta(1),date(year,5,1),easter+timedelta(39),
            easter+timedelta(50),date(year,7,21),date(year,8,15),date(year,11,1),
            date(year,11,11),date(year,12,25)]

def get_working_days(year,month):
    from datetime import date
    import calendar
    holidays=get_belgian_holidays(year)
    _,nd=calendar.monthrange(year,month)
    return sum(1 for d in range(1,nd+1) if date(year,month,d).weekday()<5 and date(year,month,d) not in holidays)

def get_vendable_hours_for_month(wh,year,month):
    return round(wh*get_working_days(year,month)/5,2)

@app.before_request
def _(): pass

DATABASE_URL=os.environ.get('DATABASE_URL','')
print(f"[STARTUP] DATABASE_URL={'SET ('+DATABASE_URL[:30]+'...)' if DATABASE_URL else 'NOT SET'}")

if DATABASE_URL:
    import psycopg2,psycopg2.extras
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL=DATABASE_URL.replace('postgres://','postgresql://',1)
    if '?sslmode=' not in DATABASE_URL and 'sslmode=' not in DATABASE_URL:
        DATABASE_URL+=('?sslmode=require')
    def get_db(): return psycopg2.connect(DATABASE_URL)
    PLACEHOLDER='%s'; USE_PG=True
else:
    import sqlite3
    def get_db():
        c=sqlite3.connect('timetracker.db'); c.row_factory=sqlite3.Row; return c
    PLACEHOLDER='?'; USE_PG=False

def P(n=1): return ', '.join([PLACEHOLDER]*n)

def init_db():
    conn=get_db();c=conn.cursor()
    if USE_PG:
        c.execute("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT DEFAULT 'user',active INTEGER DEFAULT 1,full_name TEXT,email TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS clients (id SERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,active INTEGER DEFAULT 1,collab_start TEXT,collab_end TEXT,dolibarr_name TEXT,address TEXT,contact_name TEXT,contact_phone TEXT,notes_permanentes TEXT,dolibarr_quote_url TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS service_templates (id SERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS mission_types (id SERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL,ref_duration_min INTEGER DEFAULT 60,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS client_services (id SERIAL PRIMARY KEY,client_id INTEGER NOT NULL,template_id INTEGER NOT NULL,monthly_hours REAL DEFAULT 0,note TEXT,UNIQUE(client_id,template_id))")
        c.execute("CREATE TABLE IF NOT EXISTS time_entries (id SERIAL PRIMARY KEY,user_id INTEGER NOT NULL,client_id INTEGER NOT NULL,template_id INTEGER NOT NULL,start_time TEXT NOT NULL,end_time TEXT,duration_minutes REAL DEFAULT 0,pause_minutes REAL DEFAULT 0,is_manual INTEGER DEFAULT 0,justification TEXT,session_id TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS session_colleagues (id SERIAL PRIMARY KEY,session_id TEXT NOT NULL,user_id INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS active_sessions (id SERIAL PRIMARY KEY,user_id INTEGER NOT NULL,session_id TEXT NOT NULL,client_id INTEGER NOT NULL,started_at TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY,value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS collaborator_settings (id SERIAL PRIMARY KEY,user_id INTEGER UNIQUE NOT NULL,hourly_cost REAL DEFAULT 0,vendable_hours REAL DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS dolibarr_cache (id SERIAL PRIMARY KEY,dolibarr_id TEXT UNIQUE NOT NULL,nom TEXT,email TEXT,phone TEXT,address TEXT,zip_code TEXT,town TEXT,country TEXT,last_sync TEXT)")
    else:
        c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT DEFAULT 'user',active INTEGER DEFAULT 1,full_name TEXT,email TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,active INTEGER DEFAULT 1,collab_start TEXT,collab_end TEXT,dolibarr_name TEXT,address TEXT,contact_name TEXT,contact_phone TEXT,notes_permanentes TEXT,dolibarr_quote_url TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS service_templates (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS mission_types (id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL,ref_duration_min INTEGER DEFAULT 60,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS client_services (id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER NOT NULL,template_id INTEGER NOT NULL,monthly_hours REAL DEFAULT 0,note TEXT,UNIQUE(client_id,template_id))")
        c.execute("CREATE TABLE IF NOT EXISTS time_entries (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,client_id INTEGER NOT NULL,template_id INTEGER NOT NULL,start_time TEXT NOT NULL,end_time TEXT,duration_minutes REAL DEFAULT 0,pause_minutes REAL DEFAULT 0,is_manual INTEGER DEFAULT 0,justification TEXT,session_id TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS session_colleagues (id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,user_id INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS active_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,session_id TEXT NOT NULL,client_id INTEGER NOT NULL,started_at TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY,value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS collaborator_settings (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL,hourly_cost REAL DEFAULT 0,vendable_hours REAL DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS dolibarr_cache (id INTEGER PRIMARY KEY AUTOINCREMENT,dolibarr_id TEXT UNIQUE NOT NULL,nom TEXT,email TEXT,phone TEXT,address TEXT,zip_code TEXT,town TEXT,country TEXT,last_sync TEXT)")
    pw=hashlib.sha256('admin123'.encode()).hexdigest()
    try:
        c.execute(f"INSERT INTO users (username,password,role,full_name) VALUES ({P(4)}) ON CONFLICT DO NOTHING" if USE_PG else f"INSERT OR IGNORE INTO users (username,password,role,full_name) VALUES ({P(4)})",('admin',pw,'admin','Administrateur'))
    except: pass
    conn.commit();conn.close()

def migrate_db():
    conn=get_db();c=conn.cursor()
    try:
        if USE_PG:
            for col in ['collab_start TEXT','collab_end TEXT','dolibarr_name TEXT','address TEXT','contact_name TEXT','contact_phone TEXT','notes_permanentes TEXT','dolibarr_quote_url TEXT']:
                c.execute(f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS {col} DEFAULT NULL")
            for col in ['note TEXT','updated_at TEXT']:
                c.execute(f"ALTER TABLE client_services ADD COLUMN IF NOT EXISTS {col} DEFAULT NULL")
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT DEFAULT NULL")
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT DEFAULT NULL")
            c.execute("CREATE TABLE IF NOT EXISTS mission_types (id SERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL,ref_duration_min INTEGER DEFAULT 60,active INTEGER DEFAULT 1)")
            c.execute("CREATE TABLE IF NOT EXISTS dolibarr_cache (id SERIAL PRIMARY KEY,dolibarr_id TEXT UNIQUE NOT NULL,nom TEXT,email TEXT,phone TEXT,address TEXT,zip_code TEXT,town TEXT,country TEXT,last_sync TEXT)")
        else:
            for col in ['collab_start TEXT','collab_end TEXT','dolibarr_name TEXT','address TEXT','contact_name TEXT','contact_phone TEXT','notes_permanentes TEXT','dolibarr_quote_url TEXT']:
                try: c.execute(f"ALTER TABLE clients ADD COLUMN {col} DEFAULT NULL")
                except: pass
            for col in ['note TEXT','updated_at TEXT']:
                try: c.execute(f"ALTER TABLE client_services ADD COLUMN {col} DEFAULT NULL")
                except: pass
            try: c.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT NULL")
            except: pass
            try: c.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT NULL")
            except: pass
            c.execute("CREATE TABLE IF NOT EXISTS mission_types (id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL,ref_duration_min INTEGER DEFAULT 60,active INTEGER DEFAULT 1)")
            c.execute("CREATE TABLE IF NOT EXISTS dolibarr_cache (id INTEGER PRIMARY KEY AUTOINCREMENT,dolibarr_id TEXT UNIQUE NOT NULL,nom TEXT,email TEXT,phone TEXT,address TEXT,zip_code TEXT,town TEXT,country TEXT,last_sync TEXT)")
        conn.commit();print("[MIGRATE] OK")
    except Exception as e: print(f"[MIGRATE] {e}")
    conn.close()

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a,**k)
    return d

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def d(*a,**k):
        if 'user_id' not in session or session.get('role')!='admin':
            return redirect(url_for('index'))
        return f(*a,**k)
    return d

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route('/login',methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        username=request.form['username'];password=hash_pw(request.form['password'])
        conn=get_db();c=conn.cursor()
        c.execute(f"SELECT id,username,role FROM users WHERE username={PLACEHOLDER} AND password={PLACEHOLDER} AND active=1",(username,password))
        user=c.fetchone();conn.close()
        if user:
            session['user_id']=user[0] if USE_PG else user['id']
            session['username']=user[1] if USE_PG else user['username']
            session['role']=user[2] if USE_PG else user['role']
            return redirect(url_for('index'))
        error="Identifiants incorrects."
    return render_template('login.html',error=error)

@app.route('/logout')
def logout():
    session.clear();return redirect(url_for('login'))

# ── TIMER ─────────────────────────────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    conn=get_db();c=conn.cursor()
    c.execute("SELECT id,name FROM clients WHERE active=1 ORDER BY name")
    cr=c.fetchall()
    c.execute("SELECT id,username FROM users WHERE active=1 ORDER BY username")
    ur=c.fetchall();conn.close()
    clients=[{'id':r[0],'name':r[1]} for r in cr] if USE_PG else [dict(r) for r in cr]
    users=[{'id':r[0],'username':r[1]} for r in ur] if USE_PG else [dict(r) for r in ur]
    return render_template('index.html',clients=clients,users=users)

@app.route('/get_services/<int:client_id>')
@login_required
def get_services(client_id):
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT cs.id,st.name,cs.monthly_hours FROM client_services cs JOIN service_templates st ON cs.template_id=st.id WHERE cs.client_id={PLACEHOLDER} ORDER BY st.name",(client_id,))
    rows=c.fetchall();conn.close()
    return jsonify([{'id':r[0],'name':r[1],'monthly_hours':r[2]} for r in rows] if USE_PG else [dict(r) for r in rows])

@app.route('/start_timer',methods=['POST'])
@login_required
def start_timer():
    import uuid
    data=request.get_json();client_id=data['client_id'];service_id=data['service_id']
    colleagues=data.get('colleagues',[])
    conn=get_db();c=conn.cursor()
    all_users=[session['user_id']]+colleagues;conflicts=[]
    for uid in all_users:
        c.execute(f"SELECT client_id FROM active_sessions WHERE user_id={PLACEHOLDER}",(uid,))
        ex=c.fetchone()
        if ex:
            ecid=ex[0] if USE_PG else ex['client_id']
            c.execute(f"SELECT username FROM users WHERE id={PLACEHOLDER}",(uid,));ur=c.fetchone()
            c.execute(f"SELECT name FROM clients WHERE id={PLACEHOLDER}",(ecid,));cr=c.fetchone()
            uname=ur[0] if USE_PG else ur['username'];cname=cr[0] if USE_PG else cr['name']
            conflicts.append(f"{'Vous êtes' if uid==session['user_id'] else uname+' est'} déjà en session sur {cname}")
    if conflicts: conn.close();return jsonify({'error':' | '.join(conflicts)}),409
    sid=str(uuid.uuid4())
    now=data.get('started_at',datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'))
    if 'Z' in now or '.' in now: now=now.replace('Z','').split('.')[0]
    c.execute(f"SELECT template_id FROM client_services WHERE id={PLACEHOLDER}",(service_id,))
    row=c.fetchone();template_id=row[0] if USE_PG else row['template_id']
    for uid in colleagues: c.execute(f"INSERT INTO session_colleagues (session_id,user_id) VALUES ({P(2)})",(sid,uid))
    for uid in all_users: c.execute(f"INSERT INTO active_sessions (user_id,session_id,client_id,started_at) VALUES ({P(4)})",(uid,sid,client_id,now))
    conn.commit();conn.close()
    return jsonify({'session_id':sid,'template_id':template_id,'client_id':client_id})

@app.route('/stop_timer',methods=['POST'])
@login_required
def stop_timer():
    data=request.get_json();sid=data['session_id'];client_id=data['client_id']
    template_id=data['template_id'];start_raw=data['start_time'];end_raw=data.get('end_time','')
    pause=float(data.get('pause_minutes',0));justification=data.get('justification','')
    def ci(ts):
        ts=ts.replace('Z','')
        if '.' in ts: ts=ts.split('.')[0]
        return ts
    st=ci(start_raw);et=ci(end_raw) if end_raw else ci(start_raw)
    net=max(0,(datetime.fromisoformat(et)-datetime.fromisoformat(st)).total_seconds()-pause*60)
    nm=math.ceil(net/60)
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT user_id FROM session_colleagues WHERE session_id={PLACEHOLDER}",(sid,))
    cols=c.fetchall()
    uids=list(set([session['user_id']]+[r[0] if USE_PG else r['user_id'] for r in cols]))
    for uid in uids:
        c.execute(f"INSERT INTO time_entries (user_id,client_id,template_id,start_time,end_time,duration_minutes,pause_minutes,is_manual,justification,session_id) VALUES ({P(10)})",(uid,client_id,template_id,st,et,nm,pause,0,justification,sid))
        c.execute(f"DELETE FROM active_sessions WHERE user_id={PLACEHOLDER}",(uid,))
    conn.commit();conn.close()
    return jsonify({'success':True,'duration_minutes':round(nm,2)})

@app.route('/quick_entry',methods=['POST'])
@login_required
def quick_entry():
    import uuid
    data=request.get_json();client_id=data['client_id'];service_id=data['service_id']
    colleagues=data.get('colleagues',[]);dur=float(data.get('duration_minutes',0))
    justification=data.get('justification','')
    def ci(ts):
        ts=ts.replace('Z','')
        if '.' in ts: ts=ts.split('.')[0]
        return ts
    st=ci(data['start_time']);et=ci(data['end_time'])
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT template_id FROM client_services WHERE id={PLACEHOLDER}",(service_id,))
    row=c.fetchone()
    if not row: conn.close();return jsonify({'error':'Service introuvable'}),404
    tid=row[0] if USE_PG else row['template_id']
    sid=str(uuid.uuid4());uids=list(set([session['user_id']]+colleagues))
    for uid in uids:
        c.execute(f"INSERT INTO time_entries (user_id,client_id,template_id,start_time,end_time,duration_minutes,pause_minutes,is_manual,justification,session_id) VALUES ({P(10)})",(uid,client_id,tid,st,et,dur,0,1,justification,sid))
    conn.commit();conn.close()
    return jsonify({'success':True,'duration_minutes':dur})

@app.route('/my_active_session')
@login_required
def my_active_session():
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT a.session_id,a.client_id,a.started_at,cl.name FROM active_sessions a JOIN clients cl ON a.client_id=cl.id WHERE a.user_id={PLACEHOLDER}",(session['user_id'],))
    row=c.fetchone()
    if not row: conn.close();return jsonify({'active':False})
    sid=row[0] if USE_PG else row['session_id'];cid=row[1] if USE_PG else row['client_id']
    sat=row[2] if USE_PG else row['started_at'];cname=row[3] if USE_PG else row['name']
    c.execute(f"SELECT cs.id,st.name,cs.template_id FROM client_services cs JOIN service_templates st ON cs.template_id=st.id WHERE cs.client_id={PLACEHOLDER}",(cid,))
    svcs=c.fetchall();conn.close()
    return jsonify({'active':True,'session_id':sid,'client_id':cid,'client_name':cname,'started_at':str(sat),
        'services':[{'id':r[0] if USE_PG else r['id'],'name':r[1] if USE_PG else r['name'],'template_id':r[2] if USE_PG else r['template_id']} for r in svcs]})

@app.route('/active_users')
@login_required
def active_users():
    conn=get_db();c=conn.cursor()
    c.execute("SELECT a.user_id,u.username,cl.name,st.name,a.started_at FROM active_sessions a JOIN users u ON a.user_id=u.id JOIN clients cl ON a.client_id=cl.id LEFT JOIN client_services cs ON cs.client_id=a.client_id LEFT JOIN service_templates st ON cs.template_id=st.id ORDER BY a.started_at ASC")
    rows=c.fetchall();conn.close()
    seen=set();result=[]
    for r in rows:
        uid=r[0] if USE_PG else r['user_id']
        if uid not in seen:
            seen.add(uid)
            result.append({'user_id':uid,'username':r[1] if USE_PG else r['username'],
                'client_name':r[2] if USE_PG else r['name'],
                'service_name':(r[3] if USE_PG else r['service_name']) or '',
                'started_at':str(r[4] if USE_PG else r['started_at'])})
    return jsonify(result)

# ── RECORDS ───────────────────────────────────────────────────────────────────
@app.route('/records')
@login_required
def records():
    conn=get_db();c=conn.cursor()
    c.execute("SELECT id,name FROM clients WHERE active=1 ORDER BY name");cr=c.fetchall()
    c.execute("SELECT id,username FROM users WHERE active=1 ORDER BY username");ur=c.fetchall()
    c.execute("SELECT id,name FROM service_templates WHERE active=1 ORDER BY name");tr=c.fetchall()
    clients=[{'id':r[0],'name':r[1]} for r in cr] if USE_PG else [dict(r) for r in cr]
    users=[{'id':r[0],'username':r[1]} for r in ur] if USE_PG else [dict(r) for r in ur]
    templates=[{'id':r[0],'name':r[1]} for r in tr] if USE_PG else [dict(r) for r in tr]
    today=datetime.now().strftime('%Y-%m-%d')
    df=request.args.get('date_from',today);dt=request.args.get('date_to',today)
    month=request.args.get('month','');cid=request.args.get('client_id','')
    tid=request.args.get('template_id','');uf=request.args.get('user_id','')
    sql="""SELECT te.id,te.start_time,te.end_time,te.duration_minutes,te.pause_minutes,
        te.is_manual,te.justification,te.session_id,u.username,c.name,st.name,
        te.client_id,te.template_id,te.user_id,cs.note
        FROM time_entries te JOIN users u ON te.user_id=u.id JOIN clients c ON te.client_id=c.id
        JOIN service_templates st ON te.template_id=st.id
        LEFT JOIN client_services cs ON cs.client_id=te.client_id AND cs.template_id=te.template_id WHERE 1=1"""
    params=[]
    if session.get('role')!='admin': sql+=f" AND te.user_id={PLACEHOLDER}";params.append(session['user_id'])
    elif uf: sql+=f" AND te.user_id={PLACEHOLDER}";params.append(uf)
    if df:
        sql+=f" AND CAST(te.start_time AS DATE)>={PLACEHOLDER}" if USE_PG else f" AND DATE(te.start_time)>={PLACEHOLDER}";params.append(df)
    if dt:
        sql+=f" AND CAST(te.start_time AS DATE)<={PLACEHOLDER}" if USE_PG else f" AND DATE(te.start_time)<={PLACEHOLDER}";params.append(dt)
    if month:
        sql+=f" AND TO_CHAR(CAST(te.start_time AS TIMESTAMP),'YYYY-MM')={PLACEHOLDER}" if USE_PG else f" AND strftime('%Y-%m',te.start_time)={PLACEHOLDER}";params.append(month)
    if cid: sql+=f" AND te.client_id={PLACEHOLDER}";params.append(cid)
    if tid: sql+=f" AND te.template_id={PLACEHOLDER}";params.append(tid)
    sql+=" ORDER BY te.start_time DESC"
    c.execute(sql,params);rows=c.fetchall();entries=[]
    for r in rows:
        if USE_PG: entries.append({'id':r[0],'start_time':str(r[1]),'end_time':str(r[2]),'duration_minutes':r[3],'pause_minutes':r[4],'is_manual':r[5],'justification':r[6],'session_id':r[7],'username':r[8],'client_name':r[9],'service_name':r[10],'client_id':r[11],'template_id':r[12],'user_id':r[13],'service_note':r[14] or ''})
        else: entries.append(dict(r))
    stats={}
    for e in entries:
        key=(e['client_name'],e['service_name'],e['client_id'],e['template_id'])
        if key not in stats: stats[key]={'total_minutes':0,'monthly_hours':0,'note':e.get('service_note','')}
        stats[key]['total_minutes']+=e['duration_minutes']
    for key in stats:
        c.execute(f"SELECT monthly_hours,note FROM client_services WHERE client_id={PLACEHOLDER} AND template_id={PLACEHOLDER}",(key[2],key[3]))
        row=c.fetchone()
        if row: stats[key]['monthly_hours']=row[0] if USE_PG else row['monthly_hours'];stats[key]['note']=(row[1] if USE_PG else row['note']) or ''
    conn.close()
    return render_template('records.html',entries=entries,stats=stats,clients=clients,users=users,templates=templates,
        filters={'date_from':df,'date_to':dt,'month':month,'client_id':cid,'template_id':tid,'user_id':uf})

# ── ADMIN INTERNE ─────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin():
    conn=get_db();c=conn.cursor()
    c.execute("SELECT id,username,role,active,full_name,email FROM users ORDER BY username");ur=c.fetchall()
    c.execute("SELECT id,name,active,address,contact_name,contact_phone,notes_permanentes,dolibarr_name FROM clients ORDER BY name");cr=c.fetchall()
    c.execute("SELECT id,name,active FROM service_templates ORDER BY name");tr=c.fetchall()
    c.execute("SELECT id,code,label,ref_duration_min,active FROM mission_types ORDER BY code");mr=c.fetchall()
    c.execute("SELECT cs.id,cs.client_id,cs.template_id,cs.monthly_hours,c.name,st.name FROM client_services cs JOIN clients c ON cs.client_id=c.id JOIN service_templates st ON cs.template_id=st.id ORDER BY c.name,st.name");csr=c.fetchall()
    conn.close()
    if USE_PG:
        users=[{'id':r[0],'username':r[1],'role':r[2],'active':r[3],'full_name':r[4],'email':r[5]} for r in ur]
        clients=[{'id':r[0],'name':r[1],'active':r[2],'address':r[3],'contact_name':r[4],'contact_phone':r[5],'notes_permanentes':r[6],'dolibarr_name':r[7]} for r in cr]
        templates=[{'id':r[0],'name':r[1],'active':r[2]} for r in tr]
        mission_types=[{'id':r[0],'code':r[1],'label':r[2],'ref_duration_min':r[3],'active':r[4]} for r in mr]
        client_services=[{'id':r[0],'client_id':r[1],'template_id':r[2],'monthly_hours':r[3],'client_name':r[4],'service_name':r[5]} for r in csr]
    else:
        users=[dict(r) for r in ur];clients=[dict(r) for r in cr];templates=[dict(r) for r in tr]
        mission_types=[dict(r) for r in mr];client_services=[dict(r) for r in csr]
    return render_template('admin.html',users=users,clients=clients,templates=templates,mission_types=mission_types,client_services=client_services)

# ── USERS ─────────────────────────────────────────────────────────────────────
@app.route('/admin/user/add',methods=['POST'])
@admin_required
def user_add():
    username=request.form['username'];password=hash_pw(request.form['password'])
    role=request.form.get('role','user');full_name=request.form.get('full_name','')
    email=request.form.get('email','')
    conn=get_db();c=conn.cursor()
    try:
        c.execute(f"INSERT INTO users (username,password,role,full_name,email) VALUES ({P(5)})",(username,password,role,full_name,email))
        conn.commit()
    except: pass
    conn.close();return redirect(url_for('admin'))

@app.route('/admin/user/edit/<int:uid>',methods=['POST'])
@admin_required
def user_edit(uid):
    role=request.form.get('role','user');full_name=request.form.get('full_name','')
    email=request.form.get('email','');pw=request.form.get('password','').strip()
    conn=get_db();c=conn.cursor()
    if pw:
        c.execute(f"UPDATE users SET role={PLACEHOLDER},full_name={PLACEHOLDER},email={PLACEHOLDER},password={PLACEHOLDER} WHERE id={PLACEHOLDER}",(role,full_name,email,hash_pw(pw),uid))
    else:
        c.execute(f"UPDATE users SET role={PLACEHOLDER},full_name={PLACEHOLDER},email={PLACEHOLDER} WHERE id={PLACEHOLDER}",(role,full_name,email,uid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/user/toggle/<int:uid>',methods=['POST'])
@admin_required
def user_toggle(uid):
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT active FROM users WHERE id={PLACEHOLDER}",(uid,));row=c.fetchone()
    active=row[0] if USE_PG else row['active']
    c.execute(f"UPDATE users SET active={PLACEHOLDER} WHERE id={PLACEHOLDER}",(1-active,uid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/user/delete/<int:uid>',methods=['POST'])
@admin_required
def user_delete(uid):
    conn=get_db();c=conn.cursor()
    c.execute(f"DELETE FROM users WHERE id={PLACEHOLDER}",(uid,))
    conn.commit();conn.close();return redirect(url_for('admin'))

# ── CLIENTS ───────────────────────────────────────────────────────────────────
@app.route('/admin/client/add',methods=['POST'])
@admin_required
def client_add():
    name=request.form['name'];address=request.form.get('address','') or None
    contact_name=request.form.get('contact_name','') or None;contact_phone=request.form.get('contact_phone','') or None
    notes=request.form.get('notes_permanentes','') or None
    conn=get_db();c=conn.cursor()
    try:
        c.execute(f"INSERT INTO clients (name,address,contact_name,contact_phone,notes_permanentes) VALUES ({P(5)})",(name,address,contact_name,contact_phone,notes))
        conn.commit()
    except Exception as e: print(f"client_add: {e}")
    conn.close();return redirect(url_for('admin'))

@app.route('/admin/client/edit/<int:cid>',methods=['POST'])
@admin_required
def client_edit(cid):
    name=request.form.get('name','').strip()
    dolibarr_name=request.form.get('dolibarr_name','').strip() or None
    address=request.form.get('address','').strip() or None
    contact_name=request.form.get('contact_name','').strip() or None
    contact_phone=request.form.get('contact_phone','').strip() or None
    notes=request.form.get('notes_permanentes','').strip() or None
    conn=get_db();c=conn.cursor()
    c.execute(f"UPDATE clients SET name={PLACEHOLDER},dolibarr_name={PLACEHOLDER},address={PLACEHOLDER},contact_name={PLACEHOLDER},contact_phone={PLACEHOLDER},notes_permanentes={PLACEHOLDER} WHERE id={PLACEHOLDER}",(name,dolibarr_name,address,contact_name,contact_phone,notes,cid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/client/toggle/<int:cid>',methods=['POST'])
@admin_required
def client_toggle(cid):
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT active FROM clients WHERE id={PLACEHOLDER}",(cid,));row=c.fetchone()
    active=row[0] if USE_PG else row['active']
    c.execute(f"UPDATE clients SET active={PLACEHOLDER} WHERE id={PLACEHOLDER}",(1-active,cid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/client/delete/<int:cid>',methods=['POST'])
@admin_required
def client_delete(cid):
    conn=get_db();c=conn.cursor()
    c.execute(f"DELETE FROM clients WHERE id={PLACEHOLDER}",(cid,))
    conn.commit();conn.close();return redirect(url_for('admin'))

# ── MISSION TYPES ─────────────────────────────────────────────────────────────
@app.route('/admin/mission-type/add',methods=['POST'])
@admin_required
def mission_type_add():
    code=request.form['code'];label=request.form['label']
    ref=int(request.form.get('ref_duration_min',60))
    conn=get_db();c=conn.cursor()
    try:
        c.execute(f"INSERT INTO mission_types (code,label,ref_duration_min) VALUES ({P(3)})",(code,label,ref))
        conn.commit()
    except: pass
    conn.close();return redirect(url_for('admin'))

@app.route('/admin/mission-type/edit/<int:tid>',methods=['POST'])
@admin_required
def mission_type_edit(tid):
    code=request.form['code'];label=request.form['label']
    ref=int(request.form.get('ref_duration_min',60))
    conn=get_db();c=conn.cursor()
    c.execute(f"UPDATE mission_types SET code={PLACEHOLDER},label={PLACEHOLDER},ref_duration_min={PLACEHOLDER} WHERE id={PLACEHOLDER}",(code,label,ref,tid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/mission-type/toggle/<int:tid>',methods=['POST'])
@admin_required
def mission_type_toggle(tid):
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT active FROM mission_types WHERE id={PLACEHOLDER}",(tid,));row=c.fetchone()
    active=row[0] if USE_PG else row['active']
    c.execute(f"UPDATE mission_types SET active={PLACEHOLDER} WHERE id={PLACEHOLDER}",(1-active,tid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/mission-type/delete/<int:tid>',methods=['POST'])
@admin_required
def mission_type_delete(tid):
    conn=get_db();c=conn.cursor()
    c.execute(f"DELETE FROM mission_types WHERE id={PLACEHOLDER}",(tid,))
    conn.commit();conn.close();return redirect(url_for('admin'))

# ── SERVICES ──────────────────────────────────────────────────────────────────
@app.route('/admin/add_service',methods=['POST'])
@admin_required
def add_service():
    client_id=request.form['client_id'];template_id=request.form['template_id']
    monthly_hours=float(request.form.get('monthly_hours',0))
    conn=get_db();c=conn.cursor()
    try:
        c.execute(f"INSERT INTO client_services (client_id,template_id,monthly_hours) VALUES ({P(3)})",(client_id,template_id,monthly_hours))
        conn.commit()
    except: pass
    conn.close();return redirect(url_for('admin'))

@app.route('/admin/edit_service/<int:csid>',methods=['POST'])
@admin_required
def edit_service(csid):
    monthly_hours=float(request.form.get('monthly_hours',0))
    updated_at=datetime.now().strftime('%Y-%m-%d %H:%M')
    conn=get_db();c=conn.cursor()
    c.execute(f"UPDATE client_services SET monthly_hours={PLACEHOLDER},updated_at={PLACEHOLDER} WHERE id={PLACEHOLDER}",(monthly_hours,updated_at,csid))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/delete_service/<int:csid>')
@admin_required
def delete_service(csid):
    conn=get_db();c=conn.cursor()
    c.execute(f"DELETE FROM client_services WHERE id={PLACEHOLDER}",(csid,))
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/get_client_assignments/<int:client_id>')
@admin_required
def get_client_assignments(client_id):
    conn=get_db();c=conn.cursor()
    c.execute("SELECT id,name FROM service_templates WHERE active=1 ORDER BY name");all_t=c.fetchall()
    c.execute(f"SELECT template_id,monthly_hours,note FROM client_services WHERE client_id={PLACEHOLDER}",(client_id,));asgn=c.fetchall()
    conn.close()
    if USE_PG:
        assigned={r[0]:{'monthly_hours':r[1],'note':r[2]} for r in asgn}
        return jsonify([{'template_id':t[0],'name':t[1],'assigned':t[0] in assigned,'monthly_hours':assigned.get(t[0],{}).get('monthly_hours',0),'note':assigned.get(t[0],{}).get('note','')} for t in all_t])
    assigned={r['template_id']:{'monthly_hours':r['monthly_hours'],'note':r['note']} for r in asgn}
    return jsonify([{'template_id':t['id'],'name':t['name'],'assigned':t['id'] in assigned,'monthly_hours':assigned.get(t['id'],{}).get('monthly_hours',0),'note':assigned.get(t['id'],{}).get('note','')} for t in all_t])

# ── ENTRIES ───────────────────────────────────────────────────────────────────
@app.route('/admin/manual_entry',methods=['POST'])
@admin_required
def manual_entry():
    import uuid
    user_id=request.form['user_id'];client_id=request.form['client_id'];template_id=request.form['template_id']
    date_str=request.form['date'];sh=request.form['start_hour'];eh=request.form['end_hour']
    colleagues=request.form.getlist('colleagues');justification=request.form.get('justification','')
    st=f"{date_str}T{sh}:00";et=f"{date_str}T{eh}:00"
    dur=max(0,(datetime.fromisoformat(et)-datetime.fromisoformat(st)).total_seconds()/60)
    sid=str(uuid.uuid4());uids=list(set([user_id]+colleagues))
    conn=get_db();c=conn.cursor()
    for uid in uids:
        c.execute(f"INSERT INTO time_entries (user_id,client_id,template_id,start_time,end_time,duration_minutes,pause_minutes,is_manual,justification,session_id) VALUES ({P(10)})",(uid,client_id,template_id,st,et,dur,0,1,justification,sid))
    conn.commit();conn.close();return redirect(url_for('records'))

@app.route('/admin/edit_entry/<int:eid>',methods=['POST'])
@admin_required
def edit_entry(eid):
    date_str=request.form['date'];sh=request.form['start_hour'];eh=request.form['end_hour']
    justification=request.form.get('justification','')
    st=f"{date_str}T{sh}:00";et=f"{date_str}T{eh}:00"
    md=request.form.get('manual_duration','').strip()
    dur=max(0,float(md)) if md else max(0,(datetime.fromisoformat(et)-datetime.fromisoformat(st)).total_seconds()/60)
    conn=get_db();c=conn.cursor()
    c.execute(f"UPDATE time_entries SET start_time={PLACEHOLDER},end_time={PLACEHOLDER},duration_minutes={PLACEHOLDER},justification={PLACEHOLDER} WHERE id={PLACEHOLDER}",(st,et,dur,justification,eid))
    conn.commit();conn.close();return redirect(url_for('records'))

@app.route('/admin/delete_entry/<int:eid>')
@admin_required
def delete_entry(eid):
    conn=get_db();c=conn.cursor()
    c.execute(f"DELETE FROM time_entries WHERE id={PLACEHOLDER}",(eid,))
    conn.commit();conn.close();return redirect(url_for('records'))

@app.route('/admin/clear_sessions',methods=['POST'])
@admin_required
def clear_sessions():
    user_id=request.form.get('user_id','')
    conn=get_db();c=conn.cursor()
    if user_id: c.execute(f"DELETE FROM active_sessions WHERE user_id={PLACEHOLDER}",(user_id,))
    else: c.execute("DELETE FROM active_sessions")
    conn.commit();conn.close();return redirect(url_for('admin'))

@app.route('/admin/reset-test',methods=['POST'])
@admin_required
def reset_test():
    conn=get_db();c=conn.cursor()
    c.execute("DELETE FROM time_entries")
    c.execute("DELETE FROM active_sessions")
    c.execute("DELETE FROM session_colleagues")
    conn.commit();conn.close();return redirect(url_for('admin'))

# ── DOLIBARR SYNC ─────────────────────────────────────────────────────────────
_sync_status={'running':False,'done':False,'imported':0,'updated':0,'message':''}

@app.route('/admin/sync-dolibarr',methods=['POST'])
@admin_required
def sync_dolibarr():
    global _sync_status
    if _sync_status.get('running'):
        return jsonify({'error':'Sync déjà en cours'}),409
    def do_sync():
        global _sync_status
        _sync_status={'running':True,'done':False,'imported':0,'updated':0,'message':'Synchronisation en cours...'}
        try:
            import requests as req
            DURL=os.environ.get('DOLIBARR_URL','https://client.cx-com.be')
            DKEY=os.environ.get('DOLIBARR_KEY','')
            headers={'DOLAPIKEY':DKEY,'Accept':'application/json'}
            page=0;all_clients=[]
            while True:
                resp=req.get(f"{DURL}/api/index.php/thirdparties",headers=headers,
                    params={'limit':100,'page':page,'sortfield':'t.nom','sortorder':'ASC'},timeout=15)
                if resp.status_code!=200:
                    _sync_status['message']=f"Erreur API: {resp.status_code}";_sync_status['running']=False;return
                data=resp.json()
                if not data: break
                all_clients.extend(data)
                if len(data)<100: break
                page+=1
            conn=get_db();c=conn.cursor()
            imported=0;updated=0;now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for cl in all_clients:
                did=str(cl.get('id',''));nom=cl.get('name','') or cl.get('nom','') or ''
                email=cl.get('email','') or '';phone=cl.get('phone','') or ''
                address=cl.get('address','') or '';zip_code=cl.get('zip','') or ''
                town=cl.get('town','') or ''
                country=cl.get('country',{}).get('label','') if isinstance(cl.get('country'),dict) else ''
                c.execute(f"SELECT id FROM dolibarr_cache WHERE dolibarr_id={PLACEHOLDER}",(did,))
                ex=c.fetchone()
                if ex:
                    c.execute(f"UPDATE dolibarr_cache SET nom={PLACEHOLDER},email={PLACEHOLDER},phone={PLACEHOLDER},address={PLACEHOLDER},zip_code={PLACEHOLDER},town={PLACEHOLDER},country={PLACEHOLDER},last_sync={PLACEHOLDER} WHERE dolibarr_id={PLACEHOLDER}",(nom,email,phone,address,zip_code,town,country,now,did))
                    updated+=1
                else:
                    c.execute(f"INSERT INTO dolibarr_cache (dolibarr_id,nom,email,phone,address,zip_code,town,country,last_sync) VALUES ({P(9)})",(did,nom,email,phone,address,zip_code,town,country,now))
                    imported+=1
            conn.commit();conn.close()
            _sync_status={'running':False,'done':True,'imported':imported,'updated':updated,
                'message':f"✅ Sync terminée — {imported} nouveaux, {updated} mis à jour"}
        except Exception as e:
            _sync_status={'running':False,'done':True,'imported':0,'updated':0,'message':f"❌ Erreur: {str(e)}"}
    t=threading.Thread(target=do_sync);t.daemon=True;t.start()
    return jsonify({'ok':True,'message':'Sync démarrée en arrière-plan'})

@app.route('/admin/sync-status')
@admin_required
def sync_status():
    return jsonify(_sync_status)

@app.route('/admin/search-dolibarr')
@admin_required
def search_dolibarr():
    q=request.args.get('q','').strip().lower()
    if len(q)<2: return jsonify([])
    conn=get_db();c=conn.cursor()
    if USE_PG:
        c.execute("SELECT dolibarr_id,nom,email,town FROM dolibarr_cache WHERE LOWER(nom) LIKE %s ORDER BY nom LIMIT 10",(f'%{q}%',))
    else:
        c.execute("SELECT dolibarr_id,nom,email,town FROM dolibarr_cache WHERE LOWER(nom) LIKE ? ORDER BY nom LIMIT 10",(f'%{q}%',))
    rows=c.fetchall();conn.close()
    return jsonify([{'id':r[0],'nom':r[1],'name':r[1],'email':r[2],'town':r[3]} for r in rows] if USE_PG else [dict(r) for r in rows])

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@admin_required
def dashboard():
    conn=get_db();c=conn.cursor()
    month=request.args.get('month','');df=request.args.get('date_from','');dt=request.args.get('date_to','');uf=request.args.get('user_id','')
    if not month and not df and not dt: month=datetime.now().strftime('%Y-%m')
    c.execute("SELECT id,username FROM users WHERE active=1 ORDER BY username");ur=c.fetchall()
    users=[{'id':r[0],'username':r[1]} for r in ur] if USE_PG else [dict(r) for r in ur]
    c.execute("SELECT user_id,hourly_cost,vendable_hours FROM collaborator_settings");sr=c.fetchall()
    settings={}
    for r in sr:
        uid=r[0] if USE_PG else r['user_id']
        settings[uid]={'hourly_cost':r[1] if USE_PG else r['hourly_cost'],'vendable_hours':r[2] if USE_PG else r['vendable_hours']}
    TARIF=75.0
    if month: yi,mi=int(month[:4]),int(month[5:7])
    else:
        ref=df or datetime.now().strftime('%Y-%m-%d');yi,mi=int(ref[:4]),int(ref[5:7])
    wd=get_working_days(yi,mi);ww=round(wd/5,2)
    sql="""SELECT te.user_id,u.username,SUM(te.duration_minutes),te.client_id,c.name,te.template_id,st.name
        FROM time_entries te JOIN users u ON te.user_id=u.id JOIN clients c ON te.client_id=c.id
        JOIN service_templates st ON te.template_id=st.id WHERE 1=1"""
    params=[]
    if df or dt:
        if df:
            sql+=f" AND CAST(te.start_time AS DATE)>={PLACEHOLDER}" if USE_PG else f" AND DATE(te.start_time)>={PLACEHOLDER}";params.append(df)
        if dt:
            sql+=f" AND CAST(te.start_time AS DATE)<={PLACEHOLDER}" if USE_PG else f" AND DATE(te.start_time)<={PLACEHOLDER}";params.append(dt)
    else:
        sql+=f" AND TO_CHAR(CAST(te.start_time AS TIMESTAMP),'YYYY-MM')={PLACEHOLDER}" if USE_PG else f" AND strftime('%Y-%m',te.start_time)={PLACEHOLDER}";params.append(month)
    if uf: sql+=f" AND te.user_id={PLACEHOLDER}";params.append(uf)
    sql+=" GROUP BY te.user_id,u.username,te.client_id,c.name,te.template_id,st.name"
    c.execute(sql,params);rows=c.fetchall();collab_stats={}
    for r in rows:
        uid=r[0] if USE_PG else r['user_id'];uname=r[1] if USE_PG else r['username']
        total_h=(r[2] if USE_PG else r['total_minutes'] or 0)/60
        s=settings.get(uid,{'hourly_cost':0,'vendable_hours':0});vh=round(s['vendable_hours']*ww,2)
        if uid not in collab_stats:
            collab_stats[uid]={'username':uname,'total_hours':0,'vendable_hours_week':s['vendable_hours'],'vendable_hours':vh,'working_weeks':ww,'working_days':wd,'hourly_cost':s['hourly_cost'],'ca_realise':0,'ca_attendu':vh*TARIF,'cout_total':0,'marge':0}
        collab_stats[uid]['total_hours']+=total_h;collab_stats[uid]['ca_realise']+=total_h*TARIF;collab_stats[uid]['cout_total']+=total_h*s['hourly_cost']
    for uid in collab_stats:
        cs=collab_stats[uid];cs['marge']=cs['ca_realise']-cs['cout_total']
        cs['taux_realisation']=round(cs['total_hours']/cs['vendable_hours']*100,1) if cs['vendable_hours']>0 else 0
    csql="""SELECT cs.client_id,cl.name,cs.template_id,st.name,cs.monthly_hours,COALESCE(SUM(te.duration_minutes),0)
        FROM client_services cs JOIN clients cl ON cs.client_id=cl.id JOIN service_templates st ON cs.template_id=st.id
        LEFT JOIN time_entries te ON te.client_id=cs.client_id AND te.template_id=cs.template_id"""
    cparams=[]
    if df or dt:
        conds=[]
        if df:
            conds.append(f"CAST(te.start_time AS DATE)>={PLACEHOLDER}" if USE_PG else f"DATE(te.start_time)>={PLACEHOLDER}");cparams.append(df)
        if dt:
            conds.append(f"CAST(te.start_time AS DATE)<={PLACEHOLDER}" if USE_PG else f"DATE(te.start_time)<={PLACEHOLDER}");cparams.append(dt)
        if conds: csql+=" AND ("+" AND ".join(conds)+")"
    else:
        csql+=f" AND TO_CHAR(CAST(te.start_time AS TIMESTAMP),'YYYY-MM')={PLACEHOLDER}" if USE_PG else f" AND strftime('%Y-%m',te.start_time)={PLACEHOLDER}";cparams.append(month)
    csql+=" GROUP BY cs.client_id,cl.name,cs.template_id,st.name,cs.monthly_hours ORDER BY cl.name"
    c.execute(csql,cparams);crows=c.fetchall();client_stats={}
    for r in crows:
        cid=r[0] if USE_PG else r['client_id'];cname=r[1] if USE_PG else r['name']
        sname=r[3] if USE_PG else r[3];qh=r[4] if USE_PG else r['monthly_hours']
        ph=(r[5] if USE_PG else r[5] or 0)/60
        if cid not in client_stats: client_stats[cid]={'name':cname,'budget':0,'ca_realise':0,'hours_quota':0,'hours_prested':0,'services':[]}
        client_stats[cid]['budget']+=qh*TARIF;client_stats[cid]['ca_realise']+=ph*TARIF
        client_stats[cid]['hours_quota']+=qh;client_stats[cid]['hours_prested']+=ph
        client_stats[cid]['services'].append({'name':sname,'quota_h':qh,'prested_h':round(ph,2),'budget':qh*TARIF,'taux_horaire':round(qh*TARIF/ph if ph>0 else 0,2)})
    conn.close()
    return render_template('dashboard.html',users=users,settings=settings,collab_stats=collab_stats,client_stats=client_stats,
        month=month,user_filter=uf,date_from=df,date_to=dt,TARIF=TARIF,working_days=wd,working_weeks=ww)

@app.route('/dashboard/save_settings',methods=['POST'])
@admin_required
def save_collab_settings():
    conn=get_db();c=conn.cursor()
    for uid in request.form.getlist('user_ids'):
        cost=float(request.form.get(f'cost_{uid}',0) or 0);hours=float(request.form.get(f'hours_{uid}',0) or 0)
        if USE_PG:
            c.execute(f"INSERT INTO collaborator_settings (user_id,hourly_cost,vendable_hours) VALUES ({P(3)}) ON CONFLICT (user_id) DO UPDATE SET hourly_cost={PLACEHOLDER},vendable_hours={PLACEHOLDER}",(uid,cost,hours,cost,hours))
        else:
            c.execute(f"INSERT OR REPLACE INTO collaborator_settings (user_id,hourly_cost,vendable_hours) VALUES ({P(3)})",(uid,cost,hours))
    conn.commit();conn.close()
    return redirect(url_for('dashboard',month=request.form.get('month',datetime.now().strftime('%Y-%m'))))


@app.route("/admin/edit_service_ajax/<int:csid>", methods=["POST"])
@admin_required
def edit_service_ajax(csid):
    data = request.get_json()
    monthly_hours = float(data.get("monthly_hours", 0))
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn=get_db();c=conn.cursor()
    c.execute(f"UPDATE client_services SET monthly_hours={PLACEHOLDER}, updated_at={PLACEHOLDER} WHERE id={PLACEHOLDER}",
              (monthly_hours, updated_at, csid))
    conn.commit();conn.close()
    return jsonify({"ok": True})
# ── ADMIN CLIENTS PAGE ────────────────────────────────────────────────────────
@app.route('/admin/clients')
@admin_required
def admin_clients():
    conn=get_db();c=conn.cursor()
    c.execute("SELECT id,name,active,dolibarr_name,address,contact_name,contact_phone,notes_permanentes FROM clients ORDER BY name")
    rows=c.fetchall();conn.close()
    if USE_PG:
        clients=[{'id':r[0],'name':r[1],'active':r[2],'dolibarr_name':r[3],'address':r[4],'contact_name':r[5],'contact_phone':r[6],'notes_permanentes':r[7]} for r in rows]
    else:
        clients=[dict(r) for r in rows]
    return render_template('admin_clients.html',clients=clients)

@app.route('/admin/client/<int:cid>')
@admin_required
def admin_client_detail(cid):
    conn=get_db();c=conn.cursor()
    c.execute(f"SELECT id,name,active,dolibarr_name,address,contact_name,contact_phone,notes_permanentes,dolibarr_quote_url FROM clients WHERE id={PLACEHOLDER}",(cid,))
    row=c.fetchone()
    if not row: conn.close();return "Client introuvable",404
    client={'id':row[0],'name':row[1],'active':row[2],'dolibarr_name':row[3],'address':row[4],'contact_name':row[5],'contact_phone':row[6],'notes_permanentes':row[7],'dolibarr_quote_url':row[8]} if USE_PG else dict(row)
    c.execute(f"SELECT cs.id,st.name,cs.monthly_hours,cs.note FROM client_services cs JOIN service_templates st ON cs.template_id=st.id WHERE cs.client_id={PLACEHOLDER} ORDER BY st.name",(cid,))
    sr=c.fetchall();conn.close()
    services=[{'id':r[0],'name':r[1],'monthly_hours':r[2],'note':r[3]} for r in sr] if USE_PG else [dict(r) for r in sr]
    return render_template('admin_client_detail.html',client=client,services=services)


# ── EXPORT ────────────────────────────────────────────────────────────────────
from export_routes import register_export_routes
register_export_routes(app,get_db,USE_PG,PLACEHOLDER,P,get_working_days)

if __name__=='__main__':
    init_db();migrate_db()
    print("✅ CX-Media TimeTracker — http://127.0.0.1:8080")
    app.run(debug=True,host='0.0.0.0',port=8080)

