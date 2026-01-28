"""
LGURT Dashboard v5.1 - Flask Backend
支持多人共用、历史记录、ResultBundle一致性
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lgurt-dev-secret-key-change-in-prod')
app.permanent_session_lifetime = timedelta(days=7)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# ==================== 数据库配置 ====================
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///lgurt_dashboard.db')
ALGO_VERSION = 'v5.1'

if DATABASE_URL.startswith('postgresql'):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_TYPE = 'postgres'
else:
    import sqlite3
    DB_TYPE = 'sqlite'
    DB_PATH = 'lgurt_dashboard.db'

def get_db():
    if DB_TYPE == 'postgres':
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    if DB_TYPE == 'postgres':
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id VARCHAR(50) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_name VARCHAR(255),
                days INTEGER,
                algo_version VARCHAR(20) DEFAULT 'v5.1',
                params_json TEXT,
                checksum_rev DECIMAL(15,2),
                checksum_op DECIMAL(15,2)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS run_results (
                id SERIAL PRIMARY KEY,
                run_id VARCHAR(50) NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                summary_json TEXT,
                skus_json TEXT,
                ads_json TEXT,
                inventory_json TEXT,
                diagnostics_json TEXT,
                config_json TEXT
            )
        ''')
    else:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_name TEXT,
                days INTEGER,
                algo_version TEXT DEFAULT 'v5.1',
                params_json TEXT,
                checksum_rev REAL,
                checksum_op REAL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS run_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                summary_json TEXT,
                skus_json TEXT,
                ads_json TEXT,
                inventory_json TEXT,
                diagnostics_json TEXT,
                config_json TEXT,
                FOREIGN KEY (run_id) REFERENCES runs (id) ON DELETE CASCADE
            )
        ''')
    
    # 创建默认用户
    try:
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)" if DB_TYPE == 'postgres' else "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    ('demo', generate_password_hash('demo123')))
    except:
        pass
    
    conn.commit()
    conn.close()

# ==================== 认证装饰器 ====================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '未登录'}), 401
        return f(*args, **kwargs)
    return decorated

# ==================== 认证API ====================
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or len(username) < 2:
        return jsonify({'error': '用户名至少2个字符'}), 400
    if not password or len(password) < 6:
        return jsonify({'error': '密码至少6个字符'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        ph = generate_password_hash(password)
        if DB_TYPE == 'postgres':
            cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id", (username, ph))
            user_id = cur.fetchone()['id']
        else:
            cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, ph))
            user_id = cur.lastrowid
        conn.commit()
        
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        
        return jsonify({'success': True, 'user': {'id': user_id, 'username': username}})
    except Exception as e:
        return jsonify({'error': '用户名已存在'}), 400
    finally:
        conn.close()

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    conn = get_db()
    cur = conn.cursor()
    
    if DB_TYPE == 'postgres':
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    else:
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    
    user = cur.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': '用户名或密码错误'}), 401
    
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    
    # 更新最后登录时间
    conn = get_db()
    cur = conn.cursor()
    if DB_TYPE == 'postgres':
        cur.execute("UPDATE users SET last_login = %s WHERE id = %s", (datetime.now(), user['id']))
    else:
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.now(), user['id']))
    conn.commit()
    conn.close()
    
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

# ==================== Runs API (任务3核心) ====================
@app.route('/api/runs/upload', methods=['POST'])
@login_required
def upload_run():
    """上传Excel → 计算 → 落库 → 返回run_id"""
    from data_processor import process_excel_file, generate_ad_plan, generate_diagnostics, calc_inventory
    
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400
    
    file = request.files['file']
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': '仅支持Excel文件'}), 400
    
    days = int(request.form.get('days', 31))
    lead_time = int(request.form.get('lead_time', 35))
    safety_days = int(request.form.get('safety_days', 30))
    target_cover = int(request.form.get('target_cover', 90))
    
    params = {
        'days': days,
        'lead_time_days': lead_time,
        'safety_days': safety_days,
        'target_cover_days': target_cover,
        'low_stock_threshold': 7,
        'overstock_threshold': 120
    }
    
    try:
        # 处理Excel
        result = process_excel_file(file, params)
        summary = result['summary']
        skus = result['skus']
        
        # 生成广告计划 (Phase1/Phase2结构化)
        ads_plan = generate_ad_plan(summary, skus)
        
        # 生成库存数据
        inventory = calc_inventory(skus, params)
        
        # 生成诊断建议
        diagnostics = generate_diagnostics(skus, params)
        
        # 一致性校验
        checksum_rev = sum(s['rev'] for s in skus)
        checksum_op = sum(s['op'] for s in skus)
        
        # 构建ResultBundle
        run_id = 'run_' + uuid.uuid4().hex[:12]
        result_bundle = {
            'run_id': run_id,
            'algo_version': ALGO_VERSION,
            'created_at': datetime.now().isoformat(),
            'params': params,
            'summary': summary,
            'skus': skus,
            'ads': ads_plan,
            'inventory': inventory,
            'diagnostics': diagnostics,
            'config': params,
            'checksum': {
                'rev': checksum_rev,
                'op': checksum_op
            }
        }
        
        # 落库
        conn = get_db()
        cur = conn.cursor()
        
        if DB_TYPE == 'postgres':
            cur.execute('''
                INSERT INTO runs (id, user_id, file_name, days, algo_version, params_json, checksum_rev, checksum_op)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (run_id, session['user_id'], file.filename, days, ALGO_VERSION, json.dumps(params), checksum_rev, checksum_op))
            
            cur.execute('''
                INSERT INTO run_results (run_id, summary_json, skus_json, ads_json, inventory_json, diagnostics_json, config_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (run_id, json.dumps(summary), json.dumps(skus), json.dumps(ads_plan), json.dumps(inventory), json.dumps(diagnostics), json.dumps(params)))
        else:
            cur.execute('''
                INSERT INTO runs (id, user_id, file_name, days, algo_version, params_json, checksum_rev, checksum_op)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (run_id, session['user_id'], file.filename, days, ALGO_VERSION, json.dumps(params), checksum_rev, checksum_op))
            
            cur.execute('''
                INSERT INTO run_results (run_id, summary_json, skus_json, ads_json, inventory_json, diagnostics_json, config_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (run_id, json.dumps(summary), json.dumps(skus), json.dumps(ads_plan), json.dumps(inventory), json.dumps(diagnostics), json.dumps(params)))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'run_id': run_id, 'result': result_bundle})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/runs')
@login_required
def list_runs():
    """获取历史记录列表"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    offset = (page - 1) * limit
    
    conn = get_db()
    cur = conn.cursor()
    
    if DB_TYPE == 'postgres':
        cur.execute('''
            SELECT id, created_at, file_name, days, algo_version, checksum_rev, checksum_op
            FROM runs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s
        ''', (session['user_id'], limit, offset))
        runs = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) as count FROM runs WHERE user_id = %s", (session['user_id'],))
        total = cur.fetchone()['count']
    else:
        cur.execute('''
            SELECT id, created_at, file_name, days, algo_version, checksum_rev, checksum_op
            FROM runs WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?
        ''', (session['user_id'], limit, offset))
        runs = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) as count FROM runs WHERE user_id = ?", (session['user_id'],))
        total = cur.fetchone()['count']
    
    conn.close()
    return jsonify({'runs': runs, 'total': total, 'page': page, 'limit': limit})

