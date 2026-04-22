from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import os, hashlib, math

app = Flask(__name__)
app.secret_key = 'cxmedia-secret-2024'

@app.before_request
def log_db_mode():
    pass  # DB mode logged at startup

# ── DATABASE ──────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get('DATABASE_URL', '')
print(f"[STARTUP] DATABASE_URL={'SET ('+DATABASE_URL[:30]+'...)' if DATABASE_URL else 'NOT SET - using SQLite'}")

if DATABASE_URL:
    # PostgreSQL sur Railway
    import psycopg2
    import psycopg2.extras
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    # Ajouter SSL si pas déjà présent
    if '?sslmode=' not in DATABASE_URL and 'sslmode=' not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL + '?sslmode=require'

    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        return conn

    def fetchall(cursor):
        return cursor.fetchall()

    def fetchone(cursor):
        return cursor.fetchone()

    PLACEHOLDER = '%s'
    USE_PG = True
else:
    # SQLite en local
    import sqlite3
    DATABASE = 'timetracker.db'

    def get_db():
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn

    PLACEHOLDER = '?'
    USE_PG = False

def P(n=1):
    """Retourne n placeholders selon le moteur DB"""
    return ', '.join([PLACEHOLDER] * n)

def init_db():
    conn = get_db()
    c = conn.cursor()

    if USE_PG:
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS service_templates (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS client_services (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            monthly_hours REAL DEFAULT 0,
            UNIQUE(client_id, template_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS time_entries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_minutes REAL DEFAULT 0,
            pause_minutes REAL DEFAULT 0,
            is_manual INTEGER DEFAULT 0,
            justification TEXT,
            session_id TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS session_colleagues (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id INTEGER NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            client_id INTEGER NOT NULL,
            started_at TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS collaborator_settings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            hourly_cost REAL DEFAULT 0,
            vendable_hours REAL DEFAULT 0
        )''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS service_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS client_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            monthly_hours REAL DEFAULT 0,
            UNIQUE(client_id, template_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_minutes REAL DEFAULT 0,
            pause_minutes REAL DEFAULT 0,
            is_manual INTEGER DEFAULT 0,
            justification TEXT,
            session_id TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS session_colleagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id INTEGER NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            client_id INTEGER NOT NULL,
            started_at TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS collaborator_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            hourly_cost REAL DEFAULT 0,
            vendable_hours REAL DEFAULT 0
        )''')

    # Admin par défaut
    pw = hashlib.sha256('admin123'.encode()).hexdigest()
    try:
        c.execute(f"INSERT INTO users (username, password, role) VALUES ({P(3)}) ON CONFLICT DO NOTHING" if USE_PG else
                  f"INSERT OR IGNORE INTO users (username, password, role) VALUES ({P(3)})",
                  ('admin', pw, 'admin'))
    except:
        pass

    conn.commit()
    conn.close()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def query(sql, params=(), one=False):
    conn = get_db()
    c = conn.cursor()
    c.execute(sql, params)
    if one:
        row = c.fetchone()
    else:
        row = c.fetchall()
    conn.close()
    return row

def execute(sql, params=()):
    conn = get_db()
    c = conn.cursor()
    c.execute(sql, params)
    conn.commit()
    conn.close()

def execute_many(sqls_params):
    conn = get_db()
    c = conn.cursor()
    for sql, params in sqls_params:
        c.execute(sql, params)
    conn.commit()
    conn.close()

def row_to_dict(row, keys):
    if row is None:
        return None
    if USE_PG:
        return dict(zip(keys, row))
    return dict(row)

def rows_to_dicts(rows, keys):
    if USE_PG:
        return [dict(zip(keys, r)) for r in rows]
    return [dict(r) for r in rows]

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = hash_pw(request.form['password'])
        conn = get_db()
        c = conn.cursor()
        c.execute(f"SELECT id, username, role FROM users WHERE username={PLACEHOLDER} AND password={PLACEHOLDER} AND active=1",
                  (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            if USE_PG:
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[2]
            else:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
            return redirect(url_for('index'))
        error = "Identifiants incorrects."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── TIMER ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM clients WHERE active=1 ORDER BY name")
    clients_raw = c.fetchall()
    c.execute("SELECT id, username FROM users WHERE active=1 ORDER BY username")
    users_raw = c.fetchall()
    conn.close()

    if USE_PG:
        clients = [{'id': r[0], 'name': r[1]} for r in clients_raw]
        users = [{'id': r[0], 'username': r[1]} for r in users_raw]
    else:
        clients = [dict(r) for r in clients_raw]
        users = [dict(r) for r in users_raw]

    return render_template('index.html', clients=clients, users=users)

@app.route('/get_services/<int:client_id>')
@login_required
def get_services(client_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"""
        SELECT cs.id, st.name, cs.monthly_hours
        FROM client_services cs
        JOIN service_templates st ON cs.template_id = st.id
        WHERE cs.client_id = {PLACEHOLDER} ORDER BY st.name
    """, (client_id,))
    rows = c.fetchall()
    conn.close()
    if USE_PG:
        return jsonify([{'id': r[0], 'name': r[1], 'monthly_hours': r[2]} for r in rows])
    return jsonify([dict(r) for r in rows])

@app.route('/start_timer', methods=['POST'])
@login_required
def start_timer():
    import uuid
    data = request.get_json()
    client_id = data['client_id']
    service_id = data['service_id']
    colleagues = data.get('colleagues', [])

    conn = get_db()
    c = conn.cursor()

    # Vérification anti-doublon : bloquer si déjà en session (peu importe le client)
    all_users = [session['user_id']] + colleagues
    conflicts = []
    for uid in all_users:
        c.execute(f"SELECT client_id FROM active_sessions WHERE user_id={PLACEHOLDER}", (uid,))
        existing = c.fetchone()
        if existing:
            existing_client_id = existing[0] if USE_PG else existing['client_id']
            c.execute(f"SELECT username FROM users WHERE id={PLACEHOLDER}", (uid,))
            urow = c.fetchone()
            c.execute(f"SELECT name FROM clients WHERE id={PLACEHOLDER}", (existing_client_id,))
            crow = c.fetchone()
            uname = urow[0] if USE_PG else urow['username']
            cname = crow[0] if USE_PG else crow['name']
            if uid == session['user_id']:
                conflicts.append(f"Vous êtes déjà en session sur {cname} — arrêtez d'abord ce timer")
            else:
                conflicts.append(f"{uname} est déjà en session sur {cname}")

    if conflicts:
        conn.close()
        return jsonify({'error': ' | '.join(conflicts)}), 409

    session_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

    c.execute(f"SELECT template_id FROM client_services WHERE id={PLACEHOLDER}", (service_id,))
    row = c.fetchone()
    template_id = row[0] if USE_PG else row['template_id']

    for uid in colleagues:
        c.execute(f"INSERT INTO session_colleagues (session_id, user_id) VALUES ({P(2)})", (session_id, uid))

    # Enregistrer sessions actives pour tous les participants
    for uid in all_users:
        c.execute(f"INSERT INTO active_sessions (user_id, session_id, client_id, started_at) VALUES ({P(4)})",
                  (uid, session_id, client_id, now))

    conn.commit()
    conn.close()

    return jsonify({'session_id': session_id, 'template_id': template_id, 'client_id': client_id})

@app.route('/stop_timer', methods=['POST'])
@login_required
def stop_timer():
    data = request.get_json()
    session_id = data['session_id']
    client_id = data['client_id']
    template_id = data['template_id']
    start_time_raw = data['start_time']
    end_time_raw = data.get('end_time', '')
    pause_minutes = float(data.get('pause_minutes', 0))
    justification = data.get('justification', '')

    def clean_iso(ts):
        ts = ts.replace('Z', '')
        if '.' in ts:
            ts = ts.split('.')[0]
        return ts

    start_time = clean_iso(start_time_raw)
    end_time = clean_iso(end_time_raw) if end_time_raw else clean_iso(start_time_raw)  # fallback = start si pas reçu

    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    total_seconds = (end_dt - start_dt).total_seconds()
    pause_seconds = pause_minutes * 60
    net_seconds = max(0, total_seconds - pause_seconds)
    net_minutes = math.ceil(net_seconds / 60)  # Arrondi à la minute supérieure

    conn = get_db()
    c = conn.cursor()

    c.execute(f"SELECT user_id FROM session_colleagues WHERE session_id={PLACEHOLDER}", (session_id,))
    colleagues = c.fetchall()
    user_ids = list(set([session['user_id']] + [r[0] if USE_PG else r['user_id'] for r in colleagues]))

    for uid in user_ids:
        c.execute(f"""
            INSERT INTO time_entries
            (user_id, client_id, template_id, start_time, end_time, duration_minutes, pause_minutes, is_manual, justification, session_id)
            VALUES ({P(10)})
        """, (uid, client_id, template_id, start_time, end_time, net_minutes, pause_minutes, 0, justification, session_id))

    # Supprimer les sessions actives pour ces users
    for uid in user_ids:
        c.execute(f"DELETE FROM active_sessions WHERE user_id={PLACEHOLDER}", (uid,))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'duration_minutes': round(net_minutes, 2)})

# ── RECORDS ───────────────────────────────────────────────────────────────────

@app.route('/records')
@login_required
def records():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, name FROM clients WHERE active=1 ORDER BY name")
    clients_raw = c.fetchall()
    c.execute("SELECT id, username FROM users WHERE active=1 ORDER BY username")
    users_raw = c.fetchall()
    c.execute("SELECT id, name FROM service_templates WHERE active=1 ORDER BY name")
    templates_raw = c.fetchall()

    if USE_PG:
        clients = [{'id': r[0], 'name': r[1]} for r in clients_raw]
        users = [{'id': r[0], 'username': r[1]} for r in users_raw]
        templates = [{'id': r[0], 'name': r[1]} for r in templates_raw]
    else:
        clients = [dict(r) for r in clients_raw]
        users = [dict(r) for r in users_raw]
        templates = [dict(r) for r in templates_raw]

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    month = request.args.get('month', '')
    client_id = request.args.get('client_id', '')
    template_id = request.args.get('template_id', '')
    user_filter = request.args.get('user_id', '')

    query_sql = """
        SELECT te.id, te.start_time, te.end_time, te.duration_minutes, te.pause_minutes,
               te.is_manual, te.justification, te.session_id,
               u.username, c.name as client_name, st.name as service_name,
               te.client_id, te.template_id, te.user_id
        FROM time_entries te
        JOIN users u ON te.user_id = u.id
        JOIN clients c ON te.client_id = c.id
        JOIN service_templates st ON te.template_id = st.id
        WHERE 1=1
    """
    params = []

    if session.get('role') != 'admin':
        query_sql += f" AND te.user_id = {PLACEHOLDER}"
        params.append(session['user_id'])
    elif user_filter:
        query_sql += f" AND te.user_id = {PLACEHOLDER}"
        params.append(user_filter)

    if date_from:
        query_sql += f" AND CAST(te.start_time AS DATE) >= {PLACEHOLDER}" if USE_PG else f" AND DATE(te.start_time) >= {PLACEHOLDER}"
        params.append(date_from)
    if date_to:
        query_sql += f" AND CAST(te.start_time AS DATE) <= {PLACEHOLDER}" if USE_PG else f" AND DATE(te.start_time) <= {PLACEHOLDER}"
        params.append(date_to)
    if month:
        query_sql += f" AND TO_CHAR(CAST(te.start_time AS TIMESTAMP), 'YYYY-MM') = {PLACEHOLDER}" if USE_PG else f" AND strftime('%Y-%m', te.start_time) = {PLACEHOLDER}"
        params.append(month)
    if client_id:
        query_sql += f" AND te.client_id = {PLACEHOLDER}"
        params.append(client_id)
    if template_id:
        query_sql += f" AND te.template_id = {PLACEHOLDER}"
        params.append(template_id)

    query_sql += " ORDER BY te.start_time DESC"
    c.execute(query_sql, params)
    rows = c.fetchall()

    entries = []
    for r in rows:
        if USE_PG:
            entries.append({
                'id': r[0], 'start_time': str(r[1]), 'end_time': str(r[2]),
                'duration_minutes': r[3], 'pause_minutes': r[4],
                'is_manual': r[5], 'justification': r[6], 'session_id': r[7],
                'username': r[8], 'client_name': r[9], 'service_name': r[10],
                'client_id': r[11], 'template_id': r[12], 'user_id': r[13]
            })
        else:
            entries.append(dict(r))

    # Stats
    stats = {}
    for e in entries:
        key = (e['client_name'], e['service_name'], e['client_id'], e['template_id'])
        if key not in stats:
            stats[key] = {'total_minutes': 0, 'monthly_hours': 0}
        stats[key]['total_minutes'] += e['duration_minutes']

    for key in stats:
        c.execute(f"SELECT monthly_hours FROM client_services WHERE client_id={PLACEHOLDER} AND template_id={PLACEHOLDER}",
                  (key[2], key[3]))
        row = c.fetchone()
        stats[key]['monthly_hours'] = (row[0] if USE_PG else row['monthly_hours']) if row else 0

    conn.close()
    return render_template('records.html', entries=entries, stats=stats,
        clients=clients, users=users, templates=templates,
        filters={'date_from': date_from, 'date_to': date_to,
                 'month': month, 'client_id': client_id,
                 'template_id': template_id, 'user_id': user_filter})

# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role, active FROM users ORDER BY username")
    users_raw = c.fetchall()
    c.execute("SELECT id, name, active FROM clients ORDER BY name")
    clients_raw = c.fetchall()
    c.execute("SELECT id, name, active FROM service_templates ORDER BY name")
    templates_raw = c.fetchall()
    c.execute("""
        SELECT cs.id, cs.monthly_hours, c.name as client_name, st.name as service_name
        FROM client_services cs
        JOIN clients c ON cs.client_id = c.id
        JOIN service_templates st ON cs.template_id = st.id
        ORDER BY c.name, st.name
    """)
    cs_raw = c.fetchall()
    conn.close()

    if USE_PG:
        users = [{'id': r[0], 'username': r[1], 'role': r[2], 'active': r[3]} for r in users_raw]
        clients = [{'id': r[0], 'name': r[1], 'active': r[2]} for r in clients_raw]
        templates = [{'id': r[0], 'name': r[1], 'active': r[2]} for r in templates_raw]
        client_services = [{'id': r[0], 'monthly_hours': r[1], 'client_name': r[2], 'service_name': r[3]} for r in cs_raw]
    else:
        users = [dict(r) for r in users_raw]
        clients = [dict(r) for r in clients_raw]
        templates = [dict(r) for r in templates_raw]
        client_services = [dict(r) for r in cs_raw]

    return render_template('admin.html', users=users, clients=clients,
                           templates=templates, client_services=client_services)

@app.route('/admin/add_user', methods=['POST'])
@admin_required
def add_user():
    username = request.form['username']
    password = hash_pw(request.form['password'])
    role = request.form.get('role', 'user')
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(f"INSERT INTO users (username, password, role) VALUES ({P(3)})", (username, password, role))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_user/<int:uid>')
@admin_required
def toggle_user(uid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT active FROM users WHERE id={PLACEHOLDER}", (uid,))
    row = c.fetchone()
    active = row[0] if USE_PG else row['active']
    c.execute(f"UPDATE users SET active={PLACEHOLDER} WHERE id={PLACEHOLDER}", (1 - active, uid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:uid>')
@admin_required
def delete_user(uid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM users WHERE id={PLACEHOLDER}", (uid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/add_client', methods=['POST'])
@admin_required
def add_client():
    name = request.form['client_name']
    conn = get_db()
    c = conn.cursor()
    try:
        if USE_PG:
            c.execute(f"INSERT INTO clients (name) VALUES ({PLACEHOLDER}) RETURNING id", (name,))
            client_id = c.fetchone()[0]
        else:
            c.execute(f"INSERT INTO clients (name) VALUES ({PLACEHOLDER})", (name,))
            client_id = c.lastrowid

        # Assigner les services cochés
        c.execute("SELECT id FROM service_templates WHERE active=1")
        all_templates = c.fetchall()
        for t in all_templates:
            tid = t[0] if USE_PG else t['id']
            if request.form.get(f'selected_{tid}'):
                hours = float(request.form.get(f'hours_{tid}', 0) or 0)
                c.execute(f"INSERT INTO client_services (client_id, template_id, monthly_hours) VALUES ({P(3)})",
                          (client_id, tid, hours))
        conn.commit()
    except Exception as e:
        print(f"Erreur add_client: {e}")
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_client/<int:cid>')
@admin_required
def toggle_client(cid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT active FROM clients WHERE id={PLACEHOLDER}", (cid,))
    row = c.fetchone()
    active = row[0] if USE_PG else row['active']
    c.execute(f"UPDATE clients SET active={PLACEHOLDER} WHERE id={PLACEHOLDER}", (1 - active, cid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_client/<int:cid>')
@admin_required
def delete_client(cid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM clients WHERE id={PLACEHOLDER}", (cid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/add_template', methods=['POST'])
@admin_required
def add_template():
    name = request.form['template_name']
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(f"INSERT INTO service_templates (name) VALUES ({PLACEHOLDER})", (name,))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_template/<int:tid>')
@admin_required
def toggle_template(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT active FROM service_templates WHERE id={PLACEHOLDER}", (tid,))
    row = c.fetchone()
    active = row[0] if USE_PG else row['active']
    c.execute(f"UPDATE service_templates SET active={PLACEHOLDER} WHERE id={PLACEHOLDER}", (1 - active, tid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_template/<int:tid>')
@admin_required
def delete_template(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM service_templates WHERE id={PLACEHOLDER}", (tid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/assign_service', methods=['POST'])
@admin_required
def assign_service():
    client_id = request.form['client_id']
    template_id = request.form['template_id']
    monthly_hours = float(request.form.get('monthly_hours', 0))
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(f"INSERT INTO client_services (client_id, template_id, monthly_hours) VALUES ({P(3)})",
                  (client_id, template_id, monthly_hours))
        conn.commit()
    except: pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/get_client_assignments/<int:client_id>')
@admin_required
def get_client_assignments(client_id):
    conn = get_db()
    c = conn.cursor()
    # Tous les templates actifs
    c.execute(f"SELECT id, name FROM service_templates WHERE active=1 ORDER BY name")
    all_templates = c.fetchall()
    # Déjà affectés à ce client
    c.execute(f"SELECT template_id, monthly_hours FROM client_services WHERE client_id={PLACEHOLDER}", (client_id,))
    assigned_raw = c.fetchall()
    conn.close()

    if USE_PG:
        assigned = {r[0]: r[1] for r in assigned_raw}
        result = []
        for t in all_templates:
            tid = t[0]
            result.append({
                'template_id': tid,
                'name': t[1],
                'assigned': tid in assigned,
                'monthly_hours': assigned.get(tid, 0)
            })
    else:
        assigned = {r['template_id']: r['monthly_hours'] for r in assigned_raw}
        result = []
        for t in all_templates:
            tid = t['id']
            result.append({
                'template_id': tid,
                'name': t['name'],
                'assigned': tid in assigned,
                'monthly_hours': assigned.get(tid, 0)
            })
    return jsonify(result)

@app.route('/admin/assign_services_bulk', methods=['POST'])
@admin_required
def assign_services_bulk():
    client_id = request.form.get('client_id')
    conn = get_db()
    c = conn.cursor()

    # Récupérer tous les templates actifs
    c.execute("SELECT id FROM service_templates WHERE active=1")
    all_templates = c.fetchall()
    template_ids = [r[0] if USE_PG else r['id'] for r in all_templates]

    for tid in template_ids:
        is_selected = request.form.get(f'selected_{tid}')
        hours = request.form.get(f'hours_{tid}', 0)
        try:
            hours = float(hours) if hours else 0
        except:
            hours = 0

        # Vérifier si déjà affecté
        c.execute(f"SELECT id FROM client_services WHERE client_id={PLACEHOLDER} AND template_id={PLACEHOLDER}",
                  (client_id, tid))
        existing = c.fetchone()

        if is_selected:
            if existing:
                # Mettre à jour les heures
                c.execute(f"UPDATE client_services SET monthly_hours={PLACEHOLDER} WHERE client_id={PLACEHOLDER} AND template_id={PLACEHOLDER}",
                          (hours, client_id, tid))
            else:
                # Créer l'affectation
                c.execute(f"INSERT INTO client_services (client_id, template_id, monthly_hours) VALUES ({P(3)})",
                          (client_id, tid, hours))
        else:
            if existing:
                # Supprimer l'affectation
                c.execute(f"DELETE FROM client_services WHERE client_id={PLACEHOLDER} AND template_id={PLACEHOLDER}",
                          (client_id, tid))

    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/edit_service/<int:csid>', methods=['POST'])
@admin_required
def edit_service(csid):
    monthly_hours = float(request.form.get('monthly_hours', 0))
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE client_services SET monthly_hours={PLACEHOLDER} WHERE id={PLACEHOLDER}", (monthly_hours, csid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_service/<int:csid>')
@admin_required
def delete_service(csid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM client_services WHERE id={PLACEHOLDER}", (csid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/manual_entry', methods=['POST'])
@admin_required
def manual_entry():
    import uuid
    user_id = request.form['user_id']
    client_id = request.form['client_id']
    template_id = request.form['template_id']
    date_str = request.form['date']
    start_h = request.form['start_hour']
    end_h = request.form['end_hour']
    colleagues = request.form.getlist('colleagues')
    justification = request.form.get('justification', '')
    start_time = f"{date_str}T{start_h}:00"
    end_time = f"{date_str}T{end_h}:00"
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    duration = max(0, (end_dt - start_dt).total_seconds() / 60)
    session_id = str(uuid.uuid4())
    user_ids = list(set([user_id] + colleagues))
    conn = get_db()
    c = conn.cursor()
    for uid in user_ids:
        c.execute(f"""INSERT INTO time_entries
            (user_id, client_id, template_id, start_time, end_time, duration_minutes, pause_minutes, is_manual, justification, session_id)
            VALUES ({P(10)})""",
            (uid, client_id, template_id, start_time, end_time, duration, 0, 1, justification, session_id))
    conn.commit()
    conn.close()
    return redirect(url_for('records'))

@app.route('/admin/edit_entry/<int:eid>', methods=['POST'])
@admin_required
def edit_entry(eid):
    date_str = request.form['date']
    start_h = request.form['start_hour']
    end_h = request.form['end_hour']
    justification = request.form.get('justification', '')
    start_time = f"{date_str}T{start_h}:00"
    end_time = f"{date_str}T{end_h}:00"
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    duration = max(0, (end_dt - start_dt).total_seconds() / 60)
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE time_entries SET start_time={PLACEHOLDER}, end_time={PLACEHOLDER}, duration_minutes={PLACEHOLDER}, justification={PLACEHOLDER} WHERE id={PLACEHOLDER}",
              (start_time, end_time, duration, justification, eid))
    conn.commit()
    conn.close()
    return redirect(url_for('records'))

@app.route('/admin/delete_entry/<int:eid>')
@admin_required
def delete_entry(eid):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM time_entries WHERE id={PLACEHOLDER}", (eid,))
    conn.commit()
    conn.close()
    return redirect(url_for('records'))

@app.route('/admin/get_services_for_client/<int:client_id>')
@admin_required
def get_services_for_client(client_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"""
        SELECT cs.template_id, st.name
        FROM client_services cs
        JOIN service_templates st ON cs.template_id = st.id
        WHERE cs.client_id = {PLACEHOLDER} ORDER BY st.name
    """, (client_id,))
    rows = c.fetchall()
    conn.close()
    if USE_PG:
        return jsonify([{'template_id': r[0], 'name': r[1]} for r in rows])
    return jsonify([dict(r) for r in rows])

# ── CONFIG supprimée — heures gérées côté navigateur ──

@app.route('/active_users')
@login_required
def active_users():
    conn = get_db()
    c = conn.cursor()
    c.execute(f"""
        SELECT a.user_id, u.username, cl.name as client_name
        FROM active_sessions a
        JOIN users u ON a.user_id = u.id
        JOIN clients cl ON a.client_id = cl.id
    """)
    rows = c.fetchall()
    conn.close()
    if USE_PG:
        return jsonify([{'user_id': r[0], 'username': r[1], 'client_name': r[2]} for r in rows])
    return jsonify([{'user_id': r['user_id'], 'username': r['username'], 'client_name': r['client_name']} for r in rows])

if __name__ == '__main__':
    init_db()
    print("✅ CX-Media TimeTracker v4 — http://127.0.0.1:8080")
    print("   Login: admin / admin123")
    print(f"   DB Mode: {'PostgreSQL' if USE_PG else 'SQLite'}")
    print(f"   DATABASE_URL: {'SET' if DATABASE_URL else 'NOT SET'}")
    app.run(debug=True, host='0.0.0.0', port=8080)

# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@admin_required
def dashboard():
    conn = get_db()
    c = conn.cursor()

    # Paramètres filtre
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    user_filter = request.args.get('user_id', '')

    # Users actifs
    c.execute("SELECT id, username FROM users WHERE active=1 ORDER BY username")
    users_raw = c.fetchall()
    users = [{'id': r[0], 'username': r[1]} for r in users_raw] if USE_PG else [dict(r) for r in users_raw]

    # Settings collaborateurs
    c.execute(f"SELECT user_id, hourly_cost, vendable_hours FROM collaborator_settings")
    settings_raw = c.fetchall()
    settings = {}
    for r in settings_raw:
        if USE_PG:
            settings[r[0]] = {'hourly_cost': r[1], 'vendable_hours': r[2]}
        else:
            settings[r['user_id']] = {'hourly_cost': r['hourly_cost'], 'vendable_hours': r['vendable_hours']}

    TARIF = 75.0

    # Heures prestées par user ce mois
    query_sql = f"""
        SELECT te.user_id, u.username,
               SUM(te.duration_minutes) as total_minutes,
               te.client_id, c.name as client_name,
               te.template_id, st.name as service_name
        FROM time_entries te
        JOIN users u ON te.user_id = u.id
        JOIN clients c ON te.client_id = c.id
        JOIN service_templates st ON te.template_id = st.id
        WHERE {'TO_CHAR(CAST(te.start_time AS TIMESTAMP),' + PLACEHOLDER + ')' if USE_PG else "strftime('%Y-%m', te.start_time)"} = {PLACEHOLDER}
    """
    params = ['YYYY-MM', month] if USE_PG else [month]

    if user_filter:
        query_sql += f" AND te.user_id = {PLACEHOLDER}"
        params.append(user_filter)

    query_sql += " GROUP BY te.user_id, u.username, te.client_id, c.name, te.template_id, st.name"
    c.execute(query_sql, params)
    rows = c.fetchall()

    # Construire stats par collaborateur
    collab_stats = {}
    client_stats = {}

    for r in rows:
        if USE_PG:
            uid, uname, total_min, cid, cname, tid, sname = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        else:
            uid, uname, total_min = r['user_id'], r['username'], r['total_minutes']
            cid, cname = r['client_id'], r['client_name']
            tid, sname = r['template_id'], r['service_name']

        total_h = (total_min or 0) / 60
        s = settings.get(uid, {'hourly_cost': 0, 'vendable_hours': 0})
        hourly_cost = s['hourly_cost']
        vendable_h = s['vendable_hours']

        # Stats collaborateur
        if uid not in collab_stats:
            collab_stats[uid] = {
                'username': uname,
                'total_hours': 0,
                'vendable_hours': vendable_h,
                'hourly_cost': hourly_cost,
                'ca_realise': 0,
                'ca_attendu': vendable_h * TARIF,
                'cout_total': 0,
                'marge': 0
            }
        collab_stats[uid]['total_hours'] += total_h
        collab_stats[uid]['ca_realise'] += total_h * TARIF
        collab_stats[uid]['cout_total'] += total_h * hourly_cost

    # Calculer marge finale par collab
    for uid in collab_stats:
        cs = collab_stats[uid]
        cs['marge'] = cs['ca_realise'] - cs['cout_total']
        cs['taux_realisation'] = round((cs['total_hours'] / cs['vendable_hours'] * 100), 1) if cs['vendable_hours'] > 0 else 0

    # Stats par client (budget vs presté)
    c.execute(f"""
        SELECT cs.client_id, cl.name, cs.template_id, st.name as sname, cs.monthly_hours,
               COALESCE(SUM(te.duration_minutes), 0) as total_min
        FROM client_services cs
        JOIN clients cl ON cs.client_id = cl.id
        JOIN service_templates st ON cs.template_id = st.id
        LEFT JOIN time_entries te ON te.client_id = cs.client_id
            AND te.template_id = cs.template_id
            AND {'TO_CHAR(CAST(te.start_time AS TIMESTAMP),' + PLACEHOLDER + ')' if USE_PG else "strftime('%Y-%m', te.start_time)"} = {PLACEHOLDER}
        GROUP BY cs.client_id, cl.name, cs.template_id, st.name, cs.monthly_hours
        ORDER BY cl.name
    """, (['YYYY-MM', month] if USE_PG else [month]))

    client_rows = c.fetchall()
    client_stats = {}
    for r in client_rows:
        if USE_PG:
            cid, cname, tid, sname, quota_h, total_min = r[0], r[1], r[2], r[3], r[4], r[5]
        else:
            cid, cname = r['client_id'], r['name']
            tid, sname = r['template_id'], r['sname']
            quota_h, total_min = r['monthly_hours'], r['total_min']

        if cid not in client_stats:
            client_stats[cid] = {
                'name': cname,
                'budget': 0,
                'ca_realise': 0,
                'hours_quota': 0,
                'hours_prested': 0,
                'services': []
            }

        prested_h = (total_min or 0) / 60
        budget = quota_h * TARIF
        ca_realise = prested_h * TARIF
        taux_horaire = budget / prested_h if prested_h > 0 else 0

        client_stats[cid]['budget'] += budget
        client_stats[cid]['ca_realise'] += ca_realise
        client_stats[cid]['hours_quota'] += quota_h
        client_stats[cid]['hours_prested'] += prested_h
        client_stats[cid]['services'].append({
            'name': sname,
            'quota_h': quota_h,
            'prested_h': round(prested_h, 2),
            'budget': budget,
            'taux_horaire': round(taux_horaire, 2)
        })

    conn.close()

    return render_template('dashboard.html',
        users=users, settings=settings,
        collab_stats=collab_stats,
        client_stats=client_stats,
        month=month, user_filter=user_filter,
        TARIF=TARIF)

@app.route('/dashboard/save_settings', methods=['POST'])
@admin_required
def save_collab_settings():
    conn = get_db()
    c = conn.cursor()
    users_ids = request.form.getlist('user_ids')
    for uid in users_ids:
        cost = float(request.form.get(f'cost_{uid}', 0) or 0)
        hours = float(request.form.get(f'hours_{uid}', 0) or 0)
        if USE_PG:
            c.execute(f"""INSERT INTO collaborator_settings (user_id, hourly_cost, vendable_hours)
                VALUES ({P(3)})
                ON CONFLICT (user_id) DO UPDATE SET hourly_cost={PLACEHOLDER}, vendable_hours={PLACEHOLDER}""",
                (uid, cost, hours, cost, hours))
        else:
            c.execute(f"""INSERT OR REPLACE INTO collaborator_settings (user_id, hourly_cost, vendable_hours)
                VALUES ({P(3)})""", (uid, cost, hours))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))
