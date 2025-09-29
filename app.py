# app_postgresql.py - Complete, Corrected Version with PostgreSQL, SSL, and all Routes

from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_bcrypt import Bcrypt
import psycopg2 # CHANGED: PostgreSQL connector
from psycopg2 import extras # ADDED: For DictCursor to fetch results as dictionaries
import logging
from logging.handlers import RotatingFileHandler
import config
from datetime import datetime, timedelta
from decimal import Decimal
import csv
from io import StringIO
from flask import make_response

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
bcrypt = Bcrypt(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enable logging to file
if not app.debug:
    handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)

# Login required decorator
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def get_db_conn():
    """Establishes a PostgreSQL database connection with SSL."""
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASS,
            dbname=config.DB_NAME,
            sslmode='prefer'  # FIXED: Changed to 'prefer' for better compatibility
        )
        conn.autocommit = True
        logger.info("Database connection established successfully.")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

# Helper function to get a cursor that returns dictionaries
def get_dict_cursor(conn):
    return conn.cursor(cursor_factory=extras.DictCursor)

# Create tables functions
# ----------------------------------------------------
def create_auth_tables():
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(120) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("SELECT id FROM users WHERE username = %s", ('admin',))
            admin_user = cur.fetchone()

            if not admin_user:
                password_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
                cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                           ('admin', password_hash))
                logger.info("Default admin user created with password: admin123")
    except Exception as e:
        logger.error(f"Error creating auth tables: {e}")
    finally:
        conn.close()