@app.route('/api/runs/<run_id>')
@login_required
def get_run(run_id):
    """获取单条记录详情（回放用）"""
    conn = get_db()
    cur = conn.cursor()
    
    if DB_TYPE == 'postgres':
        cur.execute("SELECT * FROM runs WHERE id = %s AND user_id = %s", (run_id, session['user_id']))
    else:
        cur.execute("SELECT * FROM runs WHERE id = ? AND user_id = ?", (run_id, session['user_id']))
    
    run = cur.fetchone()
    if not run:
        conn.close()
        return jsonify({'error': '记录不存在'}), 404
    
    if DB_TYPE == 'postgres':
        cur.execute("SELECT * FROM run_results WHERE run_id = %s", (run_id,))
    else:
        cur.execute("SELECT * FROM run_results WHERE run_id = ?", (run_id,))
    
    result = cur.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': '结果数据不存在'}), 404
    
    # 构建完整ResultBundle
    result_bundle = {
        'run_id': run_id,
        'algo_version': run['algo_version'],
        'created_at': str(run['created_at']),
        'file_name': run['file_name'],
        'days': run['days'],
        'params': json.loads(run['params_json']) if run['params_json'] else {},
        'summary': json.loads(result['summary_json']) if result['summary_json'] else {},
        'skus': json.loads(result['skus_json']) if result['skus_json'] else [],
        'ads': json.loads(result['ads_json']) if result['ads_json'] else {},
        'inventory': json.loads(result['inventory_json']) if result['inventory_json'] else [],
        'diagnostics': json.loads(result['diagnostics_json']) if result['diagnostics_json'] else [],
        'config': json.loads(result['config_json']) if result['config_json'] else {},
        'checksum': {
            'rev': float(run['checksum_rev']) if run['checksum_rev'] else 0,
            'op': float(run['checksum_op']) if run['checksum_op'] else 0
        }
    }
    
    return jsonify({'success': True, 'result': result_bundle})

