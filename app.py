from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
import os
import csv   
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt


# -------------------- APP CONFIG --------------------



app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")

DB_NAME = "expenses.db"
STATIC_FOLDER = "static"
EXPORT_FOLDER = "exports"   

os.makedirs(STATIC_FOLDER, exist_ok=True)
os.makedirs(EXPORT_FOLDER, exist_ok=True)


# -------------------- DATABASE --------------------

def get_db():
    con = sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con



def init_db():
    con = get_db()
    cur = con.cursor()

    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_verified INTEGER DEFAULT 1,
        created_at TEXT
    )
""")

    # Personal Expenses table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    
      # Groups
    cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # Group members
    cur.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TEXT,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Group expenses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS group_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            paid_by INTEGER NOT NULL,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            date TEXT,
            created_at TEXT,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (paid_by) REFERENCES users(id)
        )
    """)

    # Notifications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    
    #expense_splits dbms------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expense_splits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        share REAL NOT NULL,
        is_settled INTEGER DEFAULT 0,
        FOREIGN KEY (expense_id) REFERENCES group_expenses(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")

    

    con.commit()
    con.close()

init_db()

# -------------------- AUTH DECORATOR --------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# -------------------- AUTH ROUTES --------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        try:
            con = get_db()
            cur = con.cursor()
            cur.execute(
                "INSERT INTO users (email, password, is_verified, created_at) VALUES (?, ?, 1, DATE('now'))",
                (email, password)
            )
            con.commit()
            con.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return "Email already exists"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        con = get_db()
        cur = con.cursor()
        cur.execute(
            "SELECT id, password FROM users WHERE email = ?",
            (email,)
        )
        user = cur.fetchone()
        con.close()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            session["email"] = email
            return redirect(url_for("index"))

        return "Invalid email or password"

    return render_template("login.html")



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------- DASHBOARD --------------------

@app.route("/")
@login_required
def index():
    con = get_db()
    cur = con.cursor()

    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM expenses WHERE user_id = ?",
        (session["user_id"],)
    )
    total_entries, total_spent = cur.fetchone()
    con.close()

    return render_template(
        "index.html",
        email=session.get("email"),  
        total_entries=total_entries,
        total_spent=round(total_spent, 2)
    )


# -------------------- ADD EXPENSE --------------------

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        title = request.form["title"]
        amount = request.form["amount"]
        category = request.form["category"]
        date = request.form["date"]

        con = get_db()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO expenses (user_id, title, amount, category, date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            title,
            amount,
            category,
            date
        ))
        con.commit()
        con.close()

        return redirect(url_for("view_expenses"))

    return render_template("add.html")

# -------------------- VIEW + FILTER --------------------

@app.route("/view")
@login_required
def view_expenses():
    start = request.args.get("start")
    end = request.args.get("end")
    category = request.args.get("category")

    query = "SELECT * FROM expenses WHERE user_id = ?"
    params = [session["user_id"]]

    if start:
        query += " AND date >= ?"
        params.append(start)
    if end:
        query += " AND date <= ?"
        params.append(end)
    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY date DESC"

    con = get_db()
    cur = con.cursor()
    cur.execute(query, params)
    expenses = cur.fetchall()

    cur.execute(
        "SELECT COALESCE(SUM(amount),0) FROM (" + query + ")",
        params
    )
    total = cur.fetchone()[0]
    con.close()

    return render_template(
        "view.html",
        expenses=expenses,
        total=round(total, 2)
    )

# -------------------- DELETE EXPENSE --------------------

@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_expense(id):
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (id, session["user_id"])
    )
    con.commit()
    con.close()
    return redirect(url_for("view_expenses"))

# -------------------- PIE CHART --------------------

