import pytest

from conftest import BASE_URL, TIMEOUT
from tienda import (CantidadInvalida, PagoRechazado, PersistenciaError,
                    ProductoNoEncontrado, StockInsuficiente, agregar_al_carrito,
                    comprar, obtener_producto, unidades_en_carrito)


class ApiEspia:
    """Envuelve la sesión real y registra las llamadas, para saber si se intentó un cobro."""

    def __init__(self, api):
        self._api = api
        self.llamadas = []

    def get(self, url, **kw):
        self.llamadas.append(("GET", url))
        return self._api.get(url, **kw)

    def post(self, url, **kw):
        self.llamadas.append(("POST", url))
        return self._api.post(url, **kw)

    def pagos_intentados(self):
        return [c for c in self.llamadas if c[0] == "POST" and c[1].endswith("/payment_intents")]


@pytest.fixture(scope="module")
def producto(api):
    """Smartphone: el de menor stock (5), útil para probar el límite."""
    r = api.get(f"{BASE_URL}/products", params={"active": "true", "limit": 100}, timeout=TIMEOUT)
    assert r.status_code == 200
    por_nombre = {p["name"]: p for p in r.json()["data"]}
    assert "Smartphone" in por_nombre, "Falta el producto Smartphone en Stripe"
    prod = obtener_producto(api, por_nombre["Smartphone"]["id"])
    assert prod["stock"] >= 2, "Se necesita stock >= 2 para estas pruebas"
    return prod


def contar(conn):
    return conn.execute("SELECT COUNT(*) FROM carrito").fetchone()[0]


# ---------------------------------------------------------------- TC-15

@pytest.mark.persistencia
def test_tc15_insertar_producto_consultado(db_connection, producto):
    fila_id = agregar_al_carrito(db_connection, producto, 2)
    fila = db_connection.execute(
        "SELECT producto_id, nombre, precio, cantidad, total FROM carrito WHERE id = ?",
        (fila_id,),
    ).fetchone()
    assert contar(db_connection) == 1
    assert fila[0] == producto["id"]
    assert fila[1] == "Smartphone"
    assert fila[2] == producto["precio"]
    assert fila[3] == 2
    assert fila[4] == producto["precio"] * 2


@pytest.mark.persistencia
def test_tc15_tipos_persistidos(db_connection, producto):
    agregar_al_carrito(db_connection, producto, 1)
    fila = db_connection.execute(
        "SELECT producto_id, nombre, precio, cantidad, total FROM carrito"
    ).fetchone()
    assert type(fila[0]) is str and fila[0].startswith("prod_")
    assert type(fila[1]) is str
    assert type(fila[2]) is float  # columna REAL
    assert type(fila[3]) is int
    assert type(fila[4]) is float


@pytest.mark.persistencia
def test_tc15_total_en_bd_coincide_con_stripe(api, db_connection, producto):
    """Parte SQLite de 6.3.2: el total local debe ser igual al amount_total de Stripe."""
    cantidad = 2
    r = api.post(
        f"{BASE_URL}/checkout/sessions",
        data={
            "mode": "payment",
            "line_items[0][price]": producto["price_id"],
            "line_items[0][quantity]": cantidad,
            "success_url": "https://example.com/exito",
            "cancel_url": "https://example.com/cancelar",
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    agregar_al_carrito(db_connection, producto, cantidad)
    total_bd = db_connection.execute("SELECT total FROM carrito").fetchone()[0]
    assert total_bd == r.json()["amount_total"]
    assert total_bd == producto["precio"] * cantidad


# ----------------------------------------- Cantidades y stock (parte local)

@pytest.mark.negativa
@pytest.mark.persistencia
@pytest.mark.parametrize(
    "cantidad",
    [0, -1, "abc", 1.5, None, True],
    ids=["cero", "negativa", "texto", "decimal", "nulo", "booleano"],
)
def test_cantidad_invalida_no_se_guarda(db_connection, producto, cantidad):
    with pytest.raises(CantidadInvalida):
        agregar_al_carrito(db_connection, producto, cantidad)
    assert contar(db_connection) == 0


@pytest.mark.negativa
@pytest.mark.persistencia
def test_cantidad_sobre_el_stock_es_rechazada(db_connection, producto):
    with pytest.raises(StockInsuficiente):
        agregar_al_carrito(db_connection, producto, producto["stock"] + 1)
    assert contar(db_connection) == 0


@pytest.mark.persistencia
def test_cantidad_igual_al_stock_es_aceptada(db_connection, producto):
    agregar_al_carrito(db_connection, producto, producto["stock"])
    assert unidades_en_carrito(db_connection, producto["id"]) == producto["stock"]


@pytest.mark.negativa
@pytest.mark.persistencia
def test_stock_se_acumula_en_el_carrito(db_connection, producto):
    stock = producto["stock"]
    agregar_al_carrito(db_connection, producto, stock - 1)
    with pytest.raises(StockInsuficiente):
        agregar_al_carrito(db_connection, producto, 2)  # (stock-1) + 2 > stock
    agregar_al_carrito(db_connection, producto, 1)       # justo hasta el límite
    assert unidades_en_carrito(db_connection, producto["id"]) == stock
    assert contar(db_connection) == 2


@pytest.mark.negativa
@pytest.mark.persistencia
def test_producto_inexistente_no_se_registra(api, db_connection):
    with pytest.raises(ProductoNoEncontrado):
        obtener_producto(api, "prod_inexistente")
    assert contar(db_connection) == 0


# ---------------------------------------------------------------- TC-16

@pytest.mark.persistencia
def test_tc16_flujo_completo_sin_fallas(api, db_connection, producto):
    pago = comprar(api, db_connection, producto, 1)
    assert pago["status"] == "succeeded"
    assert contar(db_connection) == 1
    total_bd = db_connection.execute("SELECT total FROM carrito").fetchone()[0]
    assert total_bd == pago["amount_received"]


@pytest.mark.negativa
@pytest.mark.persistencia
def test_tc16_falla_de_bd_no_confirma_el_pago(api, db_connection, producto):
    espia = ApiEspia(api)
    db_connection.execute("DROP TABLE carrito")  # la API responde bien, la BD falla
    with pytest.raises(PersistenciaError):
        comprar(espia, db_connection, producto, 1)
    assert espia.pagos_intentados() == [], "Se cobró aunque la BD no pudo registrar el pedido"


@pytest.mark.negativa
@pytest.mark.persistencia
def test_tc16_pago_rechazado_no_deja_datos_huerfanos(api, db_connection, producto):
    with pytest.raises(PagoRechazado):
        comprar(api, db_connection, producto, 1, payment_method="pm_card_chargeDeclined")
    assert contar(db_connection) == 0, "Quedó un registro de un pago que no se cobró"