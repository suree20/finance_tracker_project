from flask import Flask, render_template, request, jsonify, redirect, request, url_for, session
import mysql.connector
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import math
import io
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from dotenv import load_dotenv
import os

load_dotenv()

database_password = os.getenv("DATABASE_PASSWORD")
database_user = os.getenv("DATABASE_USER")
database_host = os.getenv("DATABASE_HOST")
database_name = os.getenv("DATABASE_NAME")

app = Flask(__name__)
db = mysql.connector.connect(
    host=database_host,
    user=database_user,
    password=database_password,
    database=database_name
)
cursor = db.cursor()

def initialize_tables():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Category (
        category_id INT AUTO_INCREMENT PRIMARY KEY,
        category_name VARCHAR(100) NOT NULL
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Transaction (
        transaction_id INT AUTO_INCREMENT PRIMARY KEY,
        category_id INT,
        amount DECIMAL(10, 2) NOT NULL,
        transaction_type VARCHAR(50),
        description TEXT,
        transaction_date DATE NOT NULL,
        FOREIGN KEY (category_id) REFERENCES Category(category_id)
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Budget (
        budget_id INT AUTO_INCREMENT PRIMARY KEY,
        category_id INT,
        amount DECIMAL(10, 2) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        FOREIGN KEY (category_id) REFERENCES Category(category_id)
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Notification (
        notification_id INT AUTO_INCREMENT PRIMARY KEY,
        message TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read BOOLEAN DEFAULT FALSE
    );
    ''')

def initialize_function():
    cursor.execute('''
    CREATE FUNCTION IF NOT EXISTS CalculateMonthlyExpenditure(cat_id INT, month_val INT, year_val INT)
    RETURNS DECIMAL(10,2)
    DETERMINISTIC
    BEGIN
        DECLARE total DECIMAL(10,2);
        SELECT SUM(amount) INTO total
        FROM Transaction
        WHERE category_id = cat_id 
            AND transaction_type = 'expense'
            AND MONTH(transaction_date) = month_val
            AND YEAR(transaction_date) = year_val;
        RETURN IFNULL(total, 0);
    END;
    ''')

def initialize_procedures():
    cursor.execute('''
    CREATE PROCEDURE IF NOT EXISTS CheckBudgetExceed (IN cat_id INT, IN trans_date DATE)
    BEGIN
        DECLARE total_spent DECIMAL(10, 2);
        DECLARE budget_amount DECIMAL(10, 2);
        DECLARE exceed_amount DECIMAL(10, 2);
        DECLARE exceed_message VARCHAR(255);
        SET total_spent = CalculateMonthlyExpenditure(cat_id, MONTH(trans_date), YEAR(trans_date));
        SELECT amount INTO budget_amount
        FROM Budget
        WHERE category_id = cat_id
              AND start_date <= trans_date
              AND end_date >= trans_date
        ORDER BY end_date DESC
        LIMIT 1;
        SET exceed_amount = total_spent - budget_amount;
        SET exceed_message = CONCAT('Budget exceeded for category ID ', cat_id, ' by amount: Rs.', exceed_amount);
        IF total_spent > budget_amount THEN
            INSERT INTO Notification (message)
            VALUES (exceed_message);
        END IF;
    END;
    ''')

    cursor.execute('''
    CREATE TRIGGER IF NOT EXISTS AfterTransactionInsert
    AFTER INSERT ON Transaction
    FOR EACH ROW
    BEGIN
        CALL CheckBudgetExceed(NEW.category_id, NEW.transaction_date);
    END;
    ''')

def monthly_analytics(month, year):
    cursor.execute(f'''
    SELECT c.category_name,
           SUM(CASE WHEN t.transaction_type = 'expense' THEN t.amount ELSE 0 END) AS total_expense,
           SUM(CASE WHEN t.transaction_type = 'income' THEN t.amount ELSE 0 END) AS total_income
    FROM Category c
    LEFT JOIN Transaction t ON c.category_id = t.category_id
         AND MONTH(t.transaction_date) = %s 
         AND YEAR(t.transaction_date) = %s
    GROUP BY c.category_id;
    ''', (month, year))

    return cursor.fetchall()

def total_budget_vs_expense(month, year):
    cursor.execute('''
    SELECT c.category_name, 
           IFNULL(SUM(b.amount), 0) AS total_budget,
           IFNULL(SUM(t.amount), 0) AS total_expense
    FROM Category c
    LEFT JOIN Budget b ON c.category_id = b.category_id
                        AND MONTH(b.start_date) <= %s 
                        AND MONTH(b.end_date) >= %s
                        AND YEAR(b.start_date) <= %s
                        AND YEAR(b.end_date) >= %s
    LEFT JOIN Transaction t ON c.category_id = t.category_id
                             AND t.transaction_type = 'expense'
                             AND MONTH(t.transaction_date) = %s
                             AND YEAR(t.transaction_date) = %s
    GROUP BY c.category_id;
    ''', (month, month, year, year, month, year))
    
    return cursor.fetchall()

def income_vs_expenses(month, year):
    results = monthly_analytics(month, year)
    data = pd.DataFrame(results, columns=['Category', 'Total Expense', 'Total Income'])
    data['Total Expense'] = pd.to_numeric(data['Total Expense'], errors='coerce').fillna(0)
    data['Total Income'] = pd.to_numeric(data['Total Income'], errors='coerce').fillna(0)

    fig, ax = plt.subplots()
    ax.bar(data['Category'], data['Total Expense'], color='red', label='Total Expense')
    ax.bar(data['Category'], data['Total Income'], color='green', label='Total Income', alpha=0.6)
    ax.set_title('Income vs Expenses')
    ax.set_ylabel('Amount')
    ax.legend()
    img = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(img)
    img.seek(0)
    graph = base64.b64encode(img.getvalue()).decode('utf-8')
    return graph

def budget_vs_expense(month, year):
    results = total_budget_vs_expense(month, year)
    data = pd.DataFrame(results, columns=['Category', 'Total Budget', 'Total Expense'])
    
    data['Total Budget'] = pd.to_numeric(data['Total Budget'], errors='coerce').fillna(0)
    data['Total Expense'] = pd.to_numeric(data['Total Expense'], errors='coerce').fillna(0)

    bar_width = 0.35
    index = range(len(data))

    fig, ax = plt.subplots()
    ax.bar(index, data['Total Budget'], width=bar_width, color='blue', label='Total Budget')
    ax.bar([i + bar_width for i in index], data['Total Expense'], width=bar_width, color='red', label='Total Expense')

    ax.set_title('Budget vs Actual Expenses')
    ax.set_ylabel('Amount')
    ax.set_xticks([i + bar_width / 2 for i in index]) 
    ax.set_xticklabels(data['Category'])
    ax.legend()

    img = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(img)
    img.seek(0)
    graph = base64.b64encode(img.getvalue()).decode('utf-8')
    return graph

def category_spending_breakdown(month, year):
    results = monthly_analytics(month, year)
    data = pd.DataFrame(results, columns=['Category', 'Total Expense', 'Total Income'])
    data['Total Expense'] = pd.to_numeric(data['Total Expense'], errors='coerce').fillna(0)
    data['Total Income'] = pd.to_numeric(data['Total Income'], errors='coerce').fillna(0)

    if data['Total Expense'].sum() == 0:
        return "No expenses to show for the selected month and year."
    else:
        fig, ax = plt.subplots()
        ax.pie(data['Total Expense'], labels=data['Category'], autopct='%1.1f%%', startangle=90)
        ax.set_title('Spending Breakdown by Category')

        img = io.BytesIO()
        canvas = FigureCanvas(fig)
        canvas.print_png(img)
        img.seek(0)
        graph = base64.b64encode(img.getvalue()).decode('utf-8')
        return graph


def keymetrics(date):
    cursor.execute("""
        SELECT 
            b.amount AS budget, 
            b.category_id, 
            COALESCE(SUM(t.amount), 0) AS total_expenses
        FROM 
            budget b
        LEFT JOIN 
            transaction t ON b.category_id = t.category_id
        WHERE 
            b.start_date < %s 
            AND YEAR(%s) <= YEAR(b.end_date) 
            AND MONTH(%s)+1 <= MONTH(b.end_date)
        GROUP BY 
            b.category_id, b.amount;
    """, (date, date, date))
    return cursor.fetchall()

def convert_to_float(value):
    """Helper function to convert to float and handle NaN."""
    try:
        return float(value) if not math.isnan(value) else 0
    except (ValueError, TypeError):
        return 0.0

@app.route('/add_category', methods=['POST'])
def add_category():
    category_name = request.form['category_name']
    cursor.execute("INSERT INTO category (category_name) VALUES (%s)", (category_name,))
    db.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_budget', methods=['POST'])
def add_budget():
    category_id = request.form['category_id']
    budget_amount = request.form['budget_amount']
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    
    cursor.execute("INSERT INTO budget (category_id, amount, start_date, end_date) VALUES (%s, %s, %s, %s)", 
                   (category_id, budget_amount, start_date, end_date))
    db.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    category_id = request.form['transaction_category_id']
    amount = request.form['amount']
    transaction_type = request.form['transaction_type']
    description = request.form['description']
    transaction_date = request.form['transaction_date']

    cursor.execute("INSERT INTO transaction (category_id, amount, transaction_type, description, transaction_date) VALUES (%s, %s, %s, %s, %s)", 
                   (category_id, amount, transaction_type, description, transaction_date))
    db.commit()
    return redirect(url_for('dashboard'))

@app.route('/')
def dashboard():
    current_date = date.today()
    result  = keymetrics(current_date)
    col1, col2, col3, col4 = [], [], [], []
    for record in result:
        amount, category_id, total_expenses = record
        amount = convert_to_float(amount)
        total_expenses = convert_to_float(total_expenses)
        remaining_budget = max(amount - total_expenses, 0)

        col1.append(category_id)
        col2.append(amount)
        col3.append(f"Rs.{total_expenses}")
        col4.append(f"Rs.{remaining_budget}")

    return render_template('dashboard.html', col1=col1, col2=col2, col3=col3, col4=col4)

@app.route('/analytics', methods=['POST'])
def analytics():
    print(request.json)
    month = request.json['month']
    year = request.json['year']
    print(month, year)
    
    income_vs_expenses_graph = income_vs_expenses(month, year)
    budget_vs_expense_graph = budget_vs_expense(month, year)
    category_spending_breakdown_graph = category_spending_breakdown(month, year)

    return jsonify({
        'income_vs_expenses_graph': income_vs_expenses_graph,
        'budget_vs_expense_graph': budget_vs_expense_graph,
        'categorical_spending_breakdown': category_spending_breakdown_graph
    })

@app.route('/get_notifications', methods=['GET'])
def get_notifications():
    cursor.execute('''
        SELECT notification_id, message, sent_at
        FROM Notification
        WHERE is_read = FALSE
        ORDER BY sent_at DESC;
    ''')
    notifications = cursor.fetchall()
    
    return jsonify({
        'notifications': notifications
    })

@app.route('/mark_as_read/<int:notification_id>', methods=['POST'])
def mark_as_read(notification_id):
    cursor.execute('''
        UPDATE Notification
        SET is_read = TRUE
        WHERE notification_id = %s;
    ''', (notification_id,))
    db.commit()
    
    return jsonify({
        'message': 'Notification marked as read'
    })


if __name__ == '__main__':
    app.run(debug=True)
