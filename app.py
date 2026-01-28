"""
LGURT Dashboard v5.1 - Flask Backend
"""
import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lgurt-dev-secret-key-2024')
app.permanent_session_lifetime = timedelta(days=7)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

DB_PATH = os.environ.get('DATABASE_PATH', 'lgurt_dashboard.db')
ALGO_VERSION = 'v5.1'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_name TEXT,
            days INTEGER,
            algo_version TEXT DEFAULT 'v5.1',
            params_json TEXT,
            checksum_rev REAL,
            checksum_op REAL
        )''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS run_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            summary_json TEXT,
            skus_json TEXT,
            ads_json TEXT,
            inventory_json TEXT,
            diagnostics_json TEXT,
            config_json TEXT
        )''')
        
        cur.execute("SELECT id FROM users WHERE username = ?", ('demo',))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        ('demo', generate_password_hash('demo123')))
        
        conn.commit()
        conn.close()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database init error: {e}")

# 登录检查
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': '未登录'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

# ==================== 页面路由 ====================
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html')

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/standalone')
def standalone():
    return send_from_directory('.', 'index_standalone.html')

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': ALGO_VERSION})

# ==================== 认证API ====================
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or len(username) < 2:
        return jsonify({'error': '用户名至少2个字符'}), 400
    if not password or len(password) < 6:
        return jsonify({'error': '密码至少6个字符'}), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                    (username, generate_password_hash(password)))
        user_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        return jsonify({'success': True, 'user': {'id': user_id, 'username': username}})
    except:
        return jsonify({'error': '用户名已存在'}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': '用户名或密码错误'}), 401
    
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    
    return jsonify({'success': True, 'user': {'id': user['id'], 'username': user['username']}})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/me')
def me():
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401
    return jsonify({'user': {'id': session['user_id'], 'username': session['username']}})

# ==================== Runs API ====================
@app.route('/api/runs/upload', methods=['POST'])
@login_required
def upload_run():
    try:
        from data_processor import process_excel_file, generate_ad_plan, generate_diagnostics, calc_inventory
    except ImportError as e:
        return jsonify({'error': f'模块导入失败: {e}'}), 500
    
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400
    
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': '仅支持Excel文件'}), 400
    
    days = int(request.form.get('days', 31))
    lead_time = int(request.form.get('lead_time', 35))
    
    params = {
        'days': days,
        'lead_time_days': lead_time,
        'safety_days': 30,
        'target_cover_days': 90,
        'low_stock_threshold': 7,
        'overstock_threshold': 120
    }
    
    try:
        result = process_excel_file(file, params)
        summary = result['summary']
        skus = result['skus']
        ads_plan = generate_ad_plan(summary, skus)
        inventory = calc_inventory(skus, params)
        diagnostics = generate_diagnostics(skus, params)
        
        run_id = 'run_' + uuid.uuid4().hex[:12]
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('INSERT INTO runs (id, user_id, file_name, days, algo_version, params_json) VALUES (?, ?, ?, ?, ?, ?)',
                    (run_id, session['user_id'], file.filename, days, ALGO_VERSION, json.dumps(params)))
        cur.execute('INSERT INTO run_results (run_id, summary_json, skus_json, ads_json, inventory_json, diagnostics_json, config_json) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (run_id, json.dumps(summary), json.dumps(skus), json.dumps(ads_plan), json.dumps(inventory), json.dumps(diagnostics), json.dumps(params)))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'run_id': run_id, 'result': {
            'run_id': run_id, 'summary': summary, 'skus': skus, 'ads': ads_plan,
            'inventory': inventory, 'diagnostics': diagnostics
        }})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/runs')
@login_required
def list_runs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, created_at, file_name, days FROM runs WHERE user_id = ? ORDER BY created_at DESC LIMIT 50', (session['user_id'],))
    runs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify({'runs': runs})

@app.route('/api/runs/<run_id>')
@login_required
def get_run(run_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM runs WHERE id = ? AND user_id = ?", (run_id, session['user_id']))
    run = cur.fetchone()
    if not run:
        conn.close()
        return jsonify({'error': '记录不存在'}), 404
    cur.execute("SELECT * FROM run_results WHERE run_id = ?", (run_id,))
    result = cur.fetchone()
    conn.close()
    
    return jsonify({'success': True, 'result': {
        'run_id': run_id,
        'summary': json.loads(result['summary_json']) if result else {},
        'skus': json.loads(result['skus_json']) if result else [],
    }})

@app.route('/api/runs/<run_id>', methods=['DELETE'])
@login_required
def delete_run(run_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM run_results WHERE run_id = ?", (run_id,))
    cur.execute("DELETE FROM runs WHERE id = ? AND user_id = ?", (run_id, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ==================== 启动时初始化数据库 ====================
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"🌐 http://127.0.0.1:{port}")
    print(f"👤 demo / demo123")
    app.run(host='0.0.0.0', port=port, debug=True)
