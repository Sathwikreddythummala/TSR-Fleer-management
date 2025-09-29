# app.py - Corrected version
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_bcrypt import Bcrypt
import pymysql
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
    try:
        conn = pymysql.connect(host=config.DB_HOST,
                               port=config.DB_PORT,
                               user=config.DB_USER,
                               password=config.DB_PASS,
                               db=config.DB_NAME,
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        logger.info("Database connection established successfully.")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

# Create users table and default admin user
def create_auth_tables():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password_hash VARCHAR(120) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Check if admin user exists, if not create one
            cur.execute("SELECT id FROM users WHERE username = 'admin'")
            admin_user = cur.fetchone()
            
            if not admin_user:
                # Default password: admin123 (you should change this after first login)
                password_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
                cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", 
                           ('admin', password_hash))
                logger.info("Default admin user created with password: admin123")
            
            conn.commit()
            logger.info("Auth tables checked/created successfully")
            
    except Exception as e:
        logger.error(f"Error creating auth tables: {e}")
    finally:
        conn.close()

# Call this function when app starts
create_auth_tables()



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
        with conn.cursor() as cur:
            # Get vehicles with their total spending
            cur.execute("SELECT v.id, v.vehicle_no, IFNULL(SUM(s.amount),0) AS total_spent FROM vehicles v LEFT JOIN spendings s ON v.id=s.vehicle_id GROUP BY v.id")
            vehicles = cur.fetchall()

            # Get overall totals
            cur.execute("SELECT COUNT(*) AS c FROM vehicles")
            total_vehicles = cur.fetchone()['c']

            cur.execute("SELECT IFNULL(SUM(amount),0) AS total_credited FROM payments")
            total_credited = cur.fetchone()['total_credited'] or 0

            cur.execute("SELECT IFNULL(SUM(amount),0) AS total_debited FROM spendings WHERE spended_by IS NOT NULL OR mode IS NOT NULL")
            total_debited = cur.fetchone()['total_debited'] or 0

            balance = Decimal(total_credited) - Decimal(total_debited)

            # Get current month's total
            current_month = datetime.now().strftime('%Y-%m-01')
            cur.execute("SELECT IFNULL(SUM(amount),0) as current_month_total FROM spendings WHERE expense_month = %s", (current_month,))
            current_month_total = cur.fetchone()['current_month_total'] or 0

            # Get previous month's total
            prev_month = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-01')
            cur.execute("SELECT IFNULL(SUM(amount),0) as prev_month_total FROM spendings WHERE expense_month = %s", (prev_month,))
            prev_month_total = cur.fetchone()['prev_month_total'] or 0

            # Get monthly expenses by vehicle for current month
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
                    DATE_FORMAT(expense_month, '%%Y-%%m') as month,
                    SUM(amount) as total_expense
                FROM spendings
                WHERE expense_month >= DATE_SUB(%s, INTERVAL 6 MONTH)
                GROUP BY expense_month
                ORDER BY expense_month DESC
            """, (current_month,))
            monthly_trend = cur.fetchall()

            # Update totals dictionary
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

# Vehicles page & add vehicle
@app.route('/vehicles', methods=['GET','POST'])
def vehicles_page():
    conn = get_db_conn()
    try:
        if request.method == 'POST':
            vehicle_no = request.form.get('vehicle_no').strip()
            with conn.cursor() as cur:
                cur.execute("INSERT INTO vehicles (vehicle_no) VALUES (%s)", (vehicle_no,))
            return redirect(url_for('vehicles_page'))

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM vehicles ORDER BY vehicle_no")
            vehicles = cur.fetchall()
    except Exception as e:
        app.logger.error(f"Error in vehicles_page route: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    return render_template('vehicles.html', vehicles=vehicles)

# Spendings list & add spending
@app.route('/spendings', methods=['GET','POST'])
def spendings():
    conn = get_db_conn()
    paid_rows = []
    unpaid_rows = []
    settled_rows = []
    monthly_totals = []
    total_spent = 0
    total_unpaid = 0
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, vehicle_no FROM vehicles ORDER BY vehicle_no")
            vehicles = cur.fetchall()

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
                    flash('Missing required fields', 'error')
                    return redirect(url_for('spendings'))
                
                try:
                    payment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    expense_month = datetime.strptime(expense_month_str, '%Y-%m').date().replace(day=1)
                    amount_decimal = Decimal(amount)
                except (ValueError, TypeError) as e:
                    flash('Invalid date or amount format', 'error')
                    return redirect(url_for('spendings'))
                
                # Check for duplicates
                cur.execute("""
    SELECT COUNT(*) as count FROM spendings 
    WHERE vehicle_id=%s AND date=%s AND category=%s 
    AND amount=%s AND reason=%s
