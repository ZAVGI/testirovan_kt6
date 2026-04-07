"""Сквозной интеграционный тест: API + БД + UI (Selenium).

Сценарий:
1) Через API очищаем БД.
2) Через UI регистрируем пользователя.
3) Через UI логинимся.
4) Через UI создаём заказ.

После каждого ключевого шага проверяем состояние БД прямыми SQL-запросами.
"""

import json
import socket
import sqlite3
import threading
from contextlib import closing
from urllib import request as urllib_request

import pytest

# Если в окружении нет нужных зависимостей, тест пропускается, а не падает на импорте.
pytest.importorskip("flask")
pytest.importorskip("selenium")
pytest.importorskip("werkzeug")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from werkzeug.serving import make_server

from app import app, init_db


@pytest.fixture(scope="session")
def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(free_port: int):
    init_db()
    server = make_server("127.0.0.1", free_port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{free_port}"

    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def db_connection():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    try:
        yield driver
    finally:
        driver.quit()


def test_user_register_login_and_create_order(live_server: str, driver, db_connection):
    email = "integration-user@example.com"
    password = "s3cret"

    # Шаг 1. Через API очищаем и переинициализируем БД.
    req = urllib_request.Request(
        f"{live_server}/api/test/reset",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["status"] == "ok"

    # SQL-проверка: после reset таблицы пустые.
    users_count = db_connection.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    orders_count = db_connection.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    assert users_count == 0
    assert orders_count == 0

    # Шаг 2. Регистрация пользователя через UI.
    driver.get(f"{live_server}/register")
    wait = WebDriverWait(driver, 10)
    wait.until(EC.visibility_of_element_located((By.ID, "email"))).send_keys(email)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.ID, "register-btn").click()

    # SQL-проверка после регистрации: пользователь создан.
    created_user = db_connection.execute(
        "SELECT id, email, last_login_at FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    assert created_user is not None
    assert created_user["email"] == email
    assert created_user["last_login_at"] is None

    # Шаг 3. Логин через UI.
    wait.until(EC.visibility_of_element_located((By.ID, "email"))).send_keys(email)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.ID, "login-btn").click()

    # SQL-проверка после логина: фиксируем факт логина в last_login_at.
    logged_user = db_connection.execute(
        "SELECT last_login_at FROM users WHERE id = ?",
        (created_user["id"],),
    ).fetchone()
    assert logged_user["last_login_at"] is not None

    # Шаг 4. Создание заказа через UI.
    wait.until(EC.visibility_of_element_located((By.ID, "item-name"))).send_keys("MacBook Pro")
    driver.find_element(By.ID, "create-order-btn").click()
    wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "Order created"))

    # SQL-проверка после создания заказа: есть запись о заказе пользователя.
    order = db_connection.execute(
        "SELECT user_id, item_name, status FROM orders WHERE user_id = ?",
        (created_user["id"],),
    ).fetchone()
    assert order is not None
    assert order["item_name"] == "MacBook Pro"
    assert order["status"] == "created"
