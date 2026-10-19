import sqlite3

import pytest

COLUMNAS_ESPERADAS = ["id", "producto_id", "nombre", "precio", "cantidad", "total"]


def insertar(conn, producto_id="prod_test", nombre="Producto de prueba",
             precio=1500, cantidad=2, total=3000):
    """Inserta un registro en carrito y devuelve el id generado."""
    cursor = conn.execute(
        "INSERT INTO carrito (producto_id, nombre, precio, cantidad, total) "
        "VALUES (?, ?, ?, ?, ?)",
        (producto_id, nombre, precio, cantidad, total),
    )
    conn.commit()
    return cursor.lastrowid


@pytest.mark.persistencia
def test_tabla_carrito_existe(db_connection):
    fila = db_connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='carrito'"
    ).fetchone()
    assert fila is not None
    assert fila[0] == "carrito"


@pytest.mark.persistencia
def test_esquema_de_la_tabla(db_connection):
    columnas = db_connection.execute("PRAGMA table_info(carrito)").fetchall()
    nombres = [c[1] for c in columnas]
    assert nombres == COLUMNAS_ESPERADAS

    tipos = {c[1]: c[2] for c in columnas}
    assert tipos["producto_id"] == "TEXT"
    assert tipos["cantidad"] == "INTEGER"
    assert tipos["precio"] == "REAL"
    assert tipos["total"] == "REAL"


@pytest.mark.persistencia
def test_insertar_y_leer_registro(db_connection):
    nuevo_id = insertar(db_connection)

    fila = db_connection.execute(
        "SELECT producto_id, nombre, precio, cantidad, total FROM carrito WHERE id = ?",
        (nuevo_id,),
    ).fetchone()

    assert fila == ("prod_test", "Producto de prueba", 1500, 2, 3000)
    total_registros = db_connection.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]
    assert total_registros == 1


@pytest.mark.persistencia
def test_id_autoincremental(db_connection):
    id1 = insertar(db_connection)
    id2 = insertar(db_connection)
    assert id1 == 1
    assert id2 == 2


@pytest.mark.persistencia
@pytest.mark.negativa
@pytest.mark.parametrize("columna_nula", ["producto_id", "nombre", "precio", "cantidad", "total"])
def test_columnas_not_null_rechazan_nulos(db_connection, columna_nula):
    valores = {"producto_id": "prod_x", "nombre": "X", "precio": 100,
               "cantidad": 1, "total": 100}
    valores[columna_nula] = None

    with pytest.raises(sqlite3.IntegrityError):
        db_connection.execute(
            "INSERT INTO carrito (producto_id, nombre, precio, cantidad, total) "
            "VALUES (:producto_id, :nombre, :precio, :cantidad, :total)",
            valores,
        )


# --- Aislamiento: estas dos pruebas hacen exactamente lo mismo. ---
# Si la base se compartiera entre pruebas, la segunda vería el registro de la primera.

@pytest.mark.persistencia
def test_aislamiento_a(db_connection):
    antes = db_connection.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]
    assert antes == 0
    insertar(db_connection)
    despues = db_connection.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]
    assert despues == 1


@pytest.mark.persistencia
def test_aislamiento_b(db_connection):
    antes = db_connection.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]
    assert antes == 0, "La BD no se reinició: la prueba anterior dejó datos"
    insertar(db_connection)
    despues = db_connection.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]
    assert despues == 1