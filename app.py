# app_postgresql.py - Converted from MySQL (pymysql) to PostgreSQL (psycopg2)

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
# Assuming config.py contains necessary SECRET_KEY and PostgreSQL connection details
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
    """Establishes a PostgreSQL database connection with SSL required."""
    try:
        # FIX: Added sslmode='require' to force an SSL connection, 
        # which is typically required by cloud providers like DigitalOcean.
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASS,
            dbname=config.DB_NAME,
            sslmode='require'  # <--- THIS IS THE CRITICAL ADDITION
        )
        # Set autocommit property for conn to True
        conn.autocommit = True
        logger.info("Database connection established successfully.")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        # Re-raise the exception so Flask catches it and logs the source of the 500 error
        raise

# Helper function to get a cursor that returns dictionaries
def get_dict_cursor(conn):
    # CHANGED: Using DictCursor for dictionary results
    return conn.cursor(cursor_factory=extras.DictCursor)


@app.route('/employee_advances', methods=['GET', 'POST'])
@login_required
def employee_advances():
    # 1. Ensure table exists (create_employee_advances_table())
    # 2. Get DB connection
    # 3. Handle POST request (insert new advance)
    # 4. Handle GET request (fetch and display all advances)
    # 5. Render the HTML template (e.g., return render_template('employee_advances.html', ...))
    
    # Placeholder to stop the 500 error, replace with actual logic:
    return "Employee Advances Page - Logic not implemented yet."
# Create tables functions
# ----------------------------------------------------
def create_auth_tables():
    conn = get_db_conn()
    try:
        # Use DictCursor for fetching admin user
        with get_dict_cursor(conn) as cur:
            # SQL CHANGE: AUTO_INCREMENT -> SERIAL
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

            logger.info("Auth tables checked/created successfully")

    except Exception as e:
        logger.error(f"Error creating auth tables: {e}")
    finally:
        conn.close()

def create_vehicles_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # SQL CHANGE: AUTO_INCREMENT -> SERIAL
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vehicles (
                    id SERIAL PRIMARY KEY,
                    vehicle_no VARCHAR(50) UNIQUE NOT NULL,
                    owner_name VARCHAR(100),
                    contact_number VARCHAR(20),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            logger.info("Vehicles table checked/created successfully")
    except Exception as e:
        logger.error(f"Error creating vehicles table: {e}")
    finally:
        conn.close()

def create_spendings_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # SQL CHANGE: AUTO_INCREMENT -> SERIAL, DECIMAL -> NUMERIC
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
            logger.info("Spendings table checked/created successfully")
    except Exception as e:
        logger.error(f"Error creating spendings table: {e}")
    finally:
        conn.close()

def create_payments_table():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # SQL CHANGE: AUTO_INCREMENT -> SERIAL, DECIMAL -> NUMERIC
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
            logger.info("Payments table checked/created successfully")
    except Exception as e:
        logger.error(f"Error creating payments table: {e}")
    finally:
        conn.close()

def create_company_audit_tables():
    create_auth_tables()
    create_vehicles_table()
    create_spendings_table()
    create_payments_table()
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
            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT v.id, v.vehicle_no, COALESCE(SUM(s.amount),0) AS total_spent FROM vehicles v LEFT JOIN spendings s ON v.id=s.vehicle_id GROUP BY v.id")
            vehicles = cur.fetchall()

            cur.execute("SELECT COUNT(*) AS c FROM vehicles")
            total_vehicles = cur.fetchone()['c']

            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total_credited FROM payments")
            total_credited = cur.fetchone()['total_credited'] or 0

            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total_debited FROM spendings WHERE spended_by IS NOT NULL OR mode IS NOT NULL")
            total_debited = cur.fetchone()['total_debited'] or 0

            balance = Decimal(total_credited) - Decimal(total_debited)

            current_month = datetime.now().strftime('%Y-%m-01')
            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT COALESCE(SUM(amount),0) as current_month_total FROM spendings WHERE expense_month = %s", (current_month,))
            current_month_total = cur.fetchone()['current_month_total'] or 0

            prev_month = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-01')
            # SQL CHANGE: IFNULL -> COALESCE
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

            # SQL CHANGE: DATE_FORMAT -> TO_CHAR; DATE_SUB -> INTERVAL
            cur.execute("""
                SELECT
                    TO_CHAR(expense_month, 'YYYY-MM') as month,
                    SUM(amount) as total_expense
                FROM spendings
                WHERE expense_month >= (CURRENT_DATE - INTERVAL '6 MONTH')
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
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


# Vehicles page & add vehicle
@app.route('/vehicles', methods=['GET','POST'])
@login_required
def vehicles_page():
    create_vehicles_table() # Ensure table exists
    conn = get_db_conn()
    vehicles = []
    try:
        # POST logic
        if request.method == 'POST':
            vehicle_no = request.form.get('vehicle_no').strip()
            owner_name = request.form.get('owner_name').strip()
            contact_number = request.form.get('contact_number').strip()

            if not vehicle_no:
                flash('Vehicle number cannot be empty.', 'error')
            else:
                with get_dict_cursor(conn) as cur:
                    # Check for duplicates first
                    cur.execute("SELECT id FROM vehicles WHERE vehicle_no = %s", (vehicle_no,))
                    if cur.fetchone():
                        flash(f'Vehicle {vehicle_no} already exists.', 'error')
                    else:
                        cur.execute("INSERT INTO vehicles (vehicle_no, owner_name, contact_number) VALUES (%s, %s, %s)",
                                   (vehicle_no, owner_name, contact_number))
                        flash('Vehicle added successfully!', 'success')
                        return redirect(url_for('vehicles_page'))

        # GET logic
        with get_dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM vehicles ORDER BY vehicle_no")
            vehicles = cur.fetchall()
    except Exception as e:
        app.logger.error(f"Error in vehicles_page route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    return render_template('vehicles.html', vehicles=vehicles)

@app.route('/company_audit')
@login_required
def company_audit():

    
    
    return redirect(url_for('index'))
    

# Delete Vehicle
@app.route('/delete_vehicle/<int:id>', methods=['POST'])
@login_required
def delete_vehicle(id):
    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            # PostgreSQL uses count(*) directly, column name is typically 'count'
            cur.execute("SELECT COUNT(*) FROM spendings WHERE vehicle_id = %s", (id,))
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
    create_spendings_table() # Ensure table exists
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
                # Input handling
                vehicle_id = request.form.get('vehicle_id')
                date_str = request.form.get('date')
                category = request.form.get('category').strip()
                reason = request.form.get('reason').strip()
                amount = request.form.get('amount')
                spended_by = request.form.get('spended_by')
                mode = request.form.get('mode')

                if not all([vehicle_id, date_str, category, amount]):
                    flash('Missing required fields.', 'error')
                    return redirect(url_for('spendings'))

                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                expense_month = date_obj.replace(day=1)
                amount_decimal = Decimal(amount)

                spended_by = spended_by if spended_by else None
                mode = mode if mode else None

                # Insert spending
                cur.execute("""
                    INSERT INTO spendings (vehicle_id, date, expense_month, category, reason, amount, spended_by, mode)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (vehicle_id, date_obj, expense_month, category, reason, amount_decimal, spended_by, mode))
                flash('Spending recorded successfully!', 'success')
                return redirect(url_for('spendings'))

            # GET logic: Fetch all spendings

            # Fetch unpaid payments
            cur.execute("""
                SELECT s.*, v.vehicle_no FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.spended_by IS NULL OR s.mode IS NULL
                ORDER BY s.date DESC
            """)
            unpaid_rows = cur.fetchall()

            # Fetch paid payments for the last 30 days
            # SQL CHANGE: DATE_SUB -> INTERVAL
            cur.execute("""
                SELECT s.*, v.vehicle_no FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                AND s.date >= (CURRENT_DATE - INTERVAL '30 DAY')
                ORDER BY s.date DESC
            """)
            paid_rows = cur.fetchall()

            # Fetch settled payments (historical - older than 30 days)
            # SQL CHANGE: DATE_SUB -> INTERVAL
            cur.execute("""
                SELECT s.*, v.vehicle_no
                FROM spendings s
                JOIN vehicles v ON s.vehicle_id = v.id
                WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                AND s.date < (CURRENT_DATE - INTERVAL '30 DAY')
                ORDER BY s.date DESC
            """)
            settled_rows = cur.fetchall()

            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT COALESCE(SUM(amount),0) as total_spent FROM spendings WHERE spended_by IS NOT NULL AND mode IS NOT NULL")
            total_spent = cur.fetchone()['total_spent'] or 0
            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT COALESCE(SUM(amount),0) as total_unpaid FROM spendings WHERE spended_by IS NULL OR s.mode IS NULL")
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

    return render_template('spendings.html',
                           vehicles=vehicles,
                           paid_rows=paid_rows,
                           unpaid_rows=unpaid_rows,
                           settled_rows=settled_rows,
                           monthly_totals=monthly_totals,
                           total_spent=float(total_spent),
                           total_unpaid=float(total_unpaid))

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
    spended_by = request.form.get('spended_by')
    mode = request.form.get('mode')
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if not spended_by or not mode:
                return jsonify({'success': False, 'message': 'Missing Spender or Mode'}), 400

            # SQL CHANGE: CONCAT(IFNULL(reason, ''), %s) -> COALESCE(reason, '') || %s
            update_reason = f" - Marked Paid by {session['username']} on {datetime.now().strftime('%Y-%m-%d')}"
            cur.execute("""
                UPDATE spendings
                SET spended_by=%s, mode=%s,
                reason=COALESCE(reason, '') || %s
                WHERE id=%s
            """, (spended_by, mode, update_reason, id))
            return jsonify({'success': True, 'message': 'Payment marked as paid successfully!'})
    except Exception as e:
        app.logger.error(f"Error marking paid: {str(e)}")
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500
    finally:
        conn.close()

# Process settlement for multiple unpaid payments
@app.route('/process_settlement', methods=['POST'])
@login_required
def process_settlement():
    data = request.get_json()
    spending_ids = data.get('spending_ids')
    spended_by = data.get('spended_by')
    mode = data.get('mode')
    settlement_date_str = data.get('settlement_date')

    if not spending_ids or not spended_by or not mode or not settlement_date_str:
        return jsonify({'success': False, 'message': 'Missing required settlement details.'}), 400

    try:
        settlement_date = datetime.strptime(settlement_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format.'}), 400

    conn = get_db_conn()
    try:
        with get_dict_cursor(conn) as cur:
            # 1. Fetch total amount for audit
            placeholders = ', '.join(['%s'] * len(spending_ids))
            cur.execute(f"SELECT SUM(amount) AS total_amount FROM spendings WHERE id IN ({placeholders}) AND (spended_by IS NULL OR mode IS NULL)", spending_ids)
            total_amount = cur.fetchone()['total_amount']

            if total_amount is None:
                return jsonify({'success': False, 'message': 'No unpaid spendings found with the provided IDs.'}), 400

            # 2. Update spendings
            update_reason = f" - Settled on {settlement_date.strftime('%Y-%m-%d')} by {session['username']}"
            # SQL CHANGE: CONCAT(IFNULL(reason, ''), %s) -> COALESCE(reason, '') || %s
            update_query = f"""
                UPDATE spendings
                SET spended_by=%s, mode=%s,
                reason=COALESCE(reason, '') || %s
                WHERE id IN ({placeholders})
            """
            update_params = [spended_by, mode, update_reason] + spending_ids
            cur.execute(update_query, update_params)

            return jsonify({'success': True, 'message': f'Settlement of {float(total_amount):.2f} processed successfully!', 'total_amount': float(total_amount)})

    except Exception as e:
        app.logger.error(f"Error processing settlement: {str(e)}")
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500
    finally:
        conn.close()


# Payments list & add payment (Credit)
@app.route('/payments', methods=['GET', 'POST'])
@login_required
def payments():
    create_payments_table() # Ensure table exists
    conn = get_db_conn()
    payment_rows = []
    total_credited = 0
    try:
        with get_dict_cursor(conn) as cur:
            if request.method == 'POST':
                date_str = request.form.get('date')
                amount = request.form.get('amount')
                received_from = request.form.get('received_from').strip()
                reason = request.form.get('reason').strip()

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

            # SQL CHANGE: IFNULL -> COALESCE
            cur.execute("SELECT COALESCE(SUM(amount),0) AS total_credited FROM payments")
            total_credited = cur.fetchone()['total_credited'] or 0

    except Exception as e:
        app.logger.error(f"Error in payments route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()

    return render_template('payments.html',
                           payment_rows=payment_rows,
                           total_credited=float(total_credited))

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

# Export data to CSV
@app.route('/export/<data_type>')
@login_required
def export_data(data_type):
    conn = get_db_conn()
    data = []
    headers = []
    query = ""

    try:
        with get_dict_cursor(conn) as cur:
            if data_type == 'paid_spendings':
                headers = ['ID', 'Vehicle No', 'Date', 'Category', 'Reason', 'Amount', 'Spended By', 'Mode']
                query = """
                    SELECT s.id, v.vehicle_no, s.date, s.category, s.reason, s.amount, s.spended_by, s.mode
                    FROM spendings s
                    JOIN vehicles v ON s.vehicle_id = v.id
                    WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                    ORDER BY s.date DESC
                """
            # ... (Other data_type blocks use standard SQL) ...
            elif data_type == 'monthly_expenses':
                headers = ['Month', 'Vehicle No', 'Total Expense']
                # SQL CHANGE: DATE_FORMAT -> TO_CHAR
                query = """
                    SELECT
                        TO_CHAR(expense_month, 'YYYY-MM') as month,
                        v.vehicle_no,
                        SUM(s.amount) as total_expense
                    FROM spendings s
                    JOIN vehicles v ON s.vehicle_id = v.id
                    WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                    GROUP BY expense_month, v.vehicle_no
                    ORDER BY expense_month DESC, total_expense DESC
                """
            else:
                flash('Invalid export type.', 'error')
                return redirect(url_for('index'))

            cur.execute(query)
            data = cur.fetchall()

            # Process data for CSV writing
            data_list_of_lists = []
            for row in data:
                row_values = []
                # Map values based on headers
                for header in headers:
                    key = next((k for k in row.keys() if k.lower().replace('_', ' ') == header.lower().replace('_', ' ')), header.lower().replace(' ', '_'))
                    value = row.get(key)
                    
                    # Convert date/decimal objects to strings/floats for CSV serialization
                    if isinstance(value, datetime):
                        value = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif hasattr(value, 'strftime'): # Check for date objects
                        value = value.strftime('%Y-%m-%d')
                    elif isinstance(value, Decimal):
                        value = float(value)

                    row_values.append(value)
                data_list_of_lists.append(row_values)

            # Create a CSV in memory
            si = StringIO()
            cw = csv.writer(si)
            cw.writerow(headers)
            cw.writerows(data_list_of_lists)

            # Create a response
            output = make_response(si.getvalue())
            output.headers["Content-Disposition"] = f"attachment; filename={data_type}_{datetime.now().strftime('%Y%m%d')}.csv"
            output.headers["Content-type"] = "text/csv"
            return output

    except Exception as e:
        app.logger.error(f"Error exporting data: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))
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
                # SQL CHANGE: DATE_FORMAT -> TO_CHAR
                q += " AND TO_CHAR(expense_month,'YYYY-MM') = %s"
                params.append(month)
            q += " ORDER BY date DESC"
            cur.execute(q, params)
            rows = cur.fetchall()

            # Format date objects and decimals for JSON serialization
            formatted_rows = []
            for row in rows:
                formatted_row = dict(row)
                if 'date' in formatted_row and formatted_row['date']:
                    formatted_row['date'] = formatted_row['date'].strftime('%Y-%m-%d')
                if 'expense_month' in formatted_row and formatted_row['expense_month']:
                    formatted_row['expense_month'] = formatted_row['expense_month'].strftime('%Y-%m-%d')
                if 'amount' in formatted_row:
                    formatted_row['amount'] = float(formatted_row['amount'])

                formatted_rows.append(formatted_row)

            return jsonify(formatted_rows)
    except Exception as e:
        app.logger.error(f"Error fetching vehicle spendings: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

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
                # Convert date object to string and decimal to float
                if result['expense_month']:
                    result['expense_month'] = result['expense_month'].strftime('%Y-%m-%d')
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
                    flash('Current password is incorrect', 'error')

        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            flash('An error occurred while changing password', 'error')
        finally:
            conn.close()

    return render_template('change_password.html')

@app.route('/clear_cookies')
def clear_cookies():
    response = make_response("Cookies cleared - <a href='/'>Go Home</a>")
    # Clear all possible session cookies
    response.set_cookie('session', '', expires=0)
    response.set_cookie(app.session_cookie_name, '', expires=0)
    return response

# Call this function when the app starts
create_company_audit_tables()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
