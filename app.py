from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
import sqlite3, os, hashlib

app = Flask(__name__)
app.secret_key = 'cxmedia-secret-2024'
DATABASE = 'timetracker.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

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
        FOREIGN KEY(client_id) REFERENCES clients(id),
        FOREIGN KEY(template_id) REFERENCES service_templates(id),
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
        session_id TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(client_id) REFERENCES clients(id),
        FOREIGN KEY(template_id) REFERENCES service_templates(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS pause_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id INTEGER,
        session_id TEXT,
        pause_start TEXT,
        pause_end TEXT,
        FOREIGN KEY(entry_id) REFERENCES time_entries(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS session_colleagues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Admin par défaut
    pw = hashlib.sha256('admin123'.encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', ?, 'admin')", (pw,))

    conn.commit()
    conn.close()

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

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
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=? AND active=1",
                            (username, password)).fetchone()
        conn.close()
        if user:
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
    clients = conn.execute("SELECT * FROM clients WHERE active=1 ORDER BY name").fetchall()
    users = conn.execute("SELECT * FROM users WHERE active=1 ORDER BY username").fetchall()
    conn.close()
    return render_template('index.html', clients=clients, users=users)

@app.route('/get_services/<int:client_id>')
@login_required
def get_services(client_id):
    conn = get_db()
    services = conn.execute("""
        SELECT cs.id, st.name, cs.monthly_hours
        FROM client_services cs
        JOIN service_templates st ON cs.template_id = st.id
        WHERE cs.client_id = ? ORDER BY st.name
    """, (client_id,)).fetchall()
    conn.close()
    return jsonify([dict(s) for s in services])

@app.route('/start_timer', methods=['POST'])
@login_required
def start_timer():
    import uuid
    data = request.get_json()
    client_id = data['client_id']
    service_id = data['service_id']
    colleagues = data.get('colleagues', [])

    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = get_db()
    # Get template_id from client_service
    cs = conn.execute("SELECT template_id FROM client_services WHERE id=?", (service_id,)).fetchone()
    template_id = cs['template_id']

    # Save colleagues in session
    for uid in colleagues:
        conn.execute("INSERT INTO session_colleagues (session_id, user_id) VALUES (?,?)", (session_id, uid))

    conn.commit()
    conn.close()

    return jsonify({
        'session_id': session_id,
        'start_time': now,
        'template_id': template_id,
        'client_id': client_id
    })

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
    end_time = clean_iso(end_time_raw) if end_time_raw else datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    total_minutes = (end_dt - start_dt).total_seconds() / 60
    net_minutes = max(0, total_minutes - pause_minutes)

    conn = get_db()

    # Get quota to check overtime
    cs = conn.execute("""
        SELECT monthly_hours FROM client_services
        WHERE client_id=? AND template_id=?
    """, (client_id, template_id)).fetchone()
    monthly_hours = cs['monthly_hours'] if cs else 0

    # Get all users for this session
    colleagues = conn.execute(
        "SELECT user_id FROM session_colleagues WHERE session_id=?", (session_id,)
    ).fetchall()
    user_ids = [session['user_id']] + [c['user_id'] for c in colleagues]
    user_ids = list(set(user_ids))

    for uid in user_ids:
        conn.execute("""
            INSERT INTO time_entries
            (user_id, client_id, template_id, start_time, end_time, duration_minutes, pause_minutes, is_manual, justification, session_id)
            VALUES (?,?,?,?,?,?,?,0,?,?)
        """, (uid, client_id, template_id, start_time, end_time, net_minutes, pause_minutes, justification, session_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'duration_minutes': round(net_minutes, 2)})

# ── RECORDS ───────────────────────────────────────────────────────────────────

@app.route('/records')
@login_required
def records():
    conn = get_db()
    clients = conn.execute("SELECT * FROM clients WHERE active=1 ORDER BY name").fetchall()
    users = conn.execute("SELECT * FROM users WHERE active=1 ORDER BY username").fetchall()
    templates = conn.execute("SELECT * FROM service_templates WHERE active=1 ORDER BY name").fetchall()

    # Filters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    month = request.args.get('month', '')
    client_id = request.args.get('client_id', '')
    template_id = request.args.get('template_id', '')
    user_filter = request.args.get('user_id', '')

    query = """
        SELECT te.*, u.username, c.name as client_name, st.name as service_name
        FROM time_entries te
        JOIN users u ON te.user_id = u.id
        JOIN clients c ON te.client_id = c.id
        JOIN service_templates st ON te.template_id = st.id
        WHERE 1=1
    """
    params = []

    if session.get('role') != 'admin':
        query += " AND te.user_id = ?"
        params.append(session['user_id'])
    elif user_filter:
        query += " AND te.user_id = ?"
        params.append(user_filter)

    if date_from:
        query += " AND DATE(te.start_time) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND DATE(te.start_time) <= ?"
        params.append(date_to)
    if month:
        query += " AND strftime('%Y-%m', te.start_time) = ?"
        params.append(month)
    if client_id:
        query += " AND te.client_id = ?"
        params.append(client_id)
    if template_id:
        query += " AND te.template_id = ?"
        params.append(template_id)

    query += " ORDER BY te.start_time DESC"
    entries = conn.execute(query, params).fetchall()

    # Stats per (client, service)
    stats = {}
    for e in entries:
        key = (e['client_name'], e['service_name'], e['client_id'], e['template_id'])
        if key not in stats:
            stats[key] = {'total_minutes': 0, 'monthly_hours': 0}
        stats[key]['total_minutes'] += e['duration_minutes']

    # Get quotas
    for key in stats:
        cs = conn.execute("""
            SELECT monthly_hours FROM client_services WHERE client_id=? AND template_id=?
        """, (key[2], key[3])).fetchone()
        stats[key]['monthly_hours'] = cs['monthly_hours'] if cs else 0

    conn.close()
    return render_template('records.html',
        entries=entries, stats=stats, clients=clients,
        users=users, templates=templates,
        filters={'date_from': date_from, 'date_to': date_to,
                 'month': month, 'client_id': client_id,
                 'template_id': template_id, 'user_id': user_filter})

# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    templates = conn.execute("SELECT * FROM service_templates ORDER BY name").fetchall()
    client_services = conn.execute("""
        SELECT cs.*, c.name as client_name, st.name as service_name
        FROM client_services cs
        JOIN clients c ON cs.client_id = c.id
        JOIN service_templates st ON cs.template_id = st.id
        ORDER BY c.name, st.name
    """).fetchall()
    conn.close()
    return render_template('admin.html', users=users, clients=clients,
                           templates=templates, client_services=client_services)

# Users
@app.route('/admin/add_user', methods=['POST'])
@admin_required
def add_user():
    username = request.form['username']
    password = hash_pw(request.form['password'])
    role = request.form.get('role', 'user')
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (username, password, role))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_user/<int:uid>')
@admin_required
def toggle_user(uid):
    conn = get_db()
    user = conn.execute("SELECT active FROM users WHERE id=?", (uid,)).fetchone()
    conn.execute("UPDATE users SET active=? WHERE id=?", (1 - user['active'], uid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:uid>')
@admin_required
def delete_user(uid):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# Clients
@app.route('/admin/add_client', methods=['POST'])
@admin_required
def add_client():
    name = request.form['client_name']
    conn = get_db()
    try:
        conn.execute("INSERT INTO clients (name) VALUES (?)", (name,))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_client/<int:cid>')
@admin_required
def toggle_client(cid):
    conn = get_db()
    c = conn.execute("SELECT active FROM clients WHERE id=?", (cid,)).fetchone()
    conn.execute("UPDATE clients SET active=? WHERE id=?", (1 - c['active'], cid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# Service Templates
@app.route('/admin/add_template', methods=['POST'])
@admin_required
def add_template():
    name = request.form['template_name']
    conn = get_db()
    try:
        conn.execute("INSERT INTO service_templates (name) VALUES (?)", (name,))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_template/<int:tid>')
@admin_required
def toggle_template(tid):
    conn = get_db()
    t = conn.execute("SELECT active FROM service_templates WHERE id=?", (tid,)).fetchone()
    conn.execute("UPDATE service_templates SET active=? WHERE id=?", (1 - t['active'], tid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# Client Services
@app.route('/admin/assign_service', methods=['POST'])
@admin_required
def assign_service():
    client_id = request.form['client_id']
    template_id = request.form['template_id']
    monthly_hours = float(request.form.get('monthly_hours', 0))
    conn = get_db()
    try:
        conn.execute("INSERT INTO client_services (client_id, template_id, monthly_hours) VALUES (?,?,?)",
                     (client_id, template_id, monthly_hours))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/edit_service/<int:csid>', methods=['POST'])
@admin_required
def edit_service(csid):
    monthly_hours = float(request.form.get('monthly_hours', 0))
    conn = get_db()
    conn.execute("UPDATE client_services SET monthly_hours=? WHERE id=?", (monthly_hours, csid))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_service/<int:csid>')
@admin_required
def delete_service(csid):
    conn = get_db()
    conn.execute("DELETE FROM client_services WHERE id=?", (csid,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# Manual Entry
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

    conn = get_db()
    user_ids = [user_id] + colleagues
    user_ids = list(set(user_ids))
    for uid in user_ids:
        conn.execute("""
            INSERT INTO time_entries
            (user_id, client_id, template_id, start_time, end_time, duration_minutes, pause_minutes, is_manual, justification, session_id)
            VALUES (?,?,?,?,?,?,0,1,?,?)
        """, (uid, client_id, template_id, start_time, end_time, duration, justification, session_id))
    conn.commit()
    conn.close()
    return redirect(url_for('records'))

# Edit / Delete Entry
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
    conn.execute("""
        UPDATE time_entries SET start_time=?, end_time=?, duration_minutes=?, justification=?
        WHERE id=?
    """, (start_time, end_time, duration, justification, eid))
    conn.commit()
    conn.close()
    return redirect(url_for('records'))

@app.route('/admin/delete_entry/<int:eid>')
@admin_required
def delete_entry(eid):
    conn = get_db()
    conn.execute("DELETE FROM time_entries WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return redirect(url_for('records'))

# Get services for a client (admin manual entry)
@app.route('/admin/get_services_for_client/<int:client_id>')
@admin_required
def get_services_for_client(client_id):
    conn = get_db()
    services = conn.execute("""
        SELECT cs.template_id, st.name
        FROM client_services cs
        JOIN service_templates st ON cs.template_id = st.id
        WHERE cs.client_id = ?
        ORDER BY st.name
    """, (client_id,)).fetchall()
    conn.close()
    return jsonify([dict(s) for s in services])

if __name__ == '__main__':
    init_db()
    print("✅ CX-Media TimeTracker v4 — http://127.0.0.1:8080")
    print("   Login: admin / admin123")
    app.run(debug=True, host='0.0.0.0', port=8080)