def create_vehicles_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vehicles (
                    id SERIAL PRIMARY KEY,
                    vehicle_no VARCHAR(50) UNIQUE NOT NULL,
                    owner_name VARCHAR(100),
                    contact_number VARCHAR(20),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating vehicles table: {e}")
    finally:
        conn.close()

def create_spendings_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS spendings (
                    id SERIAL PRIMARY KEY,
                    vehicle_id INTEGER REFERENCES vehicles(id),
                    date DATE NOT NULL,
                    expense_month DATE,
                    category VARCHAR(100) NOT NULL,
                    reason TEXT,
                    amount NUMERIC(10, 2) NOT NULL,
                    spended_by VARCHAR(50),
                    mode VARCHAR(50),
                    marked BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating spendings table: {e}")
    finally:
        conn.close()

def create_payments_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    received_from VARCHAR(100),
                    reason TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating payments table: {e}")
    finally:
        conn.close()

def create_companies_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating companies table: {e}")
    finally:
        conn.close()

def create_employee_advances_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS employee_advances (
                    id SERIAL PRIMARY KEY,
                    employee_name VARCHAR(100) NOT NULL,
                    date DATE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    purpose TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating employee advances table: {e}")
    finally:
        conn.close()

def create_employee_balance_view():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE VIEW employee_balance AS
                SELECT 
                    employee_name,
                    COALESCE(SUM(amount), 0) as total_advances,
                    COALESCE((
                        SELECT SUM(amount) 
                        FROM spendings 
                        WHERE spended_by = employee_advances.employee_name
                    ), 0) as total_expenses,
                    COALESCE(SUM(amount), 0) - COALESCE((
                        SELECT SUM(amount) 
                        FROM spendings 
                        WHERE spended_by = employee_advances.employee_name
                    ), 0) as balance
                FROM employee_advances 
                GROUP BY employee_name;
            """)
    except Exception as e:
        logger.error(f"Error creating employee_balance view: {e}")
    finally:
        conn.close()

def create_hired_vehicles_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hired_vehicles (
                    id SERIAL PRIMARY KEY,
                    vehicle_no VARCHAR(50) UNIQUE NOT NULL,
                    owner_name VARCHAR(255),
                    contact_number VARCHAR(20),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating hired vehicles table: {e}")
    finally:
        conn.close()

def create_hired_vehicle_transactions_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hired_vehicle_transactions (
                    id SERIAL PRIMARY KEY,
                    hired_vehicle_id INTEGER REFERENCES hired_vehicles(id),
                    transaction_type VARCHAR(50) NOT NULL,
                    transaction_date DATE NOT NULL,
                    month_year DATE NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    description TEXT,
                    reference_no VARCHAR(100),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating hired_vehicle_transactions table: {e}")
    finally:
        conn.close()

def create_company_sales_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_sales (
                    id SERIAL PRIMARY KEY,
                    sale_date DATE NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    invoice_number VARCHAR(100),
                    sale_amount NUMERIC(12,2) NOT NULL,
                    description TEXT,
                    month_year DATE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating company_sales table: {e}")
    finally:
        conn.close()

def create_company_payments_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_payments (
                    id SERIAL PRIMARY KEY,
                    payment_date DATE NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    received_amount NUMERIC(12,2) NOT NULL,
                    payment_mode VARCHAR(50) NOT NULL,
                    reference_number VARCHAR(100),
                    description TEXT,
                    month_year DATE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
    except Exception as e:
        logger.error(f"Error creating company_payments table: {e}")
    finally:
        conn.close()

def initialize_database():
    """Initialize all database tables and views"""
    create_auth_tables()
    create_vehicles_table()
    create_spendings_table()
    create_payments_table()
    create_companies_table()
    create_employee_advances_table()
    create_employee_balance_view()
    create_hired_vehicles_table()
    create_hired_vehicle_transactions_table()
    create_company_sales_table()
    create_company_payments_table()
    logger.info("All database tables initialized successfully")

# ----------------------------------------------------

# Home / Dashboard with monthly expense tracking
@app.route('/')
@login_required
def index():
    conn = get_db_conn()
    vehicles = []
    monthly_vehicle_expenses = []
    monthly_trend = []
    totals = {
        'vehicles': 0,
        'credited': 0,
        'debited': 0,
        'balance': 0,
        'current_month': 0,
        'prev_month': 0
    }

    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT v.id, v.vehicle_no, COALESCE(SUM(s.amount),0) AS total_spent FROM vehicles v LEFT JOIN spendings s ON v.id=s.vehicle_id GROUP BY v.id, v.vehicle_no")
            vehicles = cur.fetchall()

            cur.execute("SELECT COUNT(*) AS c FROM vehicles")
            total_vehicles = cur.fetchone()['c']

            cur.execute("SELECT COALESCE(SUM(amount),0) AS total_credited FROM payments")
            total_credited = cur.fetchone()['total_credited'] or 0

            # FIXED: Removed incorrect table alias 's'
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total_debited FROM spendings WHERE spended_by IS NOT NULL OR mode IS NOT NULL")
            total_debited = cur.fetchone()['total_debited'] or 0

            balance = Decimal(total_credited) - Decimal(total_debited)

            current_month = datetime.now().strftime('%Y-%m-01')
            cur.execute("SELECT COALESCE(SUM(amount),0) as current_month_total FROM spendings WHERE expense_month = %s", (current_month,))
            current_month_total = cur.fetchone()['current_month_total'] or 0

            prev_month = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-01')
            cur.execute("SELECT COALESCE(SUM(amount),0) as prev_month_total FROM spendings WHERE expense_month = %s", (prev_month,))
            prev_month_total = cur.fetchone()['prev_month_total'] or 0

            cur.execute("""
                SELECT
                    v.vehicle_no,
                    SUM(s.amount) as monthly_total
                FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.expense_month = %s
                GROUP BY v.vehicle_no
                ORDER BY monthly_total DESC
            """, (current_month,))
            monthly_vehicle_expenses = cur.fetchall()

            cur.execute("""
                SELECT
                    TO_CHAR(expense_month, 'YYYY-MM') as month,
                    SUM(amount) as total_expense
                FROM spendings
                WHERE expense_month >= (CURRENT_DATE - INTERVAL '6 months')
                GROUP BY expense_month
                ORDER BY expense_month DESC
            """)
            monthly_trend = cur.fetchall()

            totals = {
                'vehicles': total_vehicles,
                'credited': float(total_credited or 0),
                'debited': float(total_debited or 0),
                'balance': float(balance),
                'current_month': float(current_month_total),
                'prev_month': float(prev_month_total)
            }

    except Exception as e:
        app.logger.error(f"Error in index route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()

    return render_template('index.html',
                         vehicles=vehicles,
                         monthly_vehicle_expenses=monthly_vehicle_expenses,
                         monthly_trend=monthly_trend,
                         totals=totals)

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_conn()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cur.fetchone()
                if user and bcrypt.check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    flash('Login successful!', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Invalid username or password.', 'error')
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login', 'error')
        finally:
            conn.close()
    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Vehicles page & add vehicle
@app.route('/vehicles', methods=['GET','POST'])
@login_required
def vehicles_page():
    conn = get_db_conn()
    vehicles = []
    try:
        if request.method == 'POST':
            vehicle_no = request.form.get('vehicle_no').strip()
            owner_name = request.form.get('owner_name', '').strip()
            contact_number = request.form.get('contact_number', '').strip()

            if not vehicle_no:
                flash('Vehicle number cannot be empty.', 'error')
            else:
                with get_dict_cursor(conn) as cur:
                    cur.execute("SELECT id FROM vehicles WHERE vehicle_no = %s", (vehicle_no,))
                    if cur.fetchone():
                        flash(f'Vehicle {vehicle_no} already exists.', 'error')
                    else:
                        cur.execute("INSERT INTO vehicles (vehicle_no, owner_name, contact_number) VALUES (%s, %s, %s)",
                                   (vehicle_no, owner_name, contact_number))
                        flash('Vehicle added successfully!', 'success')
                        return redirect(url_for('vehicles_page'))

        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM vehicles ORDER BY vehicle_no")
            vehicles = cur.fetchall()
    except Exception as e:
        app.logger.error(f"Error in vehicles_page route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    return render_template('vehicles.html', vehicles=vehicles)

# Delete Vehicle
@app.route('/delete_vehicle/<int:id>', methods=['POST'])
@login_required
def delete_vehicle(id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT COUNT(*) as count FROM spendings WHERE vehicle_id = %s", (id,))
            if cur.fetchone()['count'] > 0:
                flash('Cannot delete vehicle. Delete all associated spendings first.', 'error')
            else:
                cur.execute("DELETE FROM vehicles WHERE id = %s", (id,))
                flash('Vehicle deleted successfully!', 'success')
    except Exception as e:
        app.logger.error(f"Error deleting vehicle: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('vehicles_page'))

# Spendings list & add spending
@app.route('/spendings', methods=['GET','POST'])
@login_required
def spendings():
    conn = get_db_conn()
    vehicles = []
    paid_rows = []
    unpaid_rows = []
    settled_rows = []
    monthly_totals = []
    total_spent = 0
    total_unpaid = 0

    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT id, vehicle_no FROM vehicles ORDER BY vehicle_no")
            vehicles = cur.fetchall()

            if request.method == 'POST':
                vehicle_id = request.form.get('vehicle_id')
                date_str = request.form.get('date')
                expense_month_str = request.form.get('expense_month')
                category = request.form.get('category').strip()
                reason = request.form.get('reason', '').strip()
                amount = request.form.get('amount')
                spended_by = request.form.get('spended_by', '').strip()
                mode = request.form.get('mode', '').strip()

                if not all([vehicle_id, date_str, expense_month_str, category, amount]):
                    flash('Missing required fields.', 'error')
                    return redirect(url_for('spendings'))

                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                expense_month = datetime.strptime(expense_month_str, '%Y-%m').date().replace(day=1)
                amount_decimal = Decimal(amount)

                spended_by = spended_by if spended_by else None
                mode = mode if mode else None

                cur.execute("""
                    INSERT INTO spendings (vehicle_id, date, expense_month, category, reason, amount, spended_by, mode)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (vehicle_id, date_obj, expense_month, category, reason, amount_decimal, spended_by, mode))
                flash('Spending recorded successfully!', 'success')
                return redirect(url_for('spendings'))

            # Fetch unpaid payments
            cur.execute("""
                SELECT s.*, v.vehicle_no FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.spended_by IS NULL OR s.mode IS NULL
                ORDER BY s.date DESC
            """)
            unpaid_rows = cur.fetchall()

            # Fetch paid payments for the last 30 days
            cur.execute("""
                SELECT s.*, v.vehicle_no FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                AND s.date >= (CURRENT_DATE - INTERVAL '30 days')
                ORDER BY s.date DESC
            """)
            paid_rows = cur.fetchall()

            # Fetch settled payments (historical - older than 30 days)
            cur.execute("""
                SELECT s.*, v.vehicle_no
                FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                AND s.date < (CURRENT_DATE - INTERVAL '30 days')
                ORDER BY s.date DESC
            """)
            settled_rows = cur.fetchall()

            # FIXED: Removed incorrect table alias 's'
            cur.execute("SELECT COALESCE(SUM(amount),0) as total_spent FROM spendings WHERE spended_by IS NOT NULL AND mode IS NOT NULL")
            total_spent = cur.fetchone()['total_spent'] or 0
            
            cur.execute("SELECT COALESCE(SUM(amount),0) as total_unpaid FROM spendings WHERE spended_by IS NULL OR mode IS NULL")
            total_unpaid = cur.fetchone()['total_unpaid'] or 0

            # Monthly totals by expense month
            cur.execute("""
                SELECT expense_month, COALESCE(SUM(amount),0) as monthly_total
                FROM spendings
                WHERE spended_by IS NOT NULL AND mode IS NOT NULL
                GROUP BY expense_month
                ORDER BY expense_month DESC
            """)
            monthly_totals = cur.fetchall()

    except Exception as e:
        app.logger.error(f"Error in spendings route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()

    today = datetime.now().strftime('%Y-%m-%d')
    current_month = datetime.now().strftime('%Y-%m')
    
    return render_template('spendings.html',
                           vehicles=vehicles,
                           paid_rows=paid_rows,
                           unpaid_rows=unpaid_rows,
                           settled_rows=settled_rows,
                           monthly_totals=monthly_totals,
                           total_spent=float(total_spent),
                           total_unpaid=float(total_unpaid),
                           today=today,
                           current_month=current_month)

# Delete Spending
@app.route('/delete_spending/<int:id>', methods=['POST'])
@login_required
def delete_spending(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM spendings WHERE id = %s", (id,))
            flash('Spending deleted successfully!', 'success')
    except Exception as e:
        app.logger.error(f"Error deleting spending: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('spendings'))

# Mark unpaid payment as paid
@app.route('/mark_paid/<int:id>', methods=['POST'])
@login_required
def mark_paid(id):
    conn = get_db_conn()
    try:
        data = request.get_json()
        spended_by = data.get('spended_by', 'MSR')
        mode = data.get('mode', 'UPI')
        
        with conn.cursor() as cur:
            update_reason = f" - Marked Paid on {datetime.now().strftime('%Y-%m-%d')}"
            cur.execute("""
                UPDATE spendings
                SET spended_by=%s, mode=%s,
                reason=COALESCE(reason, '') || %s
                WHERE id=%s
            """, (spended_by, mode, update_reason, id))
            conn.commit()
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error marking paid: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# Process settlement for multiple unpaid payments
@app.route('/process_settlement', methods=['POST'])
@login_required
def process_settlement():
    conn = get_db_conn()
    try:
        data = request.get_json()
        spending_ids = data.get('spending_ids', [])
        spended_by = data.get('spended_by', 'MSR')
        mode = data.get('mode', 'UPI')
        
        if not spending_ids:
            return jsonify({'success': False, 'message': 'No spendings selected'})
        
        spending_ids = [int(id) for id in spending_ids]
        
        with get_dict_cursor(conn) as cur:
            placeholders = ','.join(['%s'] * len(spending_ids))
            cur.execute(f"SELECT SUM(amount) as total FROM spendings WHERE id IN ({placeholders})", spending_ids)
            total_amount = cur.fetchone()['total'] or 0
            
            update_query = f"""
                UPDATE spendings 
                SET spended_by=%s, mode=%s, 
                reason=COALESCE(reason, '') || %s 
                WHERE id IN ({placeholders})
            """
            update_params = [spended_by, mode, f" - Settled on {datetime.now().strftime('%Y-%m-%d')}"] + spending_ids
            cur.execute(update_query, update_params)
            
            conn.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Settlement processed for {len(spending_ids)} payments totaling ₹{total_amount}'
            })
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in process_settlement: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# Payments list & add payment (Credit)
@app.route('/payments', methods=['GET', 'POST'])
@login_required
def payments():
    conn = get_db_conn()
    payment_rows = []
    total_credited = 0
    try:
        with get_dict_cursor(conn) as cur:
            if request.method == 'POST':
                date_str = request.form.get('date')
                amount = request.form.get('amount')
                received_from = request.form.get('received_from', '').strip()
                reason = request.form.get('reason', '').strip()

                if not all([date_str, amount]):
                    flash('Missing required fields.', 'error')
                    return redirect(url_for('payments'))

                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                amount_decimal = Decimal(amount)

                received_from = received_from if received_from else None
                reason = reason if reason else None

                cur.execute("""
                    INSERT INTO payments (date, amount, received_from, reason)
                    VALUES (%s, %s, %s, %s)
                """, (date_obj, amount_decimal, received_from, reason))
                flash('Payment recorded successfully!', 'success')
                return redirect(url_for('payments'))

            cur.execute("SELECT * FROM payments ORDER BY date DESC")
            payment_rows = cur.fetchall()

            cur.execute("SELECT COALESCE(SUM(amount),0) AS total_credited FROM payments")
            total_credited = cur.fetchone()['total_credited'] or 0

    except Exception as e:
        app.logger.error(f"Error in payments route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('payments.html',
                           payment_rows=payment_rows,
                           total_credited=float(total_credited),
                           today=today)

# Delete Payment
@app.route('/delete_payment/<int:id>', methods=['POST'])
@login_required
def delete_payment(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM payments WHERE id = %s", (id,))
            flash('Payment deleted successfully!', 'success')
    except Exception as e:
        app.logger.error(f"Error deleting payment: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('payments'))

# Employee Advances
@app.route('/employee_advances', methods=['GET', 'POST'])
@login_required
def employee_advances():
    conn = get_db_conn()
    
    if request.method == 'POST':
        try:
            employee_name = request.form['employee_name']
            date = request.form['date']
            amount = request.form['amount']
            purpose = request.form.get('purpose', '')

            if not employee_name or not date or not amount:
                flash('Please fill in all required fields.', 'error')
            else:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO employee_advances 
                        (employee_name, date, amount, purpose) 
                        VALUES (%s, %s, %s, %s)
                    """, (employee_name, date, amount, purpose))
                    conn.commit()
                
                flash(f'Advance added successfully for {employee_name}.', 'success')
                return redirect(url_for('employee_advances'))
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding employee advance: {str(e)}")
            flash('An error occurred while adding the advance.', 'error')
    
    employee_balances = []
    advances = []
    
    try:
        with get_dict_cursor(conn) as cur:
            # Fetch balances from the view
            cur.execute("SELECT * FROM employee_balance ORDER BY employee_name")
            employee_balances = cur.fetchall()
            
            # Convert Decimal types to float for safe display
            for employee in employee_balances:
                for key in ['total_advances', 'total_expenses', 'balance']:
                    if isinstance(employee.get(key), Decimal):
                        employee[key] = float(employee[key])
                        
            # Fetch all individual advances
            cur.execute("SELECT * FROM employee_advances ORDER BY date DESC")
            advances = cur.fetchall()
            
            # Convert amount for display
            for advance in advances:
                 if isinstance(advance.get('amount'), Decimal):
                    advance['amount'] = float(advance['amount'])

    except Exception as e:
        logger.error(f"Database error in employee_advances: {e}")
        flash(f'Error loading employee advances: {str(e)}', 'error')
        
    finally:
        if conn:
            conn.close()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('employee_advances.html',
                         advances=advances,
                         employee_balances=employee_balances,
                         today=today)

# Hired Vehicles Audit
@app.route('/hired_vehicles_audit', methods=['GET', 'POST'])
@login_required
def hired_vehicles_audit():
    conn = get_db_conn()
    hired_vehicles = []
    recent_transactions = []
    hired_vehicles_summary = []
    
    try:
        with get_dict_cursor(conn) as cur:
            if request.method == 'POST':
                action = request.form.get('action')
                
                if action == 'add_hired_vehicle':
                    vehicle_no = request.form.get('vehicle_no').strip()
                    owner_name = request.form.get('owner_name').strip()
                    contact_number = request.form.get('contact_number', '').strip()
                    
                    cur.execute(
                        "INSERT INTO hired_vehicles (vehicle_no, owner_name, contact_number) VALUES (%s, %s, %s)",
                        (vehicle_no, owner_name, contact_number)
                    )
                    flash('Hired vehicle added successfully', 'success')
                    
                elif action == 'add_transaction':
                    hired_vehicle_id = request.form.get('hired_vehicle_id')
                    transaction_type = request.form.get('transaction_type')
                    transaction_date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d').date()
                    month_year = datetime.strptime(request.form.get('month_year'), '%Y-%m').date().replace(day=1)
                    amount = request.form.get('amount')
                    description = request.form.get('description', '').strip()
                    reference_no = request.form.get('reference_no', '').strip()
                    
                    cur.execute("""
                        INSERT INTO hired_vehicle_transactions 
                        (hired_vehicle_id, transaction_type, transaction_date, month_year, amount, description, reference_no)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (hired_vehicle_id, transaction_type, transaction_date, month_year, amount, description, reference_no))
                    
                    flash('Transaction added successfully', 'success')
            
            # Get all hired vehicles
            cur.execute("SELECT * FROM hired_vehicles ORDER BY vehicle_no")
            hired_vehicles = cur.fetchall()
            
            # Get recent transactions
            cur.execute("""
                SELECT t.*, hv.vehicle_no, hv.owner_name 
                FROM hired_vehicle_transactions t
                JOIN hired_vehicles hv ON t.hired_vehicle_id = hv.id
                ORDER BY t.transaction_date DESC, t.created_at DESC
                LIMIT 50
            """)
            recent_transactions = cur.fetchall()
            
            # Get summary for all hired vehicles
            for vehicle in hired_vehicles:
                cur.execute("""
                    SELECT 
                        SUM(CASE WHEN transaction_type = 'sale' THEN amount ELSE 0 END) as total_sales,
                        SUM(CASE WHEN transaction_type = 'payment' THEN amount ELSE 0 END) as total_payments
                    FROM hired_vehicle_transactions 
                    WHERE hired_vehicle_id = %s
                """, (vehicle['id'],))
                summary = cur.fetchone()
                
                hired_vehicles_summary.append({
                    'id': vehicle['id'],
                    'vehicle_no': vehicle['vehicle_no'],
                    'owner_name': vehicle['owner_name'],
                    'total_sales': float(summary['total_sales'] or 0),
                    'total_payments': float(summary['total_payments'] or 0)
                })
                
    except Exception as e:
        app.logger.error(f"Error in hired_vehicles_audit: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    
    today = datetime.now().strftime('%Y-%m-%d')
    current_month = datetime.now().strftime('%Y-%m')
    
    return render_template('hired_vehicles_audit.html',
                         hired_vehicles=hired_vehicles,
                         recent_transactions=recent_transactions,
                         hired_vehicles_summary=hired_vehicles_summary,
                         today=today,
                         current_month=current_month)

# Company Audit
@app.route('/company_audit', methods=['GET', 'POST'])
@login_required
def company_audit():
    conn = get_db_conn()
    recent_sales = []
    recent_payments = []
    company_summary = []
    company_list = []
    totals = {
        'total_sales': 0,
        'total_received': 0,
        'pending_amount': 0,
        'total_companies': 0
    }
    
    try:
        with get_dict_cursor(conn) as cur:
            if request.method == 'POST':
                action = request.form.get('action')
                
                if action == 'add_sale':
                    sale_date = datetime.strptime(request.form.get('sale_date'), '%Y-%m-%d').date()
                    company_name = request.form.get('company_name').strip()
                    invoice_number = request.form.get('invoice_number', '').strip()
                    sale_amount = request.form.get('sale_amount')
                    month_year = datetime.strptime(request.form.get('month_year'), '%Y-%m').date().replace(day=1)
                    description = request.form.get('description', '').strip()
                    
                    cur.execute("""
                        INSERT INTO company_sales 
                        (sale_date, company_name, invoice_number, sale_amount, month_year, description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (sale_date, company_name, invoice_number, sale_amount, month_year, description))
                    
                    flash('Sale recorded successfully', 'success')
                    
                elif action == 'add_payment':
                    payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
                    company_name = request.form.get('company_name').strip()
                    if company_name == '_new':
                        company_name = request.form.get('new_company_name').strip()
                    received_amount = request.form.get('received_amount')
                    payment_mode = request.form.get('payment_mode')
                    reference_number = request.form.get('reference_number', '').strip()
                    month_year = datetime.strptime(request.form.get('month_year'), '%Y-%m').date().replace(day=1)
                    description = request.form.get('description', '').strip()
                    
                    cur.execute("""
                        INSERT INTO company_payments 
                        (payment_date, company_name, received_amount, payment_mode, reference_number, month_year, description)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (payment_date, company_name, received_amount, payment_mode, reference_number, month_year, description))
                    
                    flash('Payment recorded successfully', 'success')
            
            # Get recent sales
            cur.execute("SELECT * FROM company_sales ORDER BY sale_date DESC LIMIT 20")
            recent_sales = cur.fetchall()
            
            # Get recent payments
            cur.execute("SELECT * FROM company_payments ORDER BY payment_date DESC LIMIT 20")
            recent_payments = cur.fetchall()
            
            # Get unique company names
            cur.execute("SELECT DISTINCT company_name FROM company_sales UNION SELECT DISTINCT company_name FROM company_payments ORDER BY company_name")
            company_list = [row['company_name'] for row in cur.fetchall()]
            
            # Get company-wise summary
            for company in company_list:
                cur.execute("SELECT SUM(sale_amount) as total_sales FROM company_sales WHERE company_name = %s", (company,))
                sales_result = cur.fetchone()
                total_sales = sales_result['total_sales'] or 0
                
                cur.execute("SELECT SUM(received_amount) as total_received FROM company_payments WHERE company_name = %s", (company,))
                payments_result = cur.fetchone()
                total_received = payments_result['total_received'] or 0
                
                cur.execute("SELECT MAX(sale_date) as last_sale_date FROM company_sales WHERE company_name = %s", (company,))
                last_sale = cur.fetchone()
                
                cur.execute("SELECT MAX(payment_date) as last_payment_date FROM company_payments WHERE company_name = %s", (company,))
                last_payment = cur.fetchone()
                
                company_summary.append({
                    'company_name': company,
                    'total_sales': float(total_sales),
                    'total_received': float(total_received),
                    'pending_amount': float(total_sales - total_received),
                    'last_sale_date': last_sale['last_sale_date'].strftime('%Y-%m-%d') if last_sale['last_sale_date'] else None,
                    'last_payment_date': last_payment['last_payment_date'].strftime('%Y-%m-%d') if last_payment['last_payment_date'] else None
                })
            
            # Get overall totals
            cur.execute("SELECT SUM(sale_amount) as total_sales FROM company_sales")
            totals['total_sales'] = float(cur.fetchone()['total_sales'] or 0)
            
            cur.execute("SELECT SUM(received_amount) as total_received FROM company_payments")
            totals['total_received'] = float(cur.fetchone()['total_received'] or 0)
            
            totals['pending_amount'] = totals['total_sales'] - totals['total_received']
            totals['total_companies'] = len(company_list)
                
    except Exception as e:
        app.logger.error(f"Error in company_audit: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    
    today = datetime.now().strftime('%Y-%m-%d')
    current_month = datetime.now().strftime('%Y-%m')
    
    return render_template('company_audit.html',
                         recent_sales=recent_sales,
                         recent_payments=recent_payments,
                         company_summary=company_summary,
                         company_list=company_list,
                         totals=totals,
                         today=today,
                         current_month=current_month)

# Export data to CSV
@app.route('/export/<data_type>')
@login_required
def export_data(data_type):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            if data_type == 'paid_spendings':
                cur.execute("""
                    SELECT s.date, v.vehicle_no, s.category, s.reason, s.amount, s.spended_by, s.mode 
                    FROM spendings s 
                    JOIN vehicles v ON s.vehicle_id = v.id 
                    WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                    ORDER BY s.date DESC
                """)
                data = cur.fetchall()
                filename = 'paid_spendings.csv'
                
            elif data_type == 'unpaid_spendings':
                cur.execute("""
                    SELECT s.date, v.vehicle_no, s.category, s.reason, s.amount 
                    FROM spendings s 
                    JOIN vehicles v ON s.vehicle_id = v.id 
                    WHERE s.spended_by IS NULL OR s.mode IS NULL
                    ORDER BY s.date DESC
                """)
                data = cur.fetchall()
                filename = 'unpaid_spendings.csv'
                
            elif data_type == 'payments':
                cur.execute("""
                    SELECT p.date, p.received_from as company_name, p.amount, p.reason
                    FROM payments p 
                    ORDER BY p.date DESC
                """)
                data = cur.fetchall()
                filename = 'payments.csv'
                
            elif data_type == 'vehicles':
                cur.execute("SELECT vehicle_no, owner_name, contact_number, created_at FROM vehicles ORDER BY vehicle_no")
                data = cur.fetchall()
                filename = 'vehicles.csv'
                
            elif data_type == 'monthly_expenses':
                cur.execute("""
                    SELECT 
                        TO_CHAR(expense_month, 'YYYY-MM') as month,
                        v.vehicle_no,
                        SUM(s.amount) as total_expense
                    FROM spendings s
                    JOIN vehicles v ON s.vehicle_id = v.id
                    WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                    GROUP BY expense_month, v.vehicle_no
                    ORDER BY expense_month DESC, total_expense DESC
                """)
                data = cur.fetchall()
                filename = 'monthly_expenses.csv'
                
            else:
                return "Invalid data type", 400
            
            output = StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            
            response = app.response_class(
                response=output.getvalue(),
                status=200,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename={filename}'}
            )
            return response
            
    except Exception as e:
        app.logger.error(f"Error exporting data: {e}")
        return "Error exporting data", 500
    finally:
        conn.close()

# Vehicle monthly spendings (AJAX fetch)
@app.route('/vehicle_spendings/<int:vehicle_id>')
@login_required
def vehicle_spendings(vehicle_id):
    month = request.args.get('month')
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            q = "SELECT * FROM spendings WHERE vehicle_id=%s"
            params = [vehicle_id]
            if month:
                q += " AND TO_CHAR(expense_month,'YYYY-MM')=%s"
                params.append(month)
            q += " ORDER BY date DESC"
            cur.execute(q, params)
            rows = cur.fetchall()
    except Exception as e:
        app.logger.error(f"Error in vehicle_spendings: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
    
    # Convert to serializable format
    serializable_rows = []
    for row in rows:
        row_dict = dict(row)
        # Convert date objects to strings
        for key, value in row_dict.items():
            if hasattr(value, 'strftime'):
                row_dict[key] = value.strftime('%Y-%m-%d')
            elif isinstance(value, Decimal):
                row_dict[key] = float(value)
        serializable_rows.append(row_dict)
    
    return jsonify(serializable_rows)

# API: Overall monthly expenses
@app.route('/api/overall_monthly_expenses')
@login_required
def overall_monthly_expenses():
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("""
                SELECT 
                    expense_month,
                    SUM(amount) as total_monthly_expense
                FROM spendings
                WHERE spended_by IS NOT NULL AND mode IS NOT NULL
                GROUP BY expense_month
                ORDER BY expense_month DESC
            """)
            
            results = cur.fetchall()
            for result in results:
                if result['expense_month']:
                    result['expense_month'] = result['expense_month'].strftime('%Y-%m')
                if 'total_monthly_expense' in result:
                    result['total_monthly_expense'] = float(result['total_monthly_expense'])
                    
            return jsonify(results)
            
    except Exception as e:
        app.logger.error(f"Error in overall_monthly_expenses: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# Change Password route
@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'error')
            return render_template('change_password.html')

        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('change_password.html')

        conn = get_db_conn()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute("SELECT password_hash FROM users WHERE id = %s", (session['user_id'],))
                user = cur.fetchone()

                if user and bcrypt.check_password_hash(user['password_hash'], current_password):
                    new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
                    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                               (new_password_hash, session['user_id']))

                    logger.info(f"User {session['username']} changed password successfully")
                    flash('Password changed successfully!', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Current password is incorrect.', 'error')

        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            flash('An error occurred while changing password.', 'error')
        finally:
            conn.close()

    return render_template('change_password.html')

@app.route('/clear_cookies')
def clear_cookies():
    response = make_response("Cookies cleared - <a href='/'>Go Home</a>")
    response.set_cookie('session', '', expires=0)
    response.set_cookie(app.session_cookie_name, '', expires=0)
    return response

# Monthly expenses report - MISSING ROUTE
@app.route('/monthly_report')
@login_required
def monthly_report():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        with get_dict_cursor(conn) as cur:
            cur.execute("""
                SELECT s.*, v.vehicle_no 
                FROM spendings s 
                JOIN vehicles v ON s.vehicle_id = v.id 
                WHERE s.expense_month = %s 
                ORDER BY s.category, s.date
            """, (datetime.strptime(month, '%Y-%m').date().replace(day=1),))
            spendings = cur.fetchall()
            
            cur.execute("""
                SELECT COALESCE(SUM(amount),0) as total 
                FROM spendings 
                WHERE expense_month = %s
            """, (datetime.strptime(month, '%Y-%m').date().replace(day=1),))
            total = cur.fetchone()['total']
            
            cur.execute("""
                SELECT DISTINCT expense_month 
                FROM spendings 
                WHERE expense_month IS NOT NULL 
                ORDER BY expense_month DESC
            """)
            available_months = [m['expense_month'].strftime('%Y-%m') for m in cur.fetchall()]
            
    except Exception as e:
        app.logger.error(f"Error in monthly_report: {str(e)}")
        flash(f'Error generating report: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        conn.close()
    
    return render_template('monthly_report.html', 
                         spendings=spendings, 
                         total=float(total), 
                         selected_month=month,
                         available_months=available_months)

# API: Monthly expenses by vehicle - MISSING ROUTE
@app.route('/api/monthly_vehicle_expenses/<month>')
@login_required
def monthly_vehicle_expenses(month):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
            
            cur.execute("""
                SELECT 
                    v.vehicle_no,
                    s.expense_month,
                    SUM(s.amount) as monthly_total
                FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.expense_month = %s
                GROUP BY v.vehicle_no, s.expense_month
                ORDER BY monthly_total DESC
            """, (month_date,))
            
            results = cur.fetchall()
            for result in results:
                result['expense_month'] = result['expense_month'].strftime('%Y-%m')
                if 'monthly_total' in result:
                    result['monthly_total'] = float(result['monthly_total'])
                    
            return jsonify(results)
            
    except Exception as e:
        app.logger.error(f"Error in monthly_vehicle_expenses: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# Edit spending - GET data for editing - MISSING ROUTE
@app.route('/get_spending/<int:id>')
@login_required
def get_spending(id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM spendings WHERE id=%s", (id,))
            spending = cur.fetchone()
            
            if not spending:
                return jsonify({'success': False, 'error': 'Spending record not found'}), 404
            
            return jsonify({
                'success': True,
                'spending': {
                    'id': spending['id'],
                    'date': spending['date'].strftime('%Y-%m-%d'),
                    'expense_month': spending['expense_month'].strftime('%Y-%m') if spending['expense_month'] else '',
                    'vehicle_id': spending['vehicle_id'],
                    'category': spending['category'],
                    'reason': spending['reason'] or '',
                    'amount': float(spending['amount']),
                    'spended_by': spending['spended_by'] or '',
                    'mode': spending['mode'] or ''
                }
            })
    except Exception as e:
        app.logger.error(f"Error in get_spending: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# Update spending - POST to save changes - MISSING ROUTE
@app.route('/update_spending/<int:id>', methods=['POST'])
@login_required
def update_spending(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # Get form data
            date_str = request.form.get('date')
            expense_month_str = request.form.get('expense_month')
            vehicle_id = request.form.get('vehicle_id')
            category = request.form.get('category')
            reason = request.form.get('reason', '')
            amount = request.form.get('amount')
            spended_by = request.form.get('spended_by')
            mode = request.form.get('mode')
            
            # Validate required fields
            if not all([date_str, expense_month_str, vehicle_id, category, amount]):
                return jsonify({'success': False, 'error': 'Missing required fields'})
            
            try:
                payment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                expense_month = datetime.strptime(expense_month_str, '%Y-%m').date().replace(day=1)
                amount_decimal = Decimal(amount)
            except (ValueError, TypeError) as e:
                return jsonify({'success': False, 'error': 'Invalid date or amount format'})
            
            # Check if record exists
            cur.execute("SELECT id FROM spendings WHERE id=%s", (id,))
            if not cur.fetchone():
                return jsonify({'success': False, 'error': 'Spending record not found'})
            
            # Handle NULL values for unpaid payments
            if not spended_by or not mode:
                cur.execute("""
                    UPDATE spendings 
                    SET date=%s, expense_month=%s, vehicle_id=%s, category=%s, 
                    reason=%s, amount=%s, spended_by=NULL, mode=NULL 
                    WHERE id=%s
                """, (payment_date, expense_month, vehicle_id, category, reason, amount_decimal, id))
            else:
                cur.execute("""
                    UPDATE spendings 
                    SET date=%s, expense_month=%s, vehicle_id=%s, category=%s, 
                    reason=%s, amount=%s, spended_by=%s, mode=%s 
                    WHERE id=%s
                """, (payment_date, expense_month, vehicle_id, category, reason, amount_decimal, spended_by, mode, id))
            
            conn.commit()
            return jsonify({'success': True, 'message': 'Spending updated successfully'})
            
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in update_spending: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# AJAX toggle mark/unmark - MISSING ROUTE
@app.route('/toggle_mark', methods=['POST'])
@login_required
def toggle_mark():
    sid = request.json.get('id')
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT marked FROM spendings WHERE id=%s", (sid,))
            r = cur.fetchone()
            if not r:
                return jsonify({'success': False}), 404
            new_mark = not r['marked']
            cur.execute("UPDATE spendings SET marked=%s WHERE id=%s", (new_mark, sid))
            conn.commit()
        return jsonify({'success': True, 'marked': new_mark})
    except Exception as e:
        app.logger.error(f"Error in toggle_mark: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/edit_spending/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_spending(id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            if request.method == 'POST':
                date_str = request.form.get('date')
                expense_month_str = request.form.get('expense_month')
                vehicle_id = request.form.get('vehicle_id')
                category = request.form.get('category')
                reason = request.form.get('reason', '')
                amount = request.form.get('amount')
                spended_by = request.form.get('spended_by')
                mode = request.form.get('mode')
                
                if not all([date_str, expense_month_str, vehicle_id, category, amount]):
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'success': False, 'error': 'Missing required fields'})
                    flash('Missing required fields', 'error')
                    return redirect(url_for('spendings'))
                
                try:
                    payment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    expense_month = datetime.strptime(expense_month_str, '%Y-%m').date().replace(day=1)
                    amount_decimal = Decimal(amount)
                except (ValueError, TypeError) as e:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({'success': False, 'error': 'Invalid date or amount format'})
                    flash('Invalid date or amount format', 'error')
                    return redirect(url_for('spendings'))
                
                if not spended_by or not mode:
                    cur.execute("""
                        UPDATE spendings 
                        SET date=%s, expense_month=%s, vehicle_id=%s, category=%s, reason=%s, amount=%s, 
                        spended_by=NULL, mode=NULL 
                        WHERE id=%s
                    """, (payment_date, expense_month, vehicle_id, category, reason, amount_decimal, id))
                else:
                    cur.execute("""
                        UPDATE spendings 
                        SET date=%s, expense_month=%s, vehicle_id=%s, category=%s, reason=%s, amount=%s, 
                        spended_by=%s, mode=%s 
                        WHERE id=%s
                    """, (payment_date, expense_month, vehicle_id, category, reason, amount_decimal, spended_by, mode, id))
                
                conn.commit()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': True})
                
                flash('Spending updated successfully', 'success')
                return redirect(url_for('spendings'))
            
            cur.execute("SELECT * FROM spendings WHERE id=%s", (id,))
            spending = cur.fetchone()
            
            if not spending:
                return jsonify({'success': False, 'error': 'Spending record not found'}), 404
            
            return jsonify({
                'success': True,
                'spending': {
                    'id': spending['id'],
                    'date': spending['date'].strftime('%Y-%m-%d'),
                    'expense_month': spending['expense_month'].strftime('%Y-%m') if spending['expense_month'] else '',
                    'vehicle_id': spending['vehicle_id'],
                    'category': spending['category'],
                    'reason': spending['reason'] or '',
                    'amount': float(spending['amount']),
                    'spended_by': spending['spended_by'] or '',
                    'mode': spending['mode'] or ''
                }
            })
            
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in edit_spending: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        
        flash(f'Error updating spending: {str(e)}', 'error')
        return redirect(url_for('spendings'))
    finally:
        conn.close()
@app.route('/incoming', methods=['GET','POST'])
@login_required
def incoming():
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            if request.method == 'POST' and request.form.get('action')=='add_company':
                name = request.form.get('company_name').strip()
                cur.execute("INSERT INTO companies (name) VALUES (%s)", (name,))
                return redirect(url_for('incoming'))

            if request.method == 'POST' and request.form.get('action')=='add_payment':
                company_id = request.form.get('company_id')
                vehicle_id = request.form.get('vehicle_id') or None
                date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
                amount = request.form.get('amount')
                cur.execute("INSERT INTO payments (company_id,vehicle_id,date,amount) VALUES (%s,%s,%s,%s)", (company_id, vehicle_id, date, amount))
                return redirect(url_for('incoming'))

            cur.execute("SELECT id,name FROM companies ORDER BY name")
            companies = cur.fetchall()
            cur.execute("SELECT id, vehicle_no FROM vehicles ORDER BY vehicle_no")
            vehicles = cur.fetchall()

            cur.execute("SELECT COALESCE(SUM(amount),0) as credited FROM payments")
            credited = cur.fetchone()['credited'] or 0
            cur.execute("SELECT COALESCE(SUM(amount),0) as debited FROM spendings WHERE spended_by IS NOT NULL AND mode IS NOT NULL")
            debited = cur.fetchone()['debited'] or 0
            balance = Decimal(credited) - Decimal(debited)
            
            cur.execute("SELECT COALESCE(SUM(amount),0) AS tsr_spent FROM spendings WHERE spended_by='TSR'")
            tsr_spent = cur.fetchone()['tsr_spent'] or 0

            cur.execute("SELECT COALESCE(SUM(amount),0) AS msr_spent FROM spendings WHERE spended_by='MSR'")
            msr_spent = cur.fetchone()['msr_spent'] or 0

            tsr_balance = Decimal(credited) - Decimal(tsr_spent)
            msr_balance = Decimal(credited) - Decimal(msr_spent)
            
            cur.execute("SELECT p.*, c.name as company_name, v.vehicle_no FROM payments p LEFT JOIN companies c ON p.company_id=c.id LEFT JOIN vehicles v ON p.vehicle_id=v.id ORDER BY p.date DESC")
            payments = cur.fetchall()
    except Exception as e:
        app.logger.error(f"Error in incoming route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('incoming.html', companies=companies, vehicles=vehicles, 
                          credited=float(credited), debited=float(debited), balance=float(balance),
                          tsr_spent=float(tsr_spent or 0), msr_spent=float(msr_spent or 0),
                          tsr_balance=float(tsr_balance or 0), msr_balance=float(msr_balance or 0),
                          payments=payments, today=today)

@app.route('/get_employee_advance/<int:id>')
@login_required
def get_employee_advance(id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM employee_advances WHERE id=%s", (id,))
            advance = cur.fetchone()
            
            if not advance:
                return jsonify({'success': False, 'error': 'Advance record not found'})
            
            return jsonify({
                'success': True,
                'advance': {
                    'id': advance['id'],
                    'employee_name': advance['employee_name'],
                    'date': advance['date'].strftime('%Y-%m-%d'),
                    'amount': float(advance['amount']),
                    'purpose': advance['purpose'] or ''
                }
            })
    except Exception as e:
        app.logger.error(f"Error in get_employee_advance: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/edit_employee_advance/<int:id>', methods=['POST'])
@login_required
def edit_employee_advance(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            employee_name = request.form.get('employee_name')
            date_str = request.form.get('date')
            amount = request.form.get('amount')
            purpose = request.form.get('purpose')
            
            if not all([employee_name, date_str, amount]):
                return jsonify({'success': False, 'error': 'Missing required fields'})
            
            dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            cur.execute("""
                UPDATE employee_advances 
                SET employee_name=%s, date=%s, amount=%s, purpose=%s 
                WHERE id=%s
            """, (employee_name, dt, amount, purpose, id))
            
            conn.commit()
            return jsonify({'success': True, 'message': 'Advance updated successfully'})
            
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in edit_employee_advance: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/delete_employee_advance/<int:id>', methods=['DELETE'])
@login_required
def delete_employee_advance(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employee_advances WHERE id=%s", (id,))
            conn.commit()
            return jsonify({'success': True, 'message': 'Advance deleted successfully'})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in delete_employee_advance: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/get_hired_vehicle_transaction/<int:transaction_id>')
@login_required
def get_hired_vehicle_transaction(transaction_id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM hired_vehicle_transactions WHERE id = %s", (transaction_id,))
            transaction = cur.fetchone()
            
            if not transaction:
                return jsonify({'success': False, 'error': 'Transaction not found'})
            
            return jsonify({
                'success': True,
                'transaction': {
                    'id': transaction['id'],
                    'transaction_type': transaction['transaction_type'],
                    'transaction_date': transaction['transaction_date'].strftime('%Y-%m-%d'),
                    'month_year': transaction['month_year'].strftime('%Y-%m'),
                    'amount': float(transaction['amount']),
                    'description': transaction['description'] or '',
                    'reference_no': transaction['reference_no'] or ''
                }
            })
    except Exception as e:
        app.logger.error(f"Error in get_hired_vehicle_transaction: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/update_hired_vehicle_transaction', methods=['POST'])
@login_required
def update_hired_vehicle_transaction():
    conn = get_db_conn()
    try:
        transaction_id = request.form.get('transaction_id')
        transaction_type = request.form.get('transaction_type')
        transaction_date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d').date()
        month_year = datetime.strptime(request.form.get('month_year'), '%Y-%m').date().replace(day=1)
        amount = request.form.get('amount')
        description = request.form.get('description', '').strip()
        reference_no = request.form.get('reference_no', '').strip()
        
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE hired_vehicle_transactions 
                SET transaction_type = %s, transaction_date = %s, month_year = %s, 
                    amount = %s, description = %s, reference_no = %s
                WHERE id = %s
            """, (transaction_type, transaction_date, month_year, amount, description, reference_no, transaction_id))
            
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Transaction updated successfully'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in update_hired_vehicle_transaction: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/delete_hired_vehicle_transaction/<int:transaction_id>', methods=['DELETE'])
@login_required
def delete_hired_vehicle_transaction(transaction_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM hired_vehicle_transactions WHERE id = %s", (transaction_id,))
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Transaction deleted successfully'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in delete_hired_vehicle_transaction: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/get_company_sale/<int:sale_id>')
@login_required
def get_company_sale(sale_id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM company_sales WHERE id = %s", (sale_id,))
            sale = cur.fetchone()
            
            if not sale:
                return jsonify({'success': False, 'error': 'Sale record not found'})
            
            return jsonify({
                'success': True,
                'sale': {
                    'id': sale['id'],
                    'sale_date': sale['sale_date'].strftime('%Y-%m-%d'),
                    'company_name': sale['company_name'],
                    'invoice_number': sale['invoice_number'] or '',
                    'sale_amount': float(sale['sale_amount']),
                    'month_year': sale['month_year'].strftime('%Y-%m'),
                    'description': sale['description'] or ''
                }
            })
    except Exception as e:
        app.logger.error(f"Error in get_company_sale: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/update_company_sale', methods=['POST'])
@login_required
def update_company_sale():
    conn = get_db_conn()
    try:
        sale_id = request.form.get('sale_id')
        sale_date = datetime.strptime(request.form.get('sale_date'), '%Y-%m-%d').date()
        company_name = request.form.get('company_name').strip()
        invoice_number = request.form.get('invoice_number', '').strip()
        sale_amount = request.form.get('sale_amount')
        month_year = datetime.strptime(request.form.get('month_year'), '%Y-%m').date().replace(day=1)
        description = request.form.get('description', '').strip()
        
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE company_sales 
                SET sale_date = %s, company_name = %s, invoice_number = %s, 
                    sale_amount = %s, month_year = %s, description = %s
                WHERE id = %s
            """, (sale_date, company_name, invoice_number, sale_amount, month_year, description, sale_id))
            
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Sale updated successfully'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in update_company_sale: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/delete_company_sale/<int:sale_id>', methods=['DELETE'])
@login_required
def delete_company_sale(sale_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_sales WHERE id = %s", (sale_id,))
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Sale deleted successfully'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in delete_company_sale: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/get_company_payment/<int:payment_id>')
@login_required
def get_company_payment(payment_id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM company_payments WHERE id = %s", (payment_id,))
            payment = cur.fetchone()
            
            if not payment:
                return jsonify({'success': False, 'error': 'Payment record not found'})
            
            return jsonify({
                'success': True,
                'payment': {
                    'id': payment['id'],
                    'payment_date': payment['payment_date'].strftime('%Y-%m-%d'),
                    'company_name': payment['company_name'],
                    'received_amount': float(payment['received_amount']),
                    'payment_mode': payment['payment_mode'],
                    'reference_number': payment['reference_number'] or '',
                    'month_year': payment['month_year'].strftime('%Y-%m'),
                    'description': payment['description'] or ''
                }
            })
    except Exception as e:
        app.logger.error(f"Error in get_company_payment: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/update_company_payment', methods=['POST'])
@login_required
def update_company_payment():
    conn = get_db_conn()
    try:
        payment_id = request.form.get('payment_id')
        payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
        company_name = request.form.get('company_name').strip()
        received_amount = request.form.get('received_amount')
        payment_mode = request.form.get('payment_mode')
        reference_number = request.form.get('reference_number', '').strip()
        month_year = datetime.strptime(request.form.get('month_year'), '%Y-%m').date().replace(day=1)
        description = request.form.get('description', '').strip()
        
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE company_payments 
                SET payment_date = %s, company_name = %s, received_amount = %s, 
                    payment_mode = %s, reference_number = %s, month_year = %s, description = %s
                WHERE id = %s
            """, (payment_date, company_name, received_amount, payment_mode, reference_number, month_year, description, payment_id))
            
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Payment updated successfully'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in update_company_payment: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/delete_company_payment/<int:payment_id>', methods=['DELETE'])
@login_required
def delete_company_payment(payment_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_payments WHERE id = %s", (payment_id,))
            conn.commit()
            
        return jsonify({'success': True, 'message': 'Payment deleted successfully'})
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in delete_company_payment: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

@app.route('/api/hired_vehicles_audit')
@login_required
def api_hired_vehicles_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        vehicle_id = request.args.get('vehicle_id', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with get_dict_cursor(conn) as cur:
            if vehicle_id == 'all':
                cur.execute("""
                    SELECT 
                        hv.id,
                        hv.vehicle_no,
                        hv.owner_name,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END), 0) as total_sales,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END), 0) as total_payments
                    FROM hired_vehicles hv
                    LEFT JOIN hired_vehicle_transactions t ON hv.id = t.hired_vehicle_id AND t.month_year = %s
                    GROUP BY hv.id, hv.vehicle_no, hv.owner_name
                    ORDER BY hv.vehicle_no
                """, (month_date,))
                
                summary = cur.fetchall()
                
                return jsonify({
                    'summary': summary,
                    'month': month
                })
                
            else:
                cur.execute("""
                    SELECT 
                        hv.id,
                        hv.vehicle_no,
                        hv.owner_name,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END), 0) as total_sales,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END), 0) as total_payments
                    FROM hired_vehicles hv
                    LEFT JOIN hired_vehicle_transactions t ON hv.id = t.hired_vehicle_id AND t.month_year = %s
                    WHERE hv.id = %s
                    GROUP BY hv.id, hv.vehicle_no, hv.owner_name
                """, (month_date, vehicle_id))
                
                summary = cur.fetchall()
                
                cur.execute("""
                    SELECT *
                    FROM hired_vehicle_transactions
                    WHERE hired_vehicle_id = %s AND month_year = %s
                    ORDER BY transaction_date, created_at
                """, (vehicle_id, month_date))
                
                transactions = cur.fetchall()
                
                return jsonify({
                    'summary': summary,
                    'transactions': transactions,
                    'month': month
                })
                
    except Exception as e:
        app.logger.error(f"Error in api_hired_vehicles_audit: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/company_audit')
@login_required
def api_company_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        company = request.args.get('company', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with get_dict_cursor(conn) as cur:
            if company == 'all':
                cur.execute("""
                    SELECT 
                        company_name,
                        COALESCE(SUM(sale_amount), 0) as sales_amount
                    FROM company_sales 
                    WHERE month_year = %s
                    GROUP BY company_name
                """, (month_date,))
                
                sales_data = cur.fetchall()
                
                cur.execute("""
                    SELECT 
                        company_name,
                        COALESCE(SUM(received_amount), 0) as received_amount
                    FROM company_payments 
                    WHERE month_year = %s
                    GROUP BY company_name
                """, (month_date,))
                
                payment_data = cur.fetchall()
                
                # Combine data
                company_dict = {}
                for row in sales_data:
                    company_dict[row['company_name']] = {
                        'company_name': row['company_name'],
                        'sales_amount': float(row['sales_amount']),
                        'received_amount': 0
                    }
                
                for row in payment_data:
                    if row['company_name'] in company_dict:
                        company_dict[row['company_name']]['received_amount'] = float(row['received_amount'])
                    else:
                        company_dict[row['company_name']] = {
                            'company_name': row['company_name'],
                            'sales_amount': 0,
                            'received_amount': float(row['received_amount'])
                        }
                
                companies = list(company_dict.values())
                for comp in companies:
                    comp['pending_amount'] = comp['sales_amount'] - comp['received_amount']
                
                return jsonify({
                    'companies': companies,
                    'month': month
                })
                
            else:
                cur.execute("""
                    SELECT 
                        company_name,
                        COALESCE(SUM(sale_amount), 0) as sales_amount
                    FROM company_sales 
                    WHERE company_name = %s AND month_year = %s
                    GROUP BY company_name
                """, (company, month_date))
                
                sales_result = cur.fetchone()
                sales_amount = float(sales_result['sales_amount'] or 0) if sales_result else 0
                
                cur.execute("""
                    SELECT 
                        company_name,
                        COALESCE(SUM(received_amount), 0) as received_amount
                    FROM company_payments 
                    WHERE company_name = %s AND month_year = %s
                    GROUP BY company_name
                """, (company, month_date))
                
                payments_result = cur.fetchone()
                received_amount = float(payments_result['received_amount'] or 0) if payments_result else 0
                
                cur.execute("""
                    SELECT 
                        'sale' as type,
                        sale_date as date,
                        invoice_number as reference,
                        sale_amount as amount,
                        description
                    FROM company_sales 
                    WHERE company_name = %s AND month_year = %s
                    
                    UNION ALL
                    
                    SELECT 
                        'payment' as type,
                        payment_date as date,
                        reference_number as reference,
                        received_amount as amount,
                        description
                    FROM company_payments 
                    WHERE company_name = %s AND month_year = %s
                    
                    ORDER BY date
                """, (company, month_date, company, month_date))
                
                transactions = cur.fetchall()
                
                return jsonify({
                    'companies': [{
                        'company_name': company,
                        'sales_amount': sales_amount,
                        'received_amount': received_amount,
                        'pending_amount': sales_amount - received_amount
                    }],
                    'transactions': transactions,
                    'month': month
                })
                
    except Exception as e:
        app.logger.error(f"Error in api_company_audit: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/export/hired_vehicles_audit')
@login_required
def export_hired_vehicles_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        vehicle_id = request.args.get('vehicle_id', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with get_dict_cursor(conn) as cur:
            if vehicle_id == 'all':
                cur.execute("""
                    SELECT 
                        hv.vehicle_no,
                        hv.owner_name,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END), 0) as total_sales,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END), 0) as total_payments,
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END), 0) - 
                        COALESCE(SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END), 0) as net_balance
                    FROM hired_vehicles hv
                    LEFT JOIN hired_vehicle_transactions t ON hv.id = t.hired_vehicle_id AND t.month_year = %s
                    GROUP BY hv.id, hv.vehicle_no, hv.owner_name
                    ORDER BY hv.vehicle_no
                """, (month_date,))
                
                data = cur.fetchall()
                filename = f'hired_vehicles_audit_{month}.csv'
                
            else:
                cur.execute("""
                    SELECT 
                        t.transaction_date,
                        t.transaction_type,
                        t.description,
                        t.reference_no,
                        t.amount,
                        hv.vehicle_no,
                        hv.owner_name
                    FROM hired_vehicle_transactions t
                    JOIN hired_vehicles hv ON t.hired_vehicle_id = hv.id
                    WHERE t.hired_vehicle_id = %s AND t.month_year = %s
                    ORDER BY t.transaction_date, t.created_at
                """, (vehicle_id, month_date))
                
                data = cur.fetchall()
                vehicle_info = data[0] if data else {}
                filename = f'hired_vehicle_audit_{vehicle_info.get("vehicle_no", "unknown")}_{month}.csv'
            
            output = StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            
            response = app.response_class(
                response=output.getvalue(),
                status=200,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename={filename}'}
            )
            return response
            
    except Exception as e:
        app.logger.error(f"Error exporting hired vehicles audit: {e}")
        return "Error exporting data", 500
    finally:
        conn.close()

@app.route('/export/company_audit')
@login_required
def export_company_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        company = request.args.get('company', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with get_dict_cursor(conn) as cur:
            if company == 'all':
                cur.execute("""
                    SELECT 
                        cs.company_name,
                        cs.sale_date,
                        cs.invoice_number,
                        cs.sale_amount,
                        cs.description,
                        cp.payment_date,
                        cp.received_amount,
                        cp.payment_mode,
                        cp.reference_number
                    FROM company_sales cs
                    LEFT JOIN company_payments cp ON cs.company_name = cp.company_name AND cs.month_year = cp.month_year
                    WHERE cs.month_year = %s
                    ORDER BY cs.company_name, cs.sale_date
                """, (month_date,))
                
                data = cur.fetchall()
                filename = f'company_audit_{month}.csv'
                
            else:
                cur.execute("""
                    SELECT 
                        'sale' as transaction_type,
                        sale_date as date,
                        invoice_number as reference,
                        sale_amount as amount,
                        description,
                        NULL as payment_mode
                    FROM company_sales 
                    WHERE company_name = %s AND month_year = %s
                    
                    UNION ALL
                    
                    SELECT 
                        'payment' as transaction_type,
                        payment_date as date,
                        reference_number as reference,
                        received_amount as amount,
                        description,
                        payment_mode
                    FROM company_payments 
                    WHERE company_name = %s AND month_year = %s
                    
                    ORDER BY date
                """, (company, month_date, company, month_date))
                
                data = cur.fetchall()
                filename = f'company_audit_{company}_{month}.csv'
            
            output = StringIO()
            if data:
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            
            response = app.response_class(
                response=output.getvalue(),
                status=200,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename={filename}'}
            )
            return response
            
    except Exception as e:
        app.logger.error(f"Error exporting company audit: {e}")
        return "Error exporting data", 500
    finally:
        conn.close()




# Initialize database when app starts
initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