""", (vehicle_id, payment_date, category, amount_decimal, reason))
                
                if cur.fetchone()['count'] > 0:
                    flash('This spending entry already exists', 'warning')
                    return redirect(url_for('spendings', duplicate=True))
                
                # Insert into database
                try:
                    if spended_by and mode:
                        cur.execute("""
                            INSERT INTO spendings (vehicle_id, date, expense_month, category, reason, amount, spended_by, mode)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (vehicle_id, payment_date, expense_month, category, reason, amount_decimal, spended_by, mode))
                    else:
                        cur.execute("""
                            INSERT INTO spendings (vehicle_id, date, expense_month, category, reason, amount)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (vehicle_id, payment_date, expense_month, category, reason, amount_decimal))
                    
                    conn.commit()
                    flash('Spending added successfully', 'success')
                    return redirect(url_for('spendings'))
                    
                except Exception as e:
                    conn.rollback()
                    app.logger.error(f"Database error: {e}")
                    flash(f'Error saving to database: {str(e)}', 'error')

            # Fetch paid spendings
            paid_query = """
                SELECT s.*, v.vehicle_no 
                FROM spendings s 
                JOIN vehicles v ON s.vehicle_id = v.id 
                WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                ORDER BY s.expense_month DESC, s.date DESC
            """
            cur.execute(paid_query)
            paid_rows = cur.fetchall()

            # Fetch unpaid spendings
            unpaid_query = """
                SELECT s.*, v.vehicle_no 
                FROM spendings s 
                JOIN vehicles v ON s.vehicle_id = v.id 
                WHERE s.spended_by IS NULL OR s.mode IS NULL
                ORDER BY s.expense_month DESC, s.date DESC
            """
            cur.execute(unpaid_query)
            unpaid_rows = cur.fetchall()

            # Fetch settled payments (historical)
            settled_query = """
                SELECT s.*, v.vehicle_no 
                FROM spendings s 
                JOIN vehicles v ON s.vehicle_id = v.id 
                WHERE s.spended_by IS NOT NULL AND s.mode IS NOT NULL
                AND s.date < DATE_SUB(NOW(), INTERVAL 30 DAY)
                ORDER BY s.date DESC
            """
            cur.execute(settled_query)
            settled_rows = cur.fetchall()

            # totals
            cur.execute("SELECT IFNULL(SUM(amount),0) as total_spent FROM spendings WHERE spended_by IS NOT NULL AND mode IS NOT NULL")
            total_spent = cur.fetchone()['total_spent'] or 0

            cur.execute("SELECT IFNULL(SUM(amount),0) as total_unpaid FROM spendings WHERE spended_by IS NULL OR mode IS NULL")
            total_unpaid = cur.fetchone()['total_unpaid'] or 0

            # Monthly totals by expense month
            cur.execute("""
                SELECT expense_month, IFNULL(SUM(amount),0) as monthly_total 
                FROM spendings 
                WHERE spended_by IS NOT NULL AND mode IS NOT NULL
                GROUP BY expense_month 
                ORDER BY expense_month DESC
            """)
            monthly_totals = cur.fetchall()
            
    except Exception as e:
        app.logger.error(f"Error in spendings route: {e}")
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
                         total_spent=total_spent,
                         total_unpaid=total_unpaid,
                         today=today,
                         current_month=current_month)

# AJAX toggle mark/unmark
@app.route('/toggle_mark', methods=['POST'])
def toggle_mark():
    sid = request.json.get('id')
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT marked FROM spendings WHERE id=%s", (sid,))
            r = cur.fetchone()
            if not r:
                return jsonify({'success': False}), 404
            new_mark = 0 if r['marked'] else 1
            cur.execute("UPDATE spendings SET marked=%s WHERE id=%s", (new_mark, sid))
            conn.commit()
        return jsonify({'success': True, 'marked': new_mark})
    except Exception as e:
        app.logger.error(f"Error in toggle_mark: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# Mark unpaid payment as paid
@app.route('/mark_paid/<int:id>', methods=['POST'])
def mark_paid(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM spendings WHERE id=%s", (id,))
            spending = cur.fetchone()
            
            if not spending:
                return jsonify({'success': False, 'message': 'Spending record not found'})
            
            data = request.get_json()
            spended_by = data.get('spended_by', 'MSR')
            mode = data.get('mode', 'UPI')
            
            cur.execute("""
                UPDATE spendings 
                SET spended_by=%s, mode=%s, 
                reason=CONCAT(IFNULL(reason, ''), ' - Marked Paid on %s') 
                WHERE id=%s
            """, (spended_by, mode, datetime.now().strftime('%Y-%m-%d'), id))
            
            conn.commit()
            return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in mark_paid: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# Process settlement for multiple unpaid payments
@app.route('/process_settlement', methods=['POST'])
def process_settlement():
    conn = get_db_conn()
    try:
        data = request.get_json()
        spending_ids = data.get('spending_ids', [])
        spended_by = data.get('spended_by', 'MSR')
        mode = data.get('mode', 'UPI')
        settlement_date = datetime.now().date()
        
        if not spending_ids:
            return jsonify({'success': False, 'message': 'No spendings selected'})
        
        spending_ids = [int(id) for id in spending_ids]
        
        with conn.cursor() as cur:
            placeholders = ','.join(['%s'] * len(spending_ids))
            cur.execute(f"SELECT SUM(amount) as total FROM spendings WHERE id IN ({placeholders})", spending_ids)
            total_amount = cur.fetchone()['total'] or 0
            
            update_query = f"""
                UPDATE spendings 
                SET spended_by=%s, mode=%s, 
                reason=CONCAT(IFNULL(reason, ''), %s) 
                WHERE id IN ({placeholders})
            """
            update_params = [spended_by, mode, f" - Settled on {settlement_date.strftime('%Y-%m-%d')}"] + spending_ids
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

# Edit spending
@app.route('/edit_spending/<int:id>', methods=['GET', 'POST'])
def edit_spending(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if request.method == 'POST':
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
                
                # Handle NULL values for unpaid
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
            
            # For GET requests
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

# Export data to CSV
@app.route('/export/<data_type>')
def export_data(data_type):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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
                    SELECT p.date, c.name as company_name, v.vehicle_no, p.amount 
                    FROM payments p 
                    LEFT JOIN companies c ON p.company_id=c.id 
                    LEFT JOIN vehicles v ON p.vehicle_id=v.id 
                    ORDER BY p.date DESC
                """)
                data = cur.fetchall()
                filename = 'payments.csv'
                
            elif data_type == 'vehicles':
                cur.execute("SELECT vehicle_no, created_at FROM vehicles ORDER by vehicle_no")
                data = cur.fetchall()
                filename = 'vehicles.csv'
                
            elif data_type == 'monthly_expenses':
                cur.execute("""
                    SELECT 
                        DATE_FORMAT(expense_month, '%Y-%m') as month,
                        v.vehicle_no,
                        SUM(s.amount) as total_expense
                    FROM spendings s
                    JOIN vehicles v ON s.vehicle_id = v.id
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

# Incoming payments / companies
@app.route('/incoming', methods=['GET','POST'])
def incoming():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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

            cur.execute("SELECT IFNULL(SUM(amount),0) as credited FROM payments")
            credited = cur.fetchone()['credited'] or 0
            cur.execute("SELECT IFNULL(SUM(amount),0) as debited FROM spendings WHERE spended_by IS NOT NULL AND mode IS NOT NULL")
            debited = cur.fetchone()['debited'] or 0
            balance = Decimal(credited) - Decimal(debited)
            
            cur.execute("SELECT IFNULL(SUM(amount),0) AS tsr_spent FROM spendings WHERE spended_by='TSR'")
            tsr_spent = cur.fetchone()['tsr_spent'] or 0

            cur.execute("SELECT IFNULL(SUM(amount),0) AS msr_spent FROM spendings WHERE spended_by='MSR'")
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
    return render_template('incoming.html', companies=companies, vehicles=vehicles, 
                          credited=float(credited), debited=float(debited), balance=float(balance),
                          tsr_spent=float(tsr_spent or 0), msr_spent=float(msr_spent or 0),
                          tsr_balance=float(tsr_balance or 0), msr_balance=float(msr_balance or 0),
                          payments=payments)

# Employee advances and expenses - COMBINED ROUTE
# Replace the employee_advances route with this corrected version:
# Replace the employee_advances route with this version:
# app.py

@app.route("/employee_advances", methods=['GET', 'POST'])
@login_required
def employee_advances():
    conn = get_db_conn()
    
    # --- 1. HANDLE POST REQUEST (ADDING ADVANCE) ---
    if request.method == 'POST':
        try:
            employee_name = request.form['employee_name']
            date = request.form['date']
            amount = request.form['amount']
            purpose = request.form.get('purpose', '')

            if not employee_name or not date or not amount:
                flash('Please fill in all required fields.', 'error')
                # Important: Do not return redirect yet, fall through to re-render the GET part
            else:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO employee_advances 
                        (employee_name, date, amount, purpose) 
                        VALUES (%s, %s, %s, %s)
                    """, (employee_name, date, amount, purpose))
                    conn.commit()
                
                flash(f'Advance added successfully for {employee_name}.', 'success')
                # Redirect after successful POST to prevent duplicate submission
                return redirect(url_for('employee_advances'))
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding employee advance: {str(e)}")
            flash('An error occurred while adding the advance.', 'error')
            # If POST failed, fall through to re-render the page
    
    # --- 2. HANDLE GET REQUEST (DISPLAYING DATA) ---
    # This section runs for GET requests AND after a failed POST (to re-render the form)
    
    employee_balances = []
    advances = []
    employee_spendings = []
    
    try:
        with conn.cursor() as cur:
            # Fetch balances from the corrected VIEW
            cur.execute("SELECT * FROM employee_balance ORDER BY employee_name")
            employee_balances = cur.fetchall()
            
            # Convert Decimal types to float for safe display (as fixed previously)
            for employee in employee_balances:
                for key in ['total_advances', 'total_expenses', 'balance']:
                    if isinstance(employee.get(key), Decimal):
                        employee[key] = float(employee[key])
                        
            # Fetch all individual advances and spendings
            cur.execute("SELECT * FROM employee_advances ORDER BY date DESC")
            advances = cur.fetchall()
            
            # Optional: Convert amount for display
            for advance in advances:
                 if isinstance(advance.get('amount'), Decimal):
                    advance['amount'] = float(advance['amount'])
            
            cur.execute("SELECT * FROM spendings ORDER BY date DESC")
            employee_spendings = cur.fetchall()
            
            # Optional: Convert amount for display
            for spending in employee_spendings:
                 if isinstance(spending.get('amount'), Decimal):
                    spending['amount'] = float(spending['amount'])

    except Exception as e:
        logger.error(f"Database error in employee_advances GET: {e}")
        # Flash the appropriate error (e.g., missing view) if needed
        
    finally:
        if conn:
            conn.close()
    
    return render_template('employee_advances.html',
                           employee_balances=employee_balances,
                           advances=advances,
                           employee_spendings=employee_spendings,
                           now=datetime.now())
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Debug information
    app.logger.info(f"Found {len(employee_balances)} employee balances")
    for balance in employee_balances:
        app.logger.info(f"Employee: {balance['employee_name']}, Advances: {balance['total_advances']}, Expenses: {balance['total_expenses']}, Balance: {balance['balance']}")
    
    return render_template('employee_advances.html', 
                         advances=advances, 
                         employee_spendings=employee_spendings,
                         employee_balances=employee_balances,
                         today=today)
