import sqlite3
import os
import hashlib
import json
import calendar
from functools import wraps
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from translations import get_translation, SUPPORTED_LANGUAGES

load_dotenv()

app = Flask(__name__)
app.secret_key = 'gebeta-nutrition-secret-key-2026'

DATABASE = 'instance/gebeta.db'

# Google OAuth Setup
google_client_id = os.environ.get('GOOGLE_CLIENT_ID')
google_client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

oauth = None
if google_client_id and google_client_secret and not google_client_id.startswith('mock') and google_client_id.strip():
    try:
        oauth = OAuth(app)
        oauth.register(
            name='google',
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile'
            }
        )
    except Exception as e:
        print(f"Error registering Authlib Google OAuth client: {e}")
        oauth = None

def get_db():
    os.makedirs('instance', exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_columns(conn, table_name, columns):
    existing = {
        column['name']
        for column in conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    }

    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}')

def init_db():
    conn = get_db()
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            activity_level TEXT,
            dietary_preference TEXT,
            religious_preference TEXT,
            fitness_goal TEXT,
            health_goals TEXT,
            medical_conditions TEXT,
            daily_budget_etb REAL,
            weekly_budget_etb REAL,
            monthly_budget_etb REAL,
            preferred_language TEXT DEFAULT 'english',
            profile_pic TEXT,
            subscription_plan TEXT DEFAULT 'free',
            google_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    ensure_columns(conn, 'users', {
        'password_hash': "TEXT DEFAULT ''",
        'google_id': 'TEXT',
        'dietary_preference': 'TEXT',
        'religious_preference': 'TEXT',
        'fitness_goal': 'TEXT',
        'health_goals': 'TEXT',
        'medical_conditions': 'TEXT',
        'daily_budget_etb': 'REAL',
        'weekly_budget_etb': 'REAL',
        'monthly_budget_etb': 'REAL',
        'preferred_language': "TEXT DEFAULT 'english'",
        'subscription_plan': "TEXT DEFAULT 'free'"
    })
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            relationship TEXT,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            medical_conditions TEXT,
            dietary_restrictions TEXT,
            is_fasting INTEGER DEFAULT 0,
            fasting_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ethiopian_foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_english TEXT NOT NULL,
            name_amharic TEXT,
            name_oromo TEXT,
            name_tigrinya TEXT,
            calories_per_100g REAL,
            protein_g REAL,
            carbs_g REAL,
            fat_g REAL,
            fiber_g REAL,
            iron_mg REAL,
            calcium_mg REAL,
            sodium_mg REAL,
            vitamin_d_iu REAL,
            vitamin_b12_mcg REAL,
            glycemic_index REAL,
            glycemic_load REAL,
            food_category TEXT,
            is_fasting_compatible INTEGER DEFAULT 1,
            is_vegan INTEGER DEFAULT 1,
            avg_price_per_kg_etb REAL,
            typical_serving_g REAL,
            common_meal_time TEXT,
            region_of_origin TEXT
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            food_id INTEGER NOT NULL,
            family_member_id INTEGER,
            serving_size_g REAL NOT NULL,
            meal_type TEXT,
            is_fasting_meal INTEGER DEFAULT 0,
            fasting_type TEXT,
            total_calories REAL,
            total_protein REAL,
            total_carbs REAL,
            total_fat REAL,
            total_iron REAL,
            total_sodium REAL,
            logged_via TEXT DEFAULT 'manual',
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (food_id) REFERENCES ethiopian_foods(id),
            FOREIGN KEY (family_member_id) REFERENCES family_members(id)
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS fasting_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            religion TEXT NOT NULL,
            fasting_name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            fasting_type TEXT,
            description TEXT,
            allowed_foods TEXT,
            restricted_foods TEXT
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS health_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            weight_kg REAL,
            blood_sugar_mgdl REAL,
            blood_pressure_systolic INTEGER,
            blood_pressure_diastolic INTEGER,
            sleep_hours REAL,
            sleep_quality INTEGER,
            water_intake_ml REAL,
            steps_count INTEGER,
            activity_minutes INTEGER,
            activity_type TEXT,
            mood_score INTEGER,
            wellness_score REAL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            recommendation_type TEXT,
            recommendation_text TEXT,
            recommendation_json TEXT,
            is_read INTEGER DEFAULT 0,
            is_implemented INTEGER DEFAULT 0,
            feedback_score INTEGER,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            food_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (food_id) REFERENCES ethiopian_foods(id)
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS wellness_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_name TEXT NOT NULL,
            challenge_type TEXT,
            description TEXT,
            start_date DATE,
            end_date DATE,
            reward_badge TEXT,
            target_value REAL,
            target_unit TEXT
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            badge_name TEXT NOT NULL,
            badge_type TEXT,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nutritionists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            specialization TEXT,
            license_number TEXT,
            years_experience INTEGER,
            consultation_fee_etb REAL,
            availability TEXT,
            rating REAL,
            profile_pic TEXT,
            bio TEXT
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nutritionist_id INTEGER NOT NULL,
            consultation_date TIMESTAMP,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            meal_plan_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (nutritionist_id) REFERENCES nutritionists(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    seed_foods()
    seed_fasting_calendar()

def seed_foods():
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM ethiopian_foods').fetchone()[0]
    
    if count == 0:
        foods = [
            ('Injera (Teff)', 'እንጀራ', 'Biddeena', 'Injera', 145, 4.8, 28.3, 1.2, 2.8, 2.4, 15, 5, 0, 0, 35, 12, 'grain', 1, 1, 45, 200, 'any', 'All regions'),
            ('Shiro Wot', 'ሽሮ ወጥ', 'Shiro', 'Shiro', 95, 6.2, 12.5, 2.8, 3.5, 4.8, 45, 8, 0, 0, 28, 8, 'legume', 1, 1, 60, 150, 'lunch,dinner', 'All regions'),
            ('Doro Wot', 'ዶሮ ወጥ', 'Doro', 'Doro', 210, 18.5, 5.2, 14.8, 1.2, 3.2, 25, 180, 0, 1.2, 20, 5, 'meat', 0, 0, 280, 200, 'lunch,dinner', 'All regions'),
            ('Misir Wot', 'ምስር ወጥ', 'Misir', 'Misir', 110, 8.5, 16.2, 1.5, 5.8, 5.2, 35, 12, 0, 0, 30, 9, 'legume', 1, 1, 55, 150, 'lunch,dinner', 'All regions'),
            ('Gomen', 'ጎመን', 'Gomen', 'Gomen', 45, 3.2, 6.8, 0.8, 4.2, 2.8, 180, 25, 0, 0, 15, 4, 'vegetable', 1, 1, 25, 100, 'any', 'All regions'),
            ('Tibs', 'ጥብስ', 'Tibs', 'Tibs', 280, 24.5, 2.1, 19.8, 0.5, 4.5, 15, 280, 0, 2.1, 25, 6, 'meat', 0, 0, 350, 150, 'lunch,dinner', 'All regions'),
            ('Firfir', 'ፍርፍር', 'Firfir', 'Firfir', 180, 5.5, 32.5, 3.8, 3.2, 2.8, 20, 45, 0, 0, 42, 15, 'mixed', 1, 1, 40, 250, 'breakfast', 'All regions'),
            ('Genfo', 'ገንፎ', 'Genfo', 'Genfo', 195, 6.8, 35.2, 3.5, 4.5, 3.5, 30, 8, 0, 0, 38, 14, 'grain', 1, 1, 35, 200, 'breakfast', 'All regions'),
            ('Kinche', 'ቅንቼ', 'Kinche', 'Kinche', 165, 7.2, 28.5, 2.2, 5.5, 4.2, 28, 10, 0, 0, 32, 11, 'grain', 1, 1, 30, 180, 'breakfast', 'All regions'),
            ('Nifro', 'ንፍሮ', 'Nifro', 'Nifro', 155, 8.8, 25.5, 1.8, 6.2, 4.5, 40, 8, 0, 0, 22, 7, 'legume', 1, 1, 50, 150, 'snack', 'All regions'),
            ('Atkilt Wot', 'አትክልት ወጥ', 'Atkilt', 'Atkilt', 65, 2.5, 10.2, 1.5, 3.8, 2.2, 45, 35, 0, 0, 25, 7, 'vegetable', 1, 1, 30, 150, 'any', 'All regions'),
            ('Dulet', 'ዱለት', 'Dulet', 'Dulet', 320, 22.5, 3.5, 24.8, 0.8, 8.5, 20, 320, 0, 5.2, 15, 4, 'meat', 0, 0, 400, 120, 'lunch,dinner', 'All regions'),
        ]
        
        for food in foods:
            conn.execute('''
                INSERT INTO ethiopian_foods 
                (name_english, name_amharic, name_oromo, name_tigrinya, calories_per_100g, 
                 protein_g, carbs_g, fat_g, fiber_g, iron_mg, calcium_mg, sodium_mg,
                 vitamin_d_iu, vitamin_b12_mcg, glycemic_index, glycemic_load,
                 food_category, is_fasting_compatible, is_vegan, avg_price_per_kg_etb,
                 typical_serving_g, common_meal_time, region_of_origin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', food)
        
        conn.commit()
    
    conn.close()

def seed_fasting_calendar():
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM fasting_calendar').fetchone()[0]
    
    if count == 0:
        fasts = [
            ('orthodox', 'Hudade (Lent)', '2026-03-02', '2026-04-18', 'strict_vegan', 'Great Lent fasting period', 'legumes,grains,vegetables,fruits', 'meat,dairy,eggs'),
            ('orthodox', 'Apostles Fast', '2026-06-01', '2026-07-11', 'strict_vegan', 'Apostles fasting period', 'legumes,grains,vegetables,fruits', 'meat,dairy,eggs'),
            ('orthodox', 'Filseta', '2026-08-07', '2026-08-21', 'strict_vegan', 'Assumption of Mary fast', 'legumes,grains,vegetables,fruits', 'meat,dairy,eggs'),
            ('orthodox', 'Nativity Fast', '2026-11-15', '2026-12-28', 'strict_vegan', 'Christmas fasting period', 'legumes,grains,vegetables,fruits', 'meat,dairy,eggs'),
            ('orthodox', 'Nineveh Fast', '2026-01-26', '2026-01-28', 'strict_vegan', 'Three days of repentance', 'legumes,grains,vegetables,fruits', 'meat,dairy,eggs,oil'),
            ('muslim', 'Ramadan 2026', '2026-02-18', '2026-03-19', 'daylight_hours', 'Holy month of fasting', 'all_foods', 'none'),
        ]
        
        for fast in fasts:
            conn.execute('''
                INSERT INTO fasting_calendar 
                (religion, fasting_name, start_date, end_date, fasting_type, description, allowed_foods, restricted_foods)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', fast)
        
        conn.commit()
    
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        return user
    return None

def calculate_bmi(weight_kg, height_cm):
    if weight_kg and height_cm:
        height_m = height_cm / 100
        return round(weight_kg / (height_m * height_m), 1)
    return None

def is_fasting_today(religious_preference):
    if not religious_preference:
        return False
    
    today = date.today().isoformat()
    conn = get_db()
    
    if religious_preference.lower() == 'orthodox':
        fast = conn.execute('''
            SELECT * FROM fasting_calendar 
            WHERE religion = 'orthodox' AND start_date <= ? AND end_date >= ?
        ''', (today, today)).fetchone()
        
        if fast:
            day_of_week = date.today().weekday()
            if day_of_week in [2, 5]:
                conn.close()
                return fast
        
        conn.close()
        return fast
    
    if religious_preference.lower() == 'muslim':
        fast = conn.execute('''
            SELECT * FROM fasting_calendar 
            WHERE religion = 'muslim' AND start_date <= ? AND end_date >= ?
        ''', (today, today)).fetchone()
        conn.close()
        return fast
    
    conn.close()
    return None

def get_dashboard_stats(user_id):
    conn = get_db()
    today = date.today().isoformat()
    
    total_calories = conn.execute('''
        SELECT COALESCE(SUM(total_calories), 0) as total
        FROM meal_logs WHERE user_id = ? AND DATE(logged_at) = ?
    ''', (user_id, today)).fetchone()['total']
    
    total_protein = conn.execute('''
        SELECT COALESCE(SUM(total_protein), 0) as total
        FROM meal_logs WHERE user_id = ? AND DATE(logged_at) = ?
    ''', (user_id, today)).fetchone()['total']
    
    total_spent = conn.execute('''
        SELECT COALESCE(SUM(ef.avg_price_per_kg_etb * ml.serving_size_g / 1000), 0) as total
        FROM meal_logs ml
        JOIN ethiopian_foods ef ON ml.food_id = ef.id
        WHERE ml.user_id = ? AND DATE(ml.logged_at) = ?
    ''', (user_id, today)).fetchone()['total']
    
    fasting_streak = 0
    current_date = date.today()
    while True:
        meals = conn.execute('''
            SELECT COUNT(*) as count FROM meal_logs 
            WHERE user_id = ? AND DATE(logged_at) = ? AND is_fasting_meal = 1
        ''', (user_id, current_date.isoformat())).fetchone()['count']
        
        if meals > 0:
            fasting_streak += 1
            current_date -= timedelta(days=1)
        else:
            break

    water_intake = conn.execute('''
        SELECT COALESCE(water_intake_ml, 0) as total
        FROM health_metrics
        WHERE user_id = ? AND DATE(recorded_at) = ?
        ORDER BY recorded_at DESC
        LIMIT 1
    ''', (user_id, today)).fetchone()
    
    conn.close()
    
    return {
        'calories_consumed': round(total_calories),
        'protein_consumed': round(total_protein, 1),
        'budget_spent': round(total_spent, 2),
        'fasting_streak': fasting_streak,
        'water_intake_ml': round(water_intake['total'] if water_intake else 0)
    }

def get_calendar_data():
    today = date.today()
    first_day = today.replace(day=1)
    last_day = today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1)
    
    conn = get_db()
    fasts = conn.execute('''
        SELECT * FROM fasting_calendar 
        WHERE start_date <= ? AND end_date >= ?
    ''', (last_day.isoformat(), first_day.isoformat())).fetchall()
    conn.close()
    
    fasting_dates = []
    for fast in fasts:
        start = datetime.strptime(fast['start_date'], '%Y-%m-%d').date()
        end = datetime.strptime(fast['end_date'], '%Y-%m-%d').date()
        
        current = max(start, first_day)
        end_range = min(end, last_day)
        
        while current <= end_range:
            if fast['religion'] == 'orthodox':
                if current.weekday() in [2, 5]:
                    fasting_dates.append({
                        'date': current.day,
                        'type': 'strict',
                        'name': fast['fasting_name']
                    })
            elif fast['religion'] == 'muslim':
                fasting_dates.append({
                    'date': current.day,
                    'type': 'daylight',
                    'name': fast['fasting_name']
                })
            current += timedelta(days=1)
    
    return fasting_dates

def get_current_month_calendar():
    today = date.today()
    first_weekday, days_in_month = calendar.monthrange(today.year, today.month)
    leading_blanks = (first_weekday + 1) % 7
    fasting_by_day = {item['date']: item for item in get_calendar_data()}

    days = [
        {'day': None, 'is_today': False, 'is_fasting': False, 'fasting_name': ''}
        for _ in range(leading_blanks)
    ]

    for day in range(1, days_in_month + 1):
        fasting_item = fasting_by_day.get(day)
        days.append({
            'day': day,
            'is_today': day == today.day,
            'is_fasting': fasting_item is not None,
            'fasting_name': fasting_item['name'] if fasting_item else ''
        })

    while len(days) % 7 != 0:
        days.append({'day': None, 'is_today': False, 'is_fasting': False, 'fasting_name': ''})

    return {
        'month_label': today.strftime('%B %Y'),
        'days': days
    }
@app.context_processor
def inject_user_plan():
    lang = session.get('lang', 'english')
    def t(key):
        return get_translation(lang, key)
    ctx = {'current_lang': lang, 't': t}
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT subscription_plan, preferred_language FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if user:
            # Prefer DB language but session overrides
            if 'lang' not in session and user['preferred_language'] in SUPPORTED_LANGUAGES:
                session['lang'] = user['preferred_language']
                lang = user['preferred_language']
                ctx['current_lang'] = lang
                ctx['t'] = lambda key: get_translation(lang, key)
            ctx['current_user_plan'] = user['subscription_plan']
            return ctx
    ctx['current_user_plan'] = 'free'
    return ctx

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/select-plan', methods=['GET', 'POST'])
@login_required
def select_plan():
    user = get_current_user()
    if request.method == 'POST':
        plan = request.form.get('plan')
        if plan not in ['free', 'plus', 'premium']:
            flash('Invalid plan selected.', 'error')
            return redirect(url_for('select_plan'))
        
        if plan == 'free':
            conn = get_db()
            conn.execute('UPDATE users SET subscription_plan = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (plan, session['user_id']))
            conn.commit()
            conn.close()
            flash('Plan updated to Free.', 'success')
            return redirect(url_for('dashboard_overview'))
        else:
            return redirect(url_for('checkout', plan=plan))
        
    return render_template('select_plan.html', user=user)

@app.route('/checkout')
@login_required
def checkout():
    plan = request.args.get('plan')
    if plan not in ['plus', 'premium']:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('select_plan'))
    
    price = 199 if plan == 'plus' else 499
    return render_template('checkout.html', plan_name=plan, price=price)

@app.route('/checkout/telebirr', methods=['GET', 'POST'])
@login_required
def telebirr_checkout():
    import uuid
    plan = request.values.get('plan')
    if plan not in ['plus', 'premium']:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('select_plan'))
    
    price = 199 if plan == 'plus' else 499
    
    if request.method == 'POST':
        conn = get_db()
        conn.execute('UPDATE users SET subscription_plan = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (plan, session['user_id']))
        conn.commit()
        conn.close()
        
        flash(f'Payment of {price} ETB successful via telebirr! Activated {plan.title()} subscription.', 'success')
        return redirect(url_for('dashboard_overview'))
    
    out_trade_no = str(uuid.uuid4().hex[:12]).upper()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('telebirr_pay.html', plan_name=plan, price=price, out_trade_no=out_trade_no, timestamp=timestamp)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([full_name, email, password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
        
        conn = get_db()
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing:
            conn.close()
            flash('Email already registered.', 'error')
            return redirect(url_for('login'))
        
        password_hash = hash_password(password)
        user_columns = {
            column['name']
            for column in conn.execute('PRAGMA table_info(users)').fetchall()
        }
        insert_columns = ['full_name', 'email', 'password_hash']
        insert_values = [full_name, email, password_hash]

        if 'google_id' in user_columns:
            insert_columns.append('google_id')
            insert_values.append(f'local:{email}')

        placeholders = ', '.join(['?'] * len(insert_columns))
        cursor = conn.cursor()
        cursor.execute(
            f'INSERT INTO users ({", ".join(insert_columns)}) VALUES ({placeholders})',
            insert_values
        )
        new_user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        session['user_id'] = new_user_id
        session['user_name'] = full_name
        session['user_email'] = email
        
        flash('Registration successful! Please choose a subscription plan.', 'success')
        return redirect(url_for('select_plan'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not all([email, password]):
            flash('Email and password are required.', 'error')
            return redirect(url_for('login'))
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and user['password_hash'] == hash_password(password):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_email'] = user['email']
            flash(f'Welcome back, {user["full_name"].split()[0]}!', 'success')
            return redirect(url_for('dashboard_overview'))
        
        flash('Invalid email or password.', 'error')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in SUPPORTED_LANGUAGES:
        session['lang'] = lang
        # Also persist to DB if logged in
        if 'user_id' in session:
            conn = get_db()
            conn.execute('UPDATE users SET preferred_language = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (lang, session['user_id']))
            conn.commit()
            conn.close()
    return redirect(request.referrer or url_for('dashboard_overview'))

@app.route('/auth/google')
def google_auth():
    redirect_uri = url_for('google_auth_callback', _external=True)
    if oauth and oauth.google:
        try:
            return oauth.google.authorize_redirect(redirect_uri)
        except Exception as e:
            print(f"Error redirecting to Google OAuth: {e}")
            return redirect(url_for('mock_google_login'))
    else:
        return redirect(url_for('mock_google_login'))

@app.route('/auth/google/mock')
def mock_google_login():
    return render_template('mock_google.html')

@app.route('/auth/google/callback')
def google_auth_callback():
    google_id = None
    email = None
    full_name = None
    
    mock_email = request.args.get('mock_email')
    mock_name = request.args.get('mock_name')
    mock_id = request.args.get('mock_id')
    
    if mock_email and mock_name and mock_id:
        google_id = mock_id
        email = mock_email.strip().lower()
        full_name = mock_name.strip()
    elif oauth and oauth.google:
        try:
            token = oauth.google.authorize_access_token()
            userinfo = token.get('userinfo')
            if userinfo:
                google_id = userinfo.get('sub')
                email = userinfo.get('email', '').strip().lower()
                full_name = userinfo.get('name', '').strip()
        except Exception as e:
            flash(f'Google authentication failed: {str(e)}', 'error')
            return redirect(url_for('login'))
            
    if not email or not google_id:
        flash('Could not retrieve user info from Google.', 'error')
        return redirect(url_for('login'))
        
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE google_id = ?', (google_id,)).fetchone()
    
    if user:
        session['user_id'] = user['id']
        session['user_name'] = user['full_name']
        session['user_email'] = user['email']
        conn.close()
        flash(f'Welcome back, {user["full_name"].split()[0]}!', 'success')
        return redirect(url_for('dashboard_overview'))
        
    user_by_email = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if user_by_email:
        conn.execute('UPDATE users SET google_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (google_id, user_by_email['id']))
        conn.commit()
        session['user_id'] = user_by_email['id']
        session['user_name'] = user_by_email['full_name']
        session['user_email'] = user_by_email['email']
        conn.close()
        flash(f'Linked Google sign-in to your account. Welcome back, {user_by_email["full_name"].split()[0]}!', 'success')
        return redirect(url_for('dashboard_overview'))
        
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (full_name, email, password_hash, google_id, subscription_plan)
        VALUES (?, ?, ?, ?, ?)
    ''', (full_name, email, '', google_id, 'free'))
    new_user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    session['user_id'] = new_user_id
    session['user_name'] = full_name
    session['user_email'] = email
    
    flash('Successfully registered with Google! Please select a plan.', 'success')
    return redirect(url_for('select_plan'))

@app.route('/dashboard/overview')
@login_required
def dashboard_overview():
    user = get_current_user()
    stats = get_dashboard_stats(session['user_id'])
    calendar = get_calendar_data()
    bmi = calculate_bmi(user['weight_kg'], user['height_cm'])
    fasting = is_fasting_today(user['religious_preference'])
    
    conn = get_db()
    today_meals = conn.execute('''
        SELECT ml.*, ef.name_english, ef.name_amharic, ef.food_category
        FROM meal_logs ml
        JOIN ethiopian_foods ef ON ml.food_id = ef.id
        WHERE ml.user_id = ? AND DATE(ml.logged_at) = ?
        ORDER BY ml.logged_at DESC
    ''', (session['user_id'], date.today().isoformat())).fetchall()
    conn.close()
    
    return render_template('dashboard.html', 
                         user=user, 
                         stats=stats, 
                         calendar=calendar,
                         bmi=bmi,
                         fasting=fasting,
                         today_meals=today_meals)

@app.route('/dashboard/food')
@login_required
def food_matrix():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    fasting_only = request.args.get('fasting_only', '0')
    
    conn = get_db()
    sql = 'SELECT * FROM ethiopian_foods WHERE 1=1'
    params = []
    
    if query:
        sql += ' AND (name_english LIKE ? OR name_amharic LIKE ?)'
        params.extend([f'%{query}%', f'%{query}%'])
    
    if category:
        sql += ' AND food_category = ?'
        params.append(category)
    
    if fasting_only == '1':
        sql += ' AND is_fasting_compatible = 1'
    
    foods = conn.execute(sql, params).fetchall()
    conn.close()
    
    return render_template('food_matrix.html', foods=foods)

@app.route('/api/foods/search')
@login_required
def search_foods():
    query = request.args.get('q', '')
    conn = get_db()
    foods = conn.execute(
        'SELECT * FROM ethiopian_foods WHERE name_english LIKE ? OR name_amharic LIKE ?',
        (f'%{query}%', f'%{query}%')
    ).fetchall()
    conn.close()
    return jsonify([dict(f) for f in foods])

@app.route('/api/meals/log', methods=['POST'])
@login_required
def log_meal():
    data = request.json
    food_id = data.get('food_id')
    serving_size = data.get('serving_size_g', 150)
    meal_type = data.get('meal_type', 'lunch')
    family_member_id = data.get('family_member_id')
    
    conn = get_db()
    food = conn.execute('SELECT * FROM ethiopian_foods WHERE id = ?', (food_id,)).fetchone()
    
    if not food:
        conn.close()
        return jsonify({'error': 'Food not found'}), 404
    
    multiplier = serving_size / 100
    
    total_calories = round(food['calories_per_100g'] * multiplier, 1)
    total_protein = round(food['protein_g'] * multiplier, 1)
    total_carbs = round(food['carbs_g'] * multiplier, 1)
    total_fat = round(food['fat_g'] * multiplier, 1)
    total_iron = round(food['iron_mg'] * multiplier, 1)
    total_sodium = round(food['sodium_mg'] * multiplier, 1)
    
    user = get_current_user()
    is_fasting = is_fasting_today(user['religious_preference'])
    
    conn.execute('''
        INSERT INTO meal_logs 
        (user_id, food_id, family_member_id, serving_size_g, meal_type, is_fasting_meal, fasting_type,
         total_calories, total_protein, total_carbs, total_fat, total_iron, total_sodium)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], food_id, family_member_id, serving_size, meal_type,
          1 if is_fasting else 0, is_fasting['fasting_name'] if is_fasting else None,
          total_calories, total_protein, total_carbs, total_fat, total_iron, total_sodium))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'calories': total_calories, 'protein': total_protein})

@app.route('/dashboard/tsom')
@login_required
def fasting_calibrator():
    conn = get_db()
    fasts = conn.execute('SELECT * FROM fasting_calendar ORDER BY start_date').fetchall()
    today = date.today().isoformat()
    current_period = conn.execute('''
        SELECT * FROM fasting_calendar
        WHERE start_date <= ? AND end_date >= ?
        ORDER BY start_date
        LIMIT 1
    ''', (today, today)).fetchone()
    conn.close()
    
    user = get_current_user()
    active_fast = is_fasting_today(user['religious_preference'])
    month_calendar = get_current_month_calendar()
    
    return render_template('fasting.html',
                         fasts=fasts,
                         active_fast=active_fast,
                         current_period=current_period,
                         month_label=month_calendar['month_label'],
                         calendar_days=month_calendar['days'])

@app.route('/dashboard/kitchen')
@login_required
def kitchen_assistant():
    return render_template('kitchen.html')

@app.route('/dashboard/ai')
@login_required
def ai_page():
    return render_template('ai_assistant.html')

@app.route('/api/kitchen/suggest', methods=['POST'])
@login_required
def kitchen_suggest():
    user = get_current_user()
    if user['subscription_plan'] not in ['plus', 'premium']:
        return jsonify({'error': 'Upgrade to Plus or Premium to use the Kitchen Assistant.'}), 403
    data = request.json
    ingredients = data.get('ingredients', [])
    
    conn = get_db()
    suggestions = []
    
    for ingredient in ingredients:
        foods = conn.execute('''
            SELECT * FROM ethiopian_foods 
            WHERE name_english LIKE ? OR name_amharic LIKE ?
        ''', (f'%{ingredient}%', f'%{ingredient}%')).fetchall()
        suggestions.extend([dict(f) for f in foods])
    
    total_protein = sum(s['protein_g'] for s in suggestions)
    total_calories = sum(s['calories_per_100g'] for s in suggestions)
    total_iron = sum(s['iron_mg'] for s in suggestions)
    
    deficiencies = []
    if total_protein < 20:
        deficiencies.append({'nutrient': 'Protein', 'message': 'Consider adding lentils or chickpeas'})
    if total_iron < 5:
        deficiencies.append({'nutrient': 'Iron', 'message': 'Add Gomen (collard greens) or Misir Wot'})
    
    conn.close()
    
    return jsonify({
        'suggestions': suggestions,
        'total_nutrition': {
            'protein': round(total_protein, 1),
            'calories': round(total_calories, 1),
            'iron': round(total_iron, 1)
        },
        'deficiencies': deficiencies
    })

@app.route('/dashboard/budget')
@login_required
def budget_optimizer():
    user = get_current_user()
    conn = get_db()

    daily_spent = conn.execute('''
        SELECT COALESCE(SUM(ef.avg_price_per_kg_etb * ml.serving_size_g / 1000), 0) as total
        FROM meal_logs ml
        JOIN ethiopian_foods ef ON ml.food_id = ef.id
        WHERE ml.user_id = ? AND DATE(ml.logged_at) = DATE('now')
    ''', (session['user_id'],)).fetchone()['total']
    
    weekly_spent = conn.execute('''
        SELECT COALESCE(SUM(ef.avg_price_per_kg_etb * ml.serving_size_g / 1000), 0) as total
        FROM meal_logs ml
        JOIN ethiopian_foods ef ON ml.food_id = ef.id
        WHERE ml.user_id = ? AND ml.logged_at >= DATE('now', '-7 days')
    ''', (session['user_id'],)).fetchone()['total']
    
    affordable_foods = conn.execute('''
        SELECT * FROM ethiopian_foods WHERE avg_price_per_kg_etb <= 60
        ORDER BY protein_g DESC
    ''').fetchall()
    
    conn.close()

    daily_budget = user['daily_budget_etb'] or 150
    budget_percent = min(round((daily_spent / daily_budget) * 100), 100) if daily_budget else 0
    
    return render_template('budget.html', 
                         user=user, 
                         daily_spent=round(daily_spent, 2),
                         weekly_spent=round(weekly_spent, 2),
                         daily_budget=daily_budget,
                         budget_percent=budget_percent,
                         affordable_foods=affordable_foods)

@app.route('/dashboard/family')
@login_required
def family_hub():
    conn = get_db()
    members = conn.execute(
        'SELECT * FROM family_members WHERE user_id = ?', 
        (session['user_id'],)
    ).fetchall()
    conn.close()
    
    return render_template('family.html', members=members)

@app.route('/api/family/add', methods=['POST'])
@login_required
def add_family_member():
    user = get_current_user()
    if user['subscription_plan'] != 'premium':
        return jsonify({'error': 'Upgrade to Premium to use the Family Hub.'}), 403
    data = request.json
    conn = get_db()
    
    conn.execute('''
        INSERT INTO family_members 
        (user_id, name, relationship, age, gender, medical_conditions, dietary_restrictions, is_fasting, fasting_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (session['user_id'], data['name'], data['relationship'], 
          data.get('age'), data.get('gender'), data.get('medical_conditions'),
          data.get('dietary_restrictions'), data.get('is_fasting', 0), data.get('fasting_type')))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/dashboard/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db()
    
    if request.method == 'POST':
        updates = {
            'age': request.form.get('age'),
            'gender': request.form.get('gender'),
            'height_cm': request.form.get('height_cm'),
            'weight_kg': request.form.get('weight_kg'),
            'activity_level': request.form.get('activity_level'),
            'dietary_preference': request.form.get('dietary_preference'),
            'religious_preference': request.form.get('religious_preference'),
            'fitness_goal': request.form.get('fitness_goal'),
            'health_goals': request.form.get('health_goals'),
            'medical_conditions': request.form.get('medical_conditions'),
            'daily_budget_etb': request.form.get('daily_budget_etb'),
            'weekly_budget_etb': request.form.get('weekly_budget_etb'),
            'monthly_budget_etb': request.form.get('monthly_budget_etb'),
            'preferred_language': request.form.get('preferred_language')
        }
        
        set_clause = ', '.join([f'{k} = ?' for k in updates if updates[k] is not None])
        values = [v for v in updates.values() if v is not None] + [session['user_id']]
        
        conn.execute(f'UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', values)
        conn.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    
    bmi = calculate_bmi(user['weight_kg'], user['height_cm'])
    
    return render_template('profile.html', user=user, bmi=bmi)

@app.route('/api/health/metrics', methods=['GET', 'POST'])
@login_required
def health_metrics():
    if request.method == 'POST':
        data = request.json
        conn = get_db()
        
        conn.execute('''
            INSERT INTO health_metrics 
            (user_id, weight_kg, blood_sugar_mgdl, blood_pressure_systolic, blood_pressure_diastolic,
             sleep_hours, sleep_quality, water_intake_ml, steps_count, activity_minutes, activity_type, mood_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], data.get('weight_kg'), data.get('blood_sugar'),
              data.get('bp_systolic'), data.get('bp_diastolic'), data.get('sleep_hours'),
              data.get('sleep_quality'), data.get('water_intake'), data.get('steps'),
              data.get('activity_minutes'), data.get('activity_type'), data.get('mood_score')))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    
    conn = get_db()
    metrics = conn.execute(
        'SELECT * FROM health_metrics WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 30',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    
    return jsonify([dict(m) for m in metrics])

@app.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_assistant():
    user = get_current_user()
    if user['subscription_plan'] != 'premium':
        return jsonify({'error': 'Upgrade to Premium to use the AI Assistant.'}), 403
    data = request.json
    question = data.get('question', '').lower()
    
    conn = get_db()
    fasting = is_fasting_today(user['religious_preference'])
    
    response = ""
    
    if 'diabetes' in question or 'blood sugar' in question:
        low_gi_foods = conn.execute(
            'SELECT * FROM ethiopian_foods WHERE glycemic_index < 40 ORDER BY glycemic_index'
        ).fetchall()
        response = f"I recommend these low glycemic foods: {', '.join([f['name_english'] for f in low_gi_foods[:5]])}. These help maintain stable blood sugar levels."
    
    elif 'gain weight' in question:
        high_cal_foods = conn.execute(
            'SELECT * FROM ethiopian_foods WHERE calories_per_100g > 200 ORDER BY calories_per_100g DESC'
        ).fetchall()
        response = f"To gain weight healthily, try: {', '.join([f['name_english'] for f in high_cal_foods[:5]])}. Aim for 3 meals plus 2 snacks daily."
    
    elif 'fasting' in question:
        if fasting:
            fasting_foods = conn.execute(
                'SELECT * FROM ethiopian_foods WHERE is_fasting_compatible = 1 AND protein_g > 5 ORDER BY protein_g DESC'
            ).fetchall()
            response = f"During {fasting['fasting_name']}, focus on these protein-rich fasting foods: {', '.join([f['name_english'] for f in fasting_foods[:5]])}. Add Gomen for iron absorption."
        else:
            response = "You're not currently in a fasting period. Would you like to see upcoming fasting schedules?"
    
    elif 'balanced' in question:
        response = "A balanced Ethiopian meal should include: 1 serving Injera (complex carbs), 1 serving Misir Wot or Shiro (protein), 1 serving Gomen (iron), and Atkilt (vitamins). This provides complete nutrition for about 400-500 calories."
    
    else:
        response = "I can help with: diabetes-friendly foods, weight gain tips, fasting nutrition, balanced meal suggestions, or budget-friendly options. What would you like to know?"
    
    conn.execute('''
        INSERT INTO ai_recommendations (user_id, recommendation_type, recommendation_text)
        VALUES (?, 'ai_chat', ?)
    ''', (session['user_id'], response))
    conn.commit()
    conn.close()
    
    return jsonify({'response': response})

@app.route('/api/achievements')
@login_required
def get_achievements():
    conn = get_db()
    achievements = conn.execute(
        'SELECT * FROM user_achievements WHERE user_id = ? ORDER BY earned_at DESC',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(a) for a in achievements])

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)