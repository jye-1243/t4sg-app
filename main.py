from flask import Flask, render_template, request, redirect, url_for, g, session
from tempfile import mkdtemp
from flask_session import Session
import sqlite3 as sql
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required

DATABASE = 'database.db'

# App configs
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

Session(app)


# Source code: https://flask.palletsprojects.com/en/1.1.x/patterns/sqlite3/
# Attach database
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sql.connect(DATABASE)
    return db

# Close connection
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Main gallery of all vaccines
@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor()
   
    # GET request used to search by name
    search = request.args.get("search")

    # Modify search_query based on if search exists
    sqlite_query = """SELECT DISTINCT v_id, status, loc1, loc2, type, user_id  FROM vaccines"""
    if search:

        # Search for vaccines
        sqlite_query = sqlite_query + """ WHERE loc1 LIKE ? OR loc2 LIKE ? OR type LIKE ? OR user_id IN (
                                          SELECT user_id FROM userinfo WHERE name LIKE ?)"""
        cursor.execute(sqlite_query, ("%" + search + "%", "%" + search + "%","%" + search + "%","%" + search + "%"))

    else:
        cursor.execute(sqlite_query)

    # Get database query results
    records = cursor.fetchall()

    # Pass database info into template
    for i in range(len(records)):
        user_id = records[i][5]
        user_query = """SELECT name FROM userinfo WHERE user_id=?"""
        cursor.execute(user_query,(user_id,))
        name = cursor.fetchall()[0]
        records[i] = records[i] + name

    return render_template("index.html", list=records)


# Personal page
@app.route("/my-vaccs")
@login_required
def owned():
    db = get_db()
    cursor = db.cursor()

    # GET request for search by filename
    search = request.args.get("search")

    # Get all posted info by user
    # Modifier for search query if there is search bar value
    sqlite_query = """SELECT DISTINCT v_id, status, loc1, loc2, type FROM vaccines WHERE user_id = ?"""
    if search:
        sqlite_query = sqlite_query + """ AND (loc1 LIKE ? OR loc2 LIKE ? OR type LIKE ?)"""
        cursor.execute(sqlite_query, (session["user_id"], "%" + search + "%", "%" + search + "%", "%" + search + "%"))
    else:
        cursor.execute(sqlite_query, (session["user_id"],))

    records = cursor.fetchall()

    # Find name
    user_query = """SELECT name FROM userinfo WHERE user_id=?"""
    cursor.execute(user_query,(session["user_id"],))
    user=cursor.fetchall()[0][0]

    return render_template("my-vaccs.html", list=records, user=user)


# Route to upload more distrubiton data
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    db = get_db()
    cursor = db.cursor()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Get all needed information if inputted
        loc1 = request.form.get("from")
        loc2 = request.form.get("to")
        type = request.form.get("type")
        quant = int(request.form.get("quant"))

        usernames = cursor.fetchall()
        # Ensure first location was submitted
        if not loc1:
            return render_template("add.html", msg="Must submit first location")

        # Ensure second location was submitted
        elif not loc2:
            return render_template("add.html", msg="Must submit second location")

        # Ensure vaccine type submitted
        elif not type:
            return render_template("add.html", msg="Must submit vaccine type")
        
        # Check quantity
        elif not quant:
            return render_template("add.html", msg="Must submit vaccine quantity")

        elif quant <= 0:
            return render_template("add.html", msg="Must submit positive quantity.")

        # Add data to database
        cursor.execute("""INSERT INTO vaccines(status, loc1, loc2, type, user_id) VALUES (?,?,?,?,?)""", (quant, loc1, loc2,type, session["user_id"]))
        db.commit()

        # Redirect user to home page
        return redirect("/")

    # GET request
    return render_template('add.html')

# Login route
@app.route('/login', methods=['GET','POST'])
def login():
    # Forget any user_id
    session.clear()

    db = get_db()
    cursor = db.cursor()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure email was submitted
        if not request.form.get("username"):
            return render_template("login.html", msg="Must submit email")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return render_template("login.html", msg="Must submit password")

        # Query database for email
        cursor.execute("""SELECT * FROM userinfo WHERE email = ?""", (request.form.get("username"),))
        rows = cursor.fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            return render_template("login.html", msg="Incorrect email or password")

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html", msg="")


## Logout route
@app.route("/logout")
@login_required
def logout():
    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


# Register route
@app.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    cursor = db.cursor()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Get all needed information if inputted
        name = request.form.get("name")
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirmation")
        cursor.execute("""SELECT email FROM userinfo""")

        usernames = cursor.fetchall()
        # Ensure username was submitted
        if not username:
            return render_template("register.html", msg="Must submit username")

        # Ensure password was submitted
        elif not password:
            return render_template("register.html", msg="Must submit password")

        # Ensure passwords match
        elif not password == confirm:
            return render_template("register.html", msg="Passwords do not match")

        # Check if email is duplicated
        for user in usernames:
            if username in user[0]:
                return render_template("register.html", msg="Email already exists. Please try another username.")

        # Add email, name and hash of password to database
        cursor.execute("""INSERT INTO userinfo(email, password, name) VALUES (?,?, ?)""", (username, generate_password_hash(password), name))
        db.commit()

        session.clear()
        cursor.execute("""SELECT user_id FROM userinfo WHERE email = ?""", (username,))
        id = cursor.fetchall()
        session["user_id"] = id[0][0]

        # Redirect user to home page
        return redirect("/")

    # GET request
    return render_template("register.html", msg="")

if __name__ == "__main__":
    app.run(debug=True)