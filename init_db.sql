\c tsr_db;

DROP VIEW IF EXISTS employee_balance;

\c tsr_db;

-- Drop the existing view
DROP VIEW IF EXISTS employee_balance;

-- Create corrected employee_balance view
-- Drop and recreate the employee_balance view with proper calculation
DROP VIEW IF EXISTS employee_balance;

CREATE VIEW employee_balance AS
SELECT 
    emp.employee_name,
    COALESCE(adv.total_advances, 0) as total_advances,
    COALESCE(exp.total_expenses, 0) as total_expenses,
    (COALESCE(adv.total_advances, 0) - COALESCE(exp.total_expenses, 0)) as balance
FROM 
    -- Union of all unique employee names from both tables
    (SELECT DISTINCT employee_name FROM employee_advances 
     WHERE employee_name IS NOT NULL AND employee_name != ''
     UNION 
     SELECT DISTINCT spended_by as employee_name FROM spendings 
     WHERE spended_by IS NOT NULL AND spended_by != '') emp
LEFT JOIN 
    -- Pre-aggregated total advances
    (SELECT employee_name, SUM(amount) as total_advances 
     FROM employee_advances 
     WHERE employee_name IS NOT NULL AND employee_name != ''
     GROUP BY employee_name) adv ON emp.employee_name = adv.employee_name
LEFT JOIN 
    -- Pre-aggregated total expenses
    (SELECT spended_by as employee_name, SUM(amount) as total_expenses 
     FROM spendings 
     WHERE spended_by IS NOT NULL AND spended_by != '' 
     GROUP BY spended_by) exp ON emp.employee_name = exp.employee_name
WHERE emp.employee_name IS NOT NULL AND emp.employee_name != '';

-- init_db.sql
CREATE DATABASE IF NOT EXISTS tsr_db;
\c tsr_db;