# Delete spending
@app.route('/delete_spending/<int:id>', methods=['DELETE'])
def delete_spending(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM spendings WHERE id=%s", (id,))
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error in delete_spending: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# Vehicle monthly spendings (AJAX fetch)
@app.route('/vehicle_spendings/<int:vehicle_id>')
def vehicle_spendings(vehicle_id):
    month = request.args.get('month')
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            q = "SELECT * FROM spendings WHERE vehicle_id=%s"
            params = [vehicle_id]
            if month:
                q += " AND DATE_FORMAT(expense_month,'%%Y-%%m')=%s"
                params.append(month)
            q += " ORDER BY date DESC"
            cur.execute(q, params)
            rows = cur.fetchall()
    except Exception as e:
        app.logger.error(f"Error in vehicle_spendings: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
    return jsonify(rows)

# Monthly expenses report
@app.route('/monthly_report')
def monthly_report():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.*, v.vehicle_no 
                FROM spendings s 
                JOIN vehicles v ON s.vehicle_id = v.id 
                WHERE s.expense_month = %s 
                ORDER BY s.category, s.date
            """, (datetime.strptime(month, '%Y-%m').date().replace(day=1),))
            spendings = cur.fetchall()
            
            cur.execute("""
                SELECT IFNULL(SUM(amount),0) as total 
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

# API: Monthly expenses by vehicle
@app.route('/api/monthly_vehicle_expenses/<month>')
def monthly_vehicle_expenses(month):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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
                
            return jsonify(results)
            
    except Exception as e:
        app.logger.error(f"Error in monthly_vehicle_expenses: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# API: Overall monthly expenses
@app.route('/api/overall_monthly_expenses')
def overall_monthly_expenses():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    expense_month,
                    SUM(amount) as total_monthly_expense
                FROM spendings
                GROUP BY expense_month
                ORDER BY expense_month DESC
            """)
            
            results = cur.fetchall()
            for result in results:
                result['expense_month'] = result['expense_month'].strftime('%Y-%m')
                
            return jsonify(results)
            
    except Exception as e:
        app.logger.error(f"Error in overall_monthly_expenses: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# Add these routes for employee advances editing

# Edit employee advance - GET data
@app.route('/get_employee_advance/<int:id>')
def get_employee_advance(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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

# Edit employee advance - UPDATE data
@app.route('/edit_employee_advance/<int:id>', methods=['POST'])
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

# Delete employee advance
@app.route('/delete_employee_advance/<int:id>', methods=['DELETE'])
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

# Edit spending - GET data for editing
@app.route('/get_spending/<int:id>')
def get_spending(id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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

# Update spending - POST to save changes
@app.route('/update_spending/<int:id>', methods=['POST'])
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

# Hired Vehicles Audit Routes
@app.route('/hired_vehicles_audit')
def hired_vehicles_audit():
    conn = get_db_conn()
    hired_vehicles = []
    recent_transactions = []
    hired_vehicles_summary = []
    
    try:
        with conn.cursor() as cur:
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
                    'total_sales': summary['total_sales'] or 0,
                    'total_payments': summary['total_payments'] or 0
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

@app.route('/hired_vehicles_audit', methods=['POST'])
def hired_vehicles_audit_post():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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
                
    except Exception as e:
        app.logger.error(f"Error in hired_vehicles_audit_post: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('hired_vehicles_audit'))

# API for audit report
@app.route('/api/hired_vehicles_audit')
def api_hired_vehicles_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        vehicle_id = request.args.get('vehicle_id', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with conn.cursor() as cur:
            if vehicle_id == 'all':
                # Get summary for all vehicles for the selected month
                cur.execute("""
                    SELECT 
                        hv.id,
                        hv.vehicle_no,
                        hv.owner_name,
                        SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END) as total_sales,
                        SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END) as total_payments
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
                # Get detailed report for specific vehicle
                cur.execute("""
                    SELECT 
                        hv.id,
                        hv.vehicle_no,
                        hv.owner_name,
                        SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END) as total_sales,
                        SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END) as total_payments
                    FROM hired_vehicles hv
                    LEFT JOIN hired_vehicle_transactions t ON hv.id = t.hired_vehicle_id AND t.month_year = %s
                    WHERE hv.id = %s
                    GROUP BY hv.id, hv.vehicle_no, hv.owner_name
                """, (month_date, vehicle_id))
                
                summary = cur.fetchall()
                
                # Get transaction details
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

# Export hired vehicles audit
@app.route('/export/hired_vehicles_audit')
def export_hired_vehicles_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        vehicle_id = request.args.get('vehicle_id', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with conn.cursor() as cur:
            if vehicle_id == 'all':
                cur.execute("""
                    SELECT 
                        hv.vehicle_no,
                        hv.owner_name,
                        SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END) as total_sales,
                        SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END) as total_payments,
                        (SUM(CASE WHEN t.transaction_type = 'sale' THEN t.amount ELSE 0 END) - 
                         SUM(CASE WHEN t.transaction_type = 'payment' THEN t.amount ELSE 0 END)) as net_balance
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

# Transaction management routes
@app.route('/get_hired_vehicle_transaction/<int:transaction_id>')
def get_hired_vehicle_transaction(transaction_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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

# Company Audit Routes
@app.route('/company_audit')
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
        with conn.cursor() as cur:
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

@app.route('/company_audit', methods=['POST'])
def company_audit_post():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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
                
    except Exception as e:
        app.logger.error(f"Error in company_audit_post: {str(e)}")
        flash(f'An error occurred: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('company_audit'))

# API for company audit report
@app.route('/api/company_audit')
def api_company_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        company = request.args.get('company', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with conn.cursor() as cur:
            if company == 'all':
                # Get summary for all companies for the selected month
                cur.execute("""
                    SELECT 
                        company_name,
                        SUM(sale_amount) as sales_amount,
                        0 as received_amount
                    FROM company_sales 
                    WHERE month_year = %s
                    GROUP BY company_name
                    
                    UNION ALL
                    
                    SELECT 
                        company_name,
                        0 as sales_amount,
                        SUM(received_amount) as received_amount
                    FROM company_payments 
                    WHERE month_year = %s
                    GROUP BY company_name
                """, (month_date, month_date))
                
                raw_data = cur.fetchall()
                
                # Aggregate data by company
                company_data = {}
                for row in raw_data:
                    company = row['company_name']
                    if company not in company_data:
                        company_data[company] = {
                            'company_name': company,
                            'sales_amount': 0,
                            'received_amount': 0
                        }
                    company_data[company]['sales_amount'] += float(row['sales_amount'] or 0)
                    company_data[company]['received_amount'] += float(row['received_amount'] or 0)
                
                companies = list(company_data.values())
                for comp in companies:
                    comp['pending_amount'] = comp['sales_amount'] - comp['received_amount']
                
                # Get totals
                total_sales = sum(comp['sales_amount'] for comp in companies)
                total_received = sum(comp['received_amount'] for comp in companies)
                pending_amount = total_sales - total_received
                
                return jsonify({
                    'companies': companies,
                    'totals': {
                        'total_sales': total_sales,
                        'total_received': total_received,
                        'pending_amount': pending_amount
                    },
                    'month': month
                })
                
            else:
                # Get detailed report for specific company
                cur.execute("""
                    SELECT 
                        company_name,
                        SUM(sale_amount) as sales_amount
                    FROM company_sales 
                    WHERE company_name = %s AND month_year = %s
                    GROUP BY company_name
                """, (company, month_date))
                
                sales_result = cur.fetchone()
                sales_amount = float(sales_result['sales_amount'] or 0) if sales_result else 0
                
                cur.execute("""
                    SELECT 
                        company_name,
                        SUM(received_amount) as received_amount
                    FROM company_payments 
                    WHERE company_name = %s AND month_year = %s
                    GROUP BY company_name
                """, (company, month_date))
                
                payments_result = cur.fetchone()
                received_amount = float(payments_result['received_amount'] or 0) if payments_result else 0
                
                # Get transaction details
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

# Export company audit
@app.route('/export/company_audit')
def export_company_audit():
    conn = get_db_conn()
    try:
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        company = request.args.get('company', 'all')
        
        month_date = datetime.strptime(month, '%Y-%m').date().replace(day=1)
        
        with conn.cursor() as cur:
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

# Company transaction management routes
@app.route('/get_company_sale/<int:sale_id>')
def get_company_sale(sale_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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
def get_company_payment(payment_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
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

def create_company_audit_tables():
    """Create company audit tables if they don't exist"""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # Create company_sales table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_sales (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    sale_date DATE NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    invoice_number VARCHAR(100) UNIQUE,
                    sale_amount DECIMAL(12,2) NOT NULL,
                    description TEXT,
                    month_year DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create company_payments table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_payments (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    payment_date DATE NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    received_amount DECIMAL(12,2) NOT NULL,
                    payment_mode ENUM('cash', 'bank_transfer', 'upi', 'cheque') NOT NULL,
                    reference_number VARCHAR(100),
                    description TEXT,
                    month_year DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            logger.info("Company audit tables checked/created successfully")
            
    except Exception as e:
        logger.error(f"Error creating company audit tables: {e}")
    finally:
        conn.close()

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cur.fetchone()
                
                if user and bcrypt.check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session.permanent = False
                    
                    # Log login attempt
                    logger.info(f"User {username} logged in successfully from IP: {request.remote_addr}")
                    
                    flash('Login successful!', 'success')
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('index'))
                else:
                    # Log failed attempt
                    logger.warning(f"Failed login attempt for username: {username} from IP: {request.remote_addr}")
                    flash('Invalid username or password', 'error')
                    
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login', 'error')
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username')
    
    try:
        # Clear Flask session
        session.clear()
        
        # Create response
        response = make_response(redirect(url_for('login')))
        
        # Explicitly delete the session cookie
        response.set_cookie(app.session_cookie_name, '', 
                           expires=0, 
                           httponly=True,
                           secure=False)  # Set to True in production
        
        logger.info(f"User {username} logged out successfully")
        flash('You have been logged out successfully', 'success')
        
        return response
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        # Even if there's an error, try to redirect to login
        return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return redirect(url_for('change_password'))
        
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password_hash FROM users WHERE id = %s", (session['user_id'],))
                user = cur.fetchone()
                
                if user and bcrypt.check_password_hash(user['password_hash'], current_password):
                    new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
                    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", 
                               (new_password_hash, session['user_id']))
                    conn.commit()
                    
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
    app.run(host="0.0.0.0", port=5000, debug=True)