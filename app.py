import os
import sqlite3
from pathlib import Path

from flask import Flask, redirect, render_template_string, request, session, url_for, jsonify

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "app.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "test-secret")
app.config["DATABASE"] = str(DB_PATH)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )


@app.post("/api/test/reset")
def api_reset_db():
    with get_connection() as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS orders;
            DROP TABLE IF EXISTS users;
            """
        )
    init_db()
    return jsonify({"status": "ok"})


@app.get("/register")
def register_form():
    return render_template_string(
        """
        <h1>Регистрация</h1>
        <form method="post" action="/register">
            <input id="email" name="email" type="email" required />
            <input id="password" name="password" type="password" required />
            <button id="register-btn" type="submit">Создать аккаунт</button>
        </form>
        """
    )


@app.post("/register")
def register_submit():
    email = request.form["email"]
    password = request.form["password"]

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            (email, password),
        )

    return redirect(url_for("login_form"))


@app.get("/login")
def login_form():
    return render_template_string(
        """
        <h1>Логин</h1>
        <form method="post" action="/login">
            <input id="email" name="email" type="email" required />
            <input id="password" name="password" type="password" required />
            <button id="login-btn" type="submit">Войти</button>
        </form>
        """
    )


@app.post("/login")
def login_submit():
    email = request.form["email"]
    password = request.form["password"]

    with get_connection() as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE email = ? AND password = ?",
            (email, password),
        ).fetchone()
        if user is None:
            return "Unauthorized", 401

        conn.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],),
        )

    session["user_id"] = user["id"]
    return redirect(url_for("new_order_form"))


@app.get("/orders/new")
def new_order_form():
    if "user_id" not in session:
        return redirect(url_for("login_form"))

    return render_template_string(
        """
        <h1>Создание заказа</h1>
        <form method="post" action="/orders/new">
            <input id="item-name" name="item_name" required />
            <button id="create-order-btn" type="submit">Создать заказ</button>
        </form>
        """
    )


@app.post("/orders/new")
def new_order_submit():
    if "user_id" not in session:
        return redirect(url_for("login_form"))

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO orders (user_id, item_name, status) VALUES (?, ?, ?)",
            (session["user_id"], request.form["item_name"], "created"),
        )

    return "Order created"


if __name__ == "__main__":
    init_db()
    app.run(port=5001)
