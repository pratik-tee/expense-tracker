from flask import Flask, render_template, request, redirect, url_for, session
import csv
import os
import hashlib

#for .env file
from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")








STATIC_FOLDER = 'static'
if not os.path.exists(STATIC_FOLDER):
    os.makedirs(STATIC_FOLDER)

app = Flask(__name__)
app.secret_key = 'your_secret_key'

USER_DATA_FOLDER = "user_data"
USER_DB = "users.csv"
os.makedirs(USER_DATA_FOLDER, exist_ok=True)

# --------------------- Helper Functions ---------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_authenticated():
    return 'username' in session

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --------------------- Routes ---------------------
@app.route('/')
@login_required
def index():
    username = session['username']
    total_spent = get_total_spent(username)
    total_entries = get_total_entries(username)
    return render_template("index.html",
                           username=username,
                           total_spent=total_spent,
                           total_entries=total_entries)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])

        if not os.path.exists(USER_DB):
            with open(USER_DB, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Username', 'Password'])

        with open(USER_DB, 'r') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row[0] == username:
                    return "User already exists!"

        with open(USER_DB, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([username, password])

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])

        with open(USER_DB, 'r') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if row[0] == username and row[1] == password:
                    session['username'] = username
                    return redirect(url_for('index'))  # Change 'index' to actual route

        error = " Invalid username or password. Please try again."

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('username', None)
    return render_template('logout.html')

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        username = session['username']
        date = request.form['date']
        item = request.form['item']
        price = request.form['price']
        description = request.form['description']
        category = request.form['category']

        file_path = os.path.join(USER_DATA_FOLDER, f"{username}.csv")
        file_exists = os.path.isfile(file_path)

        with open(file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date', 'Item', 'Price', 'Description', 'Category'])
            writer.writerow([date, item, price, description, category])

        return redirect(url_for('view_expenses'))

    return render_template('add.html')






from datetime import datetime
@app.route('/view', methods=['GET'])
@login_required
def view_expenses():
    from datetime import datetime

    username = session['username']
    file_path = os.path.join(USER_DATA_FOLDER, f"{username}.csv")
    expenses = []

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    month = request.args.get('month')
    year = request.args.get('year')

    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row:
                    continue
                try:
                    row_date = datetime.strptime(row[0], "%Y-%m-%d").date()
                except ValueError:
                    continue

                include = True
                if start_date and end_date:
                    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
                    ed = datetime.strptime(end_date, "%Y-%m-%d").date()
                    include = sd <= row_date <= ed
                elif month and year:
                    include = row_date.month == int(month) and row_date.year == int(year)
                elif year:
                    include = row_date.year == int(year)

                if include:
                    expenses.append(row)

    # ✅ Calculate total from filtered expenses
    total = 0
    try:
        total = sum(float(row[2]) for row in expenses)
    except (IndexError, ValueError):
        total = 0

    return render_template('view.html', rows=expenses, total=total, request=request, str=str)









  
from flask import flash  # Add this import if not already

@app.route('/delete/<int:index>', methods=['POST'])
@login_required
def delete_expense_by_index(index):
    username = session['username']
    file_path = os.path.join(USER_DATA_FOLDER, f"{username}.csv")

    if not os.path.isfile(file_path):
        return redirect(url_for('view_expenses'))

    with open(file_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        expenses = list(reader)

    if 0 <= index < len(expenses):
        del expenses[index]

        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            if header:
                writer.writerow(header)
            writer.writerows(expenses)

        flash("Expense deleted successfully!", "success")

    return redirect(url_for('view_expenses'))
  
    
    



import matplotlib.pyplot as plt
import csv
import os

@app.route('/pie')
@login_required
def pie_chart():
    username = session['username']
    file_path = os.path.join(USER_DATA_FOLDER, f"{username}.csv")
    pie_path = os.path.join('static', f"{username}_pie.png")

    if not os.path.exists(file_path):
        return render_template('pie.html', error="No expenses data found.")

    categories = {}
    with open(file_path, newline='') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                category = row[4]
                amount = float(row[2])
                categories[category] = categories.get(category, 0) + amount
            except (IndexError, ValueError):
                continue

    if not categories:
        return render_template('pie.html', error="No valid category data.")

    # Generate pie chart
    plt.figure(figsize=(6,6))
    plt.pie(categories.values(), labels=categories.keys(), autopct='%1.1f%%', startangle=90)
    plt.axis('equal')
    plt.title(f"{username}'s Spending by Category")

    # Save to static folder
    plt.savefig(pie_path)
    plt.close()

    return render_template('pie.html', pie_file=f"{username}_pie.png")


def get_total_spent(username):
    file_path = os.path.join(USER_DATA_FOLDER, f"{username}.csv")
    total = 0.0
    if os.path.exists(file_path):
        with open(file_path, newline='') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                try:
                    total += float(row[2])  # Assuming price is 3rd column
                except (IndexError, ValueError):
                    pass
    return round(total, 2)


def get_total_entries(username):
    file_path = os.path.join(USER_DATA_FOLDER, f"{username}.csv")
    count = 0
    if os.path.exists(file_path):
        with open(file_path, newline='') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            count = sum(1 for _ in reader)
    return count






# --------------------- Main ---------------------
if __name__ == '__main__':
   port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
