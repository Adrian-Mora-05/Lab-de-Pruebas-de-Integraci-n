from conftest import BASE_URL, TIMEOUT

def test_conexion_stripe(api):
    """Prueba de conexión a la API de Stripe."""
    response = api.get(f"{BASE_URL}/products", params={"limit": 1}, timeout=TIMEOUT)
    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert "data" in response.json()

def test_db_en_memoria_vacia(db_connection):
    """Prueba que la base de datos en memoria esté vacía al inicio."""
    count = db_connection.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]
    assert count == 0