@app.route("/pie")
@login_required
def pie_chart():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id = ?
        GROUP BY category
    """, (session["user_id"],))
    data = cur.fetchall()
    con.close()

    if not data:
        return render_template("pie.html", error="No data to display")

    labels = [row[0] for row in data]
    values = [row[1] for row in data]

    pie_file = f"user_{session['user_id']}_pie.png"
    pie_path = os.path.join(STATIC_FOLDER, pie_file)

    plt.figure(figsize=(6,6))
    plt.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    plt.axis("equal")
    plt.title("Spending by Category")
    plt.savefig(pie_path)
    plt.close()

    return render_template("pie.html", pie_file=pie_file)

# -------------CSV---------------------------


@app.route("/export")
@login_required
def export_csv():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT date, title, amount, category
        FROM expenses
        WHERE user_id = ?
        ORDER BY date DESC
    """, (session["user_id"],))

    rows = cur.fetchall()
    con.close()

    file_path = os.path.join(EXPORT_FOLDER, "expenses.csv")

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Title", "Amount", "Category"])
        writer.writerows(rows)

    return send_file(
        file_path,
        as_attachment=True,
        download_name="expenses.csv"
    )






# ================== DELETE GROUP EXPENSE ==================

@app.route("/groups/<int:group_id>/delete", methods=["POST"])
@login_required
def delete_group(group_id):
    con = get_db()
    cur = con.cursor()

    # 1️⃣ Check if current user is admin of this group
    cur.execute("""
        SELECT role FROM group_members
        WHERE group_id = ? AND user_id = ?
    """, (group_id, session["user_id"]))
    role = cur.fetchone()

    if not role or role[0] != "admin":
        con.close()
        return "Unauthorized", 403

    # 2️⃣ Delete expense splits
    cur.execute("""
        DELETE FROM expense_splits
        WHERE expense_id IN (
            SELECT id FROM group_expenses WHERE group_id = ?
        )
    """, (group_id,))

    # 3️⃣ Delete group expenses
    cur.execute("""
        DELETE FROM group_expenses WHERE group_id = ?
    """, (group_id,))

    # 4️⃣ Delete group members
    cur.execute("""
        DELETE FROM group_members WHERE group_id = ?
    """, (group_id,))

    # 5️⃣ Delete group
    cur.execute("""
        DELETE FROM groups WHERE id = ?
    """, (group_id,))

    con.commit()
    con.close()

    return redirect(url_for("groups"))   # 👈 IMPORTANT


#====================================