@app.route('/api/runs/<run_id>', methods=['DELETE'])
@login_required
def delete_run(run_id):
    """删除记录"""
    conn = get_db()
    cur = conn.cursor()
    
    if DB_TYPE == 'postgres':
        cur.execute("DELETE FROM runs WHERE id = %s AND user_id = %s", (run_id, session['user_id']))
    else:
        cur.execute("DELETE FROM run_results WHERE run_id = ?", (run_id,))
        cur.execute("DELETE FROM runs WHERE id = ? AND user_id = ?", (run_id, session['user_id']))
    
    conn.commit()
    affected = cur.rowcount
    conn.close()
    
    if affected == 0:
        return jsonify({'error': '记录不存在'}), 404
    
    return jsonify({'success': True})

# ==================== 一致性校验API ====================
@app.route('/api/runs/<run_id>/verify')
@login_required
def verify_run(run_id):
    """校验run_id回放一致性"""
    conn = get_db()
    cur = conn.cursor()
    
    if DB_TYPE == 'postgres':
        cur.execute("SELECT checksum_rev, checksum_op FROM runs WHERE id = %s", (run_id,))
    else:
        cur.execute("SELECT checksum_rev, checksum_op FROM runs WHERE id = ?", (run_id,))
    
    run = cur.fetchone()
    if not run:
        conn.close()
        return jsonify({'error': '记录不存在'}), 404
    
    if DB_TYPE == 'postgres':
        cur.execute("SELECT skus_json FROM run_results WHERE run_id = %s", (run_id,))
    else:
        cur.execute("SELECT skus_json FROM run_results WHERE run_id = ?", (run_id,))
    
    result = cur.fetchone()
    conn.close()
    
    skus = json.loads(result['skus_json']) if result and result['skus_json'] else []
    calc_rev = sum(s.get('rev', 0) for s in skus)
    calc_op = sum(s.get('op', 0) for s in skus)
    
    stored_rev = float(run['checksum_rev']) if run['checksum_rev'] else 0
    stored_op = float(run['checksum_op']) if run['checksum_op'] else 0
    
    rev_diff = abs(calc_rev - stored_rev)
    op_diff = abs(calc_op - stored_op)
    
    is_consistent = rev_diff < 1 and op_diff < 1
    
    return jsonify({
        'run_id': run_id,
        'is_consistent': is_consistent,
        'stored': {'rev': stored_rev, 'op': stored_op},
        'calculated': {'rev': calc_rev, 'op': calc_op},
        'difference': {'rev': rev_diff, 'op': op_diff}
    })

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

# ==================== 启动 ====================
if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
