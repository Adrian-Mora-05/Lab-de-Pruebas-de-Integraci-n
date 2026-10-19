import sqlite3

from conftest import BASE_URL, TIMEOUT


class ErrorDeNegocio(Exception):
    pass


class CantidadInvalida(ErrorDeNegocio):
    pass


class StockInsuficiente(ErrorDeNegocio):
    pass


class ProductoNoEncontrado(ErrorDeNegocio):
    pass


class PersistenciaError(ErrorDeNegocio):
    pass


class PagoRechazado(ErrorDeNegocio):
    pass


def validar_cantidad(cantidad):
    # type() y no isinstance(): True es un int en Python y no debe aceptarse
    if type(cantidad) is not int:
        raise CantidadInvalida(f"La cantidad debe ser un entero, llegó {cantidad!r}")
    if cantidad <= 0:
        raise CantidadInvalida(f"La cantidad debe ser mayor que cero, llegó {cantidad}")


def obtener_producto(api, product_id):
    """Consulta producto y precio en Stripe. El stock se convierte de str a int (H-01)."""
    r = api.get(f"{BASE_URL}/products/{product_id}", timeout=TIMEOUT)
    if r.status_code == 404:
        raise ProductoNoEncontrado(product_id)
    r.raise_for_status()
    p = r.json()

    rp = api.get(
        f"{BASE_URL}/prices",
        params={"product": product_id, "active": "true", "type": "one_time", "limit": 10},
        timeout=TIMEOUT,
    )
    rp.raise_for_status()
    precio = next((x for x in rp.json()["data"] if isinstance(x.get("unit_amount"), int)), None)
    if precio is None:
        raise ErrorDeNegocio(f"{product_id} no tiene precio fijo de pago único")

    try:
        stock = int(p["metadata"]["stock"])
    except (KeyError, ValueError) as e:
        raise ErrorDeNegocio(f"{product_id} no tiene un stock válido en metadata") from e

    return {
        "id": p["id"],
        "nombre": p["name"],
        "price_id": precio["id"],
        "precio": precio["unit_amount"],  # centavos
        "currency": precio["currency"],
        "stock": stock,
    }


def unidades_en_carrito(conn, producto_id):
    return conn.execute(
        "SELECT COALESCE(SUM(cantidad), 0) FROM carrito WHERE producto_id = ?", (producto_id,)
    ).fetchone()[0]


def validar_pedido(conn, producto, cantidad):
    validar_cantidad(cantidad)
    try:
        en_carrito = unidades_en_carrito(conn, producto["id"])
    except sqlite3.Error as e:
        raise PersistenciaError(str(e)) from e
    if en_carrito + cantidad > producto["stock"]:
        raise StockInsuficiente(
            f"{producto['nombre']}: stock {producto['stock']}, "
            f"en carrito {en_carrito}, pedido {cantidad}"
        )


def _insertar(conn, producto, cantidad):
    return conn.execute(
        "INSERT INTO carrito (producto_id, nombre, precio, cantidad, total) VALUES (?, ?, ?, ?, ?)",
        (producto["id"], producto["nombre"], producto["precio"], cantidad,
         producto["precio"] * cantidad),
    )


def agregar_al_carrito(conn, producto, cantidad):
    """Registra el producto en SQLite aplicando las reglas de negocio."""
    validar_pedido(conn, producto, cantidad)
    try:
        cur = _insertar(conn, producto, cantidad)
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise PersistenciaError(str(e)) from e
    return cur.lastrowid


def comprar(api, conn, producto, cantidad, payment_method="pm_card_visa"):
    """Orden: 1) registrar en BD sin confirmar, 2) cobrar, 3) confirmar la BD.
    Si falla la BD no se intenta el cobro; si falla el cobro se deshace el registro."""
    validar_pedido(conn, producto, cantidad)
    try:
        _insertar(conn, producto, cantidad)
    except sqlite3.Error as e:
        conn.rollback()
        raise PersistenciaError(str(e)) from e

    r = api.post(
        f"{BASE_URL}/payment_intents",
        data={
            "amount": producto["precio"] * cantidad,
            "currency": producto["currency"],
            "payment_method": payment_method,
            "confirm": "true",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
            "metadata[producto_id]": producto["id"],
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200 or r.json().get("status") != "succeeded":
        conn.rollback()
        raise PagoRechazado(r.text)
    conn.commit()
    return r.json()