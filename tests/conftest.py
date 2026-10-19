import os
import sqlite3

import pytest
import requests

BASE_URL = "https://api.stripe.com/v1"
TIMEOUT = 10


@pytest.fixture(scope="session")
def api_key():
    """Lee la clave desde la variable de entorno; nunca va en el código."""
    key = os.environ.get("STRIPE_API_KEY", "")
    if not key.startswith(("sk_test_", "rk_test_")):
        pytest.exit(
            "Defina STRIPE_API_KEY con una clave de Test Mode (sk_test_... o rk_test_...). "
            "Las claves live no se permiten.",
            returncode=2,
        )
    return key


@pytest.fixture(scope="session")
def api(api_key):
    """Sesión HTTP autenticada contra Stripe."""
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_key}"})
    return session


@pytest.fixture
def db_connection():
    """SQLite en memoria: se crea y se destruye en cada prueba."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE carrito (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id TEXT NOT NULL,
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            cantidad INTEGER NOT NULL,
            total REAL NOT NULL
        )
        """
    )
    conn.commit()
    yield conn
    conn.close()