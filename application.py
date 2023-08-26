import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
        SELECT symbol, SUM(shares) as allshares
        FROM transactions
        WHERE user_id = :user_id
        GROUP BY symbol
        HAVING SUM(shares) > 0;
    """, user_id=session["user_id"])
    share_holding = []
    totalvalue = 0
    for row in rows:
        stock = lookup(row["symbol"])
        share_holding.append({
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": row["allshares"],
            "price": usd(stock["price"]),
            "total": usd(stock["price"] * row["allshares"])
        })
        totalvalue += stock["price"] * row["allshares"]
    rows = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
    cash = rows[0]["cash"]
    totalvalue += cash

    return render_template("index.html", share_holding=share_holding, cash=usd(cash), totalvalue=usd(totalvalue))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        find_errors = is_provided("symbol") or is_provided("shares")
        if find_errors:
            return find_errors
        elif not request.form.get("shares").isdigit():
            return apology("invalid number of shares")
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol")
        rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        cash = rows[0]["cash"]

        current_cash = cash - shares*stock["price"]
        if current_cash < 0:
            return apology("Amount Insufficient")
        db.execute("UPDATE users SET cash=:current_cash WHERE id=:id",
                   current_cash=current_cash,
                   id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], stock["symbol"], shares, stock["price"])
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("""
    SELECT symbol, shares, price, transacted
    FROM transactions
    WHERE user_id=?
    """, session["user_id"])

    for i in range(len(transactions)):
        transactions[i]["price"] = usd(transactions[i]["price"])
    return render_template("history.html", transactions=transactions)


def is_provided(field):
    if not request.form.get(field):
        return apology(f"must provide {field}", 403)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        result_check = is_provided("symbol")
        if result_check is not None:
            return result_check
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol", 400)
        return render_template("quoted.html", stockname={
            'name': stock['name'],
            'symbol': stock['symbol'],
            'price': usd(stock['price'])

        })

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide confirmation password", 403)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Password not matching")
        try:
            primary_key = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                                     request.form.get("username"),
                                     generate_password_hash(request.form.get("password")))
        except:
            return apology("username already exists", 403)
        if primary_key is None:
            return apology("registration error", 403)
        session["user_id"] = primary_key
        flash("Registered!")
        # Redirect user to home page
        return redirect("/")
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        find_errors = is_provided("symbol") or is_provided("shares")
        if find_errors:
            return find_errors
        elif not request.form.get("shares").isdigit():
            return apology("invalid number of shares")
        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))
        stock = lookup(symbol)
        if stock is None:
            return apology("invalid symbol")

        rows = db.execute("""
            SELECT symbol, SUM(shares) as allshares
            FROM transactions
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING allshares > 0;
        """, user_id=session["user_id"])
        for row in rows:
            if row["symbol"] == symbol:
                if shares > row["allshares"]:
                    return apology("too many shares")

        rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        cash = rows[0]["cash"]

        current_cash = cash + shares * stock["price"]

        db.execute("UPDATE users SET cash=:current_cash WHERE id=:id",
                   current_cash=current_cash,
                   id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], stock["symbol"], -1 * shares, stock["price"])
        return redirect("/")

    else:
        rows = db.execute("""
            SELECT symbol
            FROM transactions
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING SUM(shares) > 0;
        """, user_id=session["user_id"])
        return render_template("sell.html", symbols=[row["symbol"] for row in rows])


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