@app.route("/groups/<int:group_id>/expense/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete_group_expense(group_id, expense_id):
    con = get_db()
    cur = con.cursor()

    # 1️⃣ Fetch expense + payer
    cur.execute("""
        SELECT paid_by
        FROM group_expenses
        WHERE id = ? AND group_id = ?
    """, (expense_id, group_id))
    row = cur.fetchone()

    if not row:
        con.close()
        return "Expense not found", 404

    paid_by = int(row[0])  # 👈 IMPORTANT

    # 2️⃣ Fetch role of current user
    cur.execute("""
        SELECT role
        FROM group_members
        WHERE group_id = ? AND user_id = ?
    """, (group_id, session["user_id"]))
    role_row = cur.fetchone()

    role = role_row[0] if role_row else None
    is_admin = role == "admin"

    # 3️⃣ Permission check
    if session["user_id"] != paid_by and not is_admin:
        con.close()
        return "Unauthorized", 403

    # 4️⃣ Delete splits
    cur.execute("""
        DELETE FROM expense_splits
        WHERE expense_id = ?
    """, (expense_id,))

    # 5️⃣ Delete expense
    cur.execute("""
        DELETE FROM group_expenses
        WHERE id = ?
    """, (expense_id,))

    con.commit()
    con.close()

    return redirect(url_for("group_detail", group_id=group_id))









#-----------------------------for create group app routes------------------------------


@app.route("/groups/create", methods=["GET", "POST"])
@login_required
def create_group():
    if request.method == "POST":
        group_name = request.form["group_name"]
        user_id = session["user_id"]

        con = get_db()
        cur = con.cursor()

        cur.execute("""
            INSERT INTO groups (name, created_by, created_at)
            VALUES (?, ?, DATE('now'))
        """, (group_name, user_id))

        group_id = cur.lastrowid

        cur.execute("""
            INSERT INTO group_members (group_id, user_id, role, joined_at)
            VALUES (?, ?, 'admin', DATE('now'))
        """, (group_id, user_id))

        con.commit()
        con.close()

        # 🔥 FIXED HERE
        return redirect(url_for("groups"))

    return render_template("create_group.html")



#-------------------list group ----------------------------------------

@app.route("/groups")
@login_required
def groups():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT g.id, g.name, gm.role
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id = ?
    """, (session["user_id"],))

    rows = cur.fetchall()
    con.close()

    groups = []
    for r in rows:
        groups.append({
            "id": r[0],
            "name": r[1],
            "role": r[2]
        })

    return render_template("groups.html", groups=groups)




# ------------------------------------ Invite Member Route ------------------------------------

@app.route("/groups/<int:group_id>/invite", methods=["GET", "POST"])
@login_required
def invite_member(group_id):
    con = get_db()
    cur = con.cursor()

    try:
        # 1️⃣ Check if current user is admin
        cur.execute("""
            SELECT role FROM group_members
            WHERE group_id = ? AND user_id = ?
        """, (group_id, session["user_id"]))
        role = cur.fetchone()

        if not role or role[0] != "admin":
            return "Unauthorized", 403

        # 2️⃣ Fetch group name
        cur.execute("SELECT name FROM groups WHERE id = ?", (group_id,))
        group = cur.fetchone()

        if not group:
            return "Group not found", 404

        group_name = group[0]

        if request.method == "POST":
            email = request.form["email"].strip().lower()

            # 3️⃣ Find user by email
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            user = cur.fetchone()

            if not user:
                return "User with this email does not exist"

            invited_user_id = user[0]

            # 4️⃣ Check if already a member
            cur.execute("""
                SELECT id FROM group_members
                WHERE group_id = ? AND user_id = ?
            """, (group_id, invited_user_id))

            if cur.fetchone():
                return "User already in group"

            # 5️⃣ Add user to group
            cur.execute("""
                INSERT INTO group_members (group_id, user_id, role, joined_at)
                VALUES (?, ?, 'member', DATE('now'))
            """, (group_id, invited_user_id))
            
            con.commit()
            con.close()

            # 6️⃣ Create notification (SAME cursor → NO LOCK)
            create_notification(
            invited_user_id,
             f"You were added to the group '{group_name}'"
)


            return redirect(url_for("group_detail", group_id=group_id))

        return render_template("invite_member.html", group_id=group_id)

    finally:
        con.close()





#-----------------------------------------------Group Details---------------------------------

@app.route("/groups/<int:group_id>")
@login_required
def group_detail(group_id):
    con = get_db()
    cur = con.cursor()

    # 1️⃣ Group info
    cur.execute("SELECT id, name FROM groups WHERE id = ?", (group_id,))
    group = cur.fetchone()

    if not group:
        con.close()
        return "Group not found", 404

    # 2️⃣ Members
    cur.execute("""
        SELECT u.email, gm.role, u.id
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ?
    """, (group_id,))
    members = cur.fetchall()

    # 3️⃣ Group expenses
    cur.execute("""
    SELECT ge.id, ge.title, ge.amount, ge.category, ge.date, u.email, ge.paid_by
    FROM group_expenses ge
    JOIN users u ON ge.paid_by = u.id
    WHERE ge.group_id = ?
    ORDER BY ge.date DESC
""", (group_id,))
    expenses = cur.fetchall()


    # 4️⃣ BALANCES (core split logic)
    cur.execute("""
        SELECT 
            u.email,
            ROUND(
                SUM(es.share) -
                COALESCE(SUM(
                    CASE 
                        WHEN ge.paid_by = u.id THEN ge.amount
                        ELSE 0
                    END
                ), 0), 2
            ) AS balance
        FROM users u
        JOIN expense_splits es ON es.user_id = u.id
        JOIN group_expenses ge ON ge.id = es.expense_id
        WHERE ge.group_id = ?
        GROUP BY u.id
    """, (group_id,))
    balances = cur.fetchall()

    con.close()

    return render_template(
        "group_detail.html",
        group=group,
        members=members,
        expenses=expenses,
        balances=balances,
        group_id=group_id
    )







#-------------------------------------------------ADD GROUP EXPENSE ROUTE-----------------------------------------------

@app.route("/groups/<int:group_id>/add-expense", methods=["GET", "POST"])
@login_required
def add_group_expense(group_id):
    con = get_db()
    cur = con.cursor()

    # Members
    cur.execute("""
        SELECT user_id FROM group_members
        WHERE group_id = ?
    """, (group_id,))
    members = [r["user_id"] for r in cur.fetchall()]

    if session["user_id"] not in members:
        con.close()
        return "Unauthorized", 403

    if request.method == "POST":
        title = request.form["title"]
        amount = float(request.form["amount"])
        category = request.form["category"]
        date = request.form["date"]

        # Insert expense
        cur.execute("""
            INSERT INTO group_expenses
            (group_id, paid_by, title, amount, category, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, DATE('now'))
        """, (
            group_id,
            session["user_id"],
            title,
            amount,
            category,
            date
        ))

        expense_id = cur.lastrowid
        split_amount = round(amount / len(members), 2)

        for uid in members:
            cur.execute("""
                INSERT INTO expense_splits (expense_id, user_id, share)
                VALUES (?, ?, ?)
            """, (expense_id, uid, split_amount))

            if uid != session["user_id"]:
                create_notification(
                    cur,
                    uid,
                    f"You owe ₹{split_amount} for '{title}'"
                )

        # ✅ ONE commit only
        con.commit()
        con.close()

        return redirect(url_for("group_detail", group_id=group_id))

    con.close()
    return render_template("add_group_expense.html", group_id=group_id)







#------------------------------------------app Notification---------------------------------------------------

def create_notification(cur, user_id, message):
    cur.execute("""
        INSERT INTO notifications (user_id, message, is_read, created_at)
        VALUES (?, ?, 0, DATE('now'))
    """, (user_id, message))









#----------------------------------------FETCH USER NOTIFICATIONS------------------------------------------------------


@app.route("/notifications")
@login_required
def notifications():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT id, message, is_read, created_at
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (session["user_id"],))

    notifications = cur.fetchall()
    con.close()

    return render_template("notifications.html", notifications=notifications)





#------------------------------------------------------MARK NOTIFICATION AS READ--------------------------------------------


@app.route("/notifications/read/<int:notif_id>")
@login_required
def mark_notification_read(notif_id):
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        UPDATE notifications SET is_read = 1
        WHERE id = ? AND user_id = ?
    """, (notif_id, session["user_id"]))

    con.commit()
    con.close()

    return redirect(url_for("notifications"))