-- Vehicles table
CREATE TABLE IF NOT EXISTS vehicles (
  id SERIAL PRIMARY KEY,
  vehicle_no VARCHAR(50) NOT NULL UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Companies table
CREATE TABLE IF NOT EXISTS companies (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Allocations table
CREATE TABLE IF NOT EXISTS allocations (
  id SERIAL PRIMARY KEY,
  vehicle_id INT NOT NULL,
  company_id INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
  FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

-- Main spendings table with expense_month field
CREATE TABLE IF NOT EXISTS spendings (
  id SERIAL PRIMARY KEY,
  vehicle_id INT NOT NULL,
  date DATE NOT NULL, -- actual transaction date
  expense_month DATE NOT NULL, -- belongs-to month (YYYY-MM-01 format)
  category VARCHAR(50) NOT NULL, -- diesel, salary, others
  reason VARCHAR(255),
  amount DECIMAL(12,2) NOT NULL,
  spended_by TEXT DEFAULT NULL,
  mode VARCHAR(20) DEFAULT NULL, -- Payment mode (Cash, UPI, Automatic)
  marked BOOLEAN DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
  INDEX idx_expense_month (expense_month),
  INDEX idx_vehicle_expense (vehicle_id, expense_month)
);

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
  id SERIAL PRIMARY KEY,
  company_id INT NOT NULL,
  vehicle_id INT, -- optional, but if allocated it's set
  date DATE NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
);

-- Company summary table
CREATE TABLE IF NOT EXISTS company_summary (
    id SERIAL PRIMARY KEY,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255),
    credit DECIMAL(10,2) DEFAULT 0.00,
    debit DECIMAL(10,2) DEFAULT 0.00,
    mode TEXT DEFAULT 'Cash'
);

-- Vehicle spending table
CREATE TABLE IF NOT EXISTS vehicle_spending (
    id SERIAL PRIMARY KEY,
    vehicle_no VARCHAR(50),
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description VARCHAR(255),
    amount DECIMAL(10,2),
    mode TEXT DEFAULT 'Cash'
);

-- Employee advances table
CREATE TABLE IF NOT EXISTS employee_advances (
    id SERIAL PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    purpose VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Monthly expense summary view (optional but helpful)
CREATE OR REPLACE VIEW monthly_expense_summary AS
SELECT 
    TO_CHAR(expense_month, '%Y-%m') as month,
    vehicle_id,
    v.vehicle_no,
    category,
    SUM(amount) as total_amount,
    COUNT(*) as transaction_count
FROM spendings s
JOIN vehicles v ON s.vehicle_id = v.id
GROUP BY expense_month, vehicle_id, category
ORDER BY expense_month DESC, total_amount DESC;

-- Vehicle monthly total view
CREATE OR REPLACE VIEW vehicle_monthly_totals AS
SELECT 
    TO_CHAR(expense_month, '%Y-%m') as month,
    vehicle_id,
    v.vehicle_no,
    SUM(amount) as monthly_total
FROM spendings s
JOIN vehicles v ON s.vehicle_id = v.id
GROUP BY expense_month, vehicle_id
ORDER BY expense_month DESC, monthly_total DESC;

-- Overall monthly totals view
CREATE OR REPLACE VIEW overall_monthly_totals AS
SELECT 
    TO_CHAR(expense_month, '%Y-%m') as month,
    SUM(amount) as total_expense,
    COUNT(*) as transaction_count
FROM spendings
GROUP BY expense_month
ORDER BY expense_month DESC;

-- Insert sample data for testing
INSERT IGNORE INTO vehicles (vehicle_no) VALUES 
('3393'),
('407'),
('202'),
('505');

INSERT IGNORE INTO companies (name) VALUES 
('ABC Transport'),
('XYZ Logistics'),
('Quick Delivery'),
('Fast Cargo');

-- Sample spendings data for testing monthly expenses
INSERT IGNORE INTO spendings (vehicle_id, date, expense_month, category, reason, amount, spended_by, mode) VALUES
(1, '2024-01-15', '2024-01-01', 'diesel', 'Diesel - Paid', 5000.00, 'MSR', 'UPI'),
(1, '2024-01-20', '2024-01-01', 'salary', 'Driver Salary', 8000.00, 'TSR', 'Cash'),
(2, '2024-01-10', '2024-01-01', 'diesel', 'Diesel - Paid', 4500.00, 'MSR', 'UPI'),
(2, '2024-01-25', '2024-01-01', 'others', 'Maintenance', 2000.00, 'TSR', 'Cash'),
(3, '2024-01-05', '2024-01-01', 'diesel', 'Diesel - Unpaid', 4800.00, NULL, NULL),
(1, '2024-02-12', '2024-02-01', 'diesel', 'Diesel - Paid', 5200.00, 'MSR', 'UPI'),
(1, '2024-02-18', '2024-02-01', 'salary', 'Driver Salary', 8000.00, 'TSR', 'Cash'),
(2, '2024-02-08', '2024-02-01', 'diesel', 'Diesel - Paid', 4600.00, 'MSR', 'UPI'),
(3, '2024-02-22', '2024-02-01', 'others', 'Repair', 3500.00, 'TSR', 'Cash');

-- Sample payments data
INSERT IGNORE INTO payments (company_id, vehicle_id, date, amount) VALUES
(1, 1, '2024-01-10', 15000.00),
(2, 2, '2024-01-15', 12000.00),
(3, 3, '2024-01-20', 10000.00),
(1, 1, '2024-02-12', 16000.00),
(2, 2, '2024-02-18', 13000.00);

-- Sample employee advances
INSERT IGNORE INTO employee_advances (employee_name, date, amount, purpose) VALUES
('Rajesh Kumar', '2024-01-05', 5000.00, 'Advance for family emergency'),
('Suresh Patel', '2024-01-10', 3000.00, 'Medical advance'),
('Rajesh Kumar', '2024-02-08', 4000.00, 'Festival advance');

-- Create a user for the application with appropriate privileges
CREATE USER IF NOT EXISTS 'tsr_user'@'localhost' IDENTIFIED BY 'tsr_password';
GRANT SELECT, INSERT, UPDATE, DELETE ON tsr_db.* TO 'tsr_user'@'localhost';
FLUSH PRIVILEGES;

-- Show table structure confirmation
SHOW TABLES;

-- Display sample data from key tables
SELECT 'Vehicles:' AS '';
SELECT * FROM vehicles;

SELECT 'Companies:' AS '';
SELECT * FROM companies;

SELECT 'Sample Spendings:' AS '';
SELECT s.id, v.vehicle_no, s.date, s.expense_month, s.category, s.reason, s.amount, s.spended_by, s.mode 
FROM spendings s 
JOIN vehicles v ON s.vehicle_id = v.id 
ORDER BY s.expense_month DESC, s.date DESC 
LIMIT 5;

SELECT 'Monthly Expense Summary:' AS '';
SELECT * FROM monthly_expense_summary LIMIT 10;

SELECT 'Vehicle Monthly Totals:' AS '';
SELECT * FROM vehicle_monthly_totals LIMIT 10;

SELECT 'Overall Monthly Totals:' AS '';
SELECT * FROM overall_monthly_totals LIMIT 12;

-- Create hired_vehicles table
CREATE TABLE hired_vehicles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    vehicle_no VARCHAR(50) UNIQUE NOT NULL,
    owner_name VARCHAR(100),
    contact_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create hired_vehicle_transactions table
CREATE TABLE hired_vehicle_transactions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    hired_vehicle_id INT,
    transaction_date DATE NOT NULL,
    transaction_type TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    description TEXT,
    reference_no VARCHAR(100),
    month_year DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hired_vehicle_id) REFERENCES hired_vehicles(id) ON DELETE CASCADE
);

-- Company sales and payments tracking
CREATE TABLE company_sales (
    id INT PRIMARY KEY AUTO_INCREMENT,
    sale_date DATE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    invoice_number VARCHAR(100) UNIQUE,
    sale_amount DECIMAL(12,2) NOT NULL,
    description TEXT,
    month_year DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE company_payments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    payment_date DATE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    received_amount DECIMAL(12,2) NOT NULL,
    payment_mode TEXT NOT NULL,
    reference_number VARCHAR(100),
    description TEXT,
    month_year DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