#------------------------------------------------- DATABASE QUERY (UNREAD COUNT)----------------------------------
def get_unread_notification_count(user_id):
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id = ? AND is_read = 0
    """, (user_id,))

    count = cur.fetchone()[0]
    con.close()
    return count

#
@app.context_processor
def inject_notification_count():
    if "user_id" in session:
        return {
            "unread_notifications": get_unread_notification_count(session["user_id"])
        }
    return {"unread_notifications": 0}


### mark all as read----------------------------------------------------------------------------
@app.route("/notifications/read-all")
@login_required
def mark_all_notifications_read():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE user_id = ?
    """, (session["user_id"],))

    con.commit()
    con.close()
    return redirect(url_for("notifications"))


#======================================split========================================================

def get_group_balances(group_id):
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        SELECT 
            u.email,
            SUM(es.share) - 
            COALESCE(SUM(
                CASE 
                    WHEN ge.paid_by = u.id THEN ge.amount
                    ELSE 0
                END
            ), 0) AS balance
        FROM users u
        JOIN expense_splits es ON es.user_id = u.id
        JOIN group_expenses ge ON ge.id = es.expense_id
        WHERE ge.group_id = ?
        GROUP BY u.id
    """, (group_id,))

    balances = cur.fetchall()
    con.close()
    return balances




# -------------------- MAIN --------------------

if __name__ == "__main__":
    app.run(debug=True)
