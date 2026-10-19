import pytest

from conftest import BASE_URL, TIMEOUT

CANTIDAD = 2
URL_EXITO = "https://example.com/exito"
URL_CANCELAR = "https://example.com/cancelar"


# ------------------------------------------------------------ Fixtures del flujo
# Cada fixture alimenta a la siguiente (scope="module"), igual que las
# variables de ambiente encadenan los requests en Postman.

@pytest.fixture(scope="module")
def catalogo_precio(api):
    """TC-01 -> TC-02: toma el primer producto activo con precio fijo de pago único."""
    r = api.get(f"{BASE_URL}/products", params={"active": "true", "limit": 10}, timeout=TIMEOUT)
    assert r.status_code == 200
    for producto in r.json()["data"]:
        rp = api.get(
            f"{BASE_URL}/prices",
            params={"product": producto["id"], "active": "true", "type": "one_time", "limit": 10},
            timeout=TIMEOUT,
        )
        assert rp.status_code == 200
        for precio in rp.json()["data"]:
            if isinstance(precio.get("unit_amount"), int):
                return {"producto": producto, "precio": precio, "respuesta": rp}
    pytest.fail("Ningún producto activo tiene un precio fijo de pago único. Cree uno en Stripe.")


@pytest.fixture(scope="module")
def carrito(api, catalogo_precio):
    """TC-03: crea el carrito (Checkout Session) con el precio y la cantidad."""
    data = {
        "mode": "payment",
        "line_items[0][price]": catalogo_precio["precio"]["id"],
        "line_items[0][quantity]": CANTIDAD,
        "success_url": URL_EXITO,
        "cancel_url": URL_CANCELAR,
    }
    return api.post(f"{BASE_URL}/checkout/sessions", data=data, timeout=TIMEOUT)


@pytest.fixture(scope="module")
def total_esperado(catalogo_precio):
    """Cálculo independiente de la API: cantidad x unit_amount (en centavos)."""
    return CANTIDAD * catalogo_precio["precio"]["unit_amount"]


@pytest.fixture(scope="module")
def pago(api, catalogo_precio, carrito, total_esperado):
    """TC-06: pago simulado por el total esperado, con tarjeta de prueba."""
    data = {
        "amount": total_esperado,
        "currency": catalogo_precio["precio"]["currency"],
        "payment_method": "pm_card_visa",
        "confirm": "true",
        "automatic_payment_methods[enabled]": "true",
        "automatic_payment_methods[allow_redirects]": "never",
        "metadata[origen]": "qa_api_lab",
        "metadata[cart_id]": carrito.json()["id"],
    }
    return api.post(f"{BASE_URL}/payment_intents", data=data, timeout=TIMEOUT)


# ---------------------------------------------------------------- TC-02

@pytest.mark.contrato
def test_tc02_respuesta_de_precios(catalogo_precio):
    r = catalogo_precio["respuesta"]
    cuerpo = r.json()
    assert r.status_code == 200
    assert cuerpo["object"] == "list"
    assert len(cuerpo["data"]) > 0
    assert catalogo_precio["precio"]["product"] == catalogo_precio["producto"]["id"]


@pytest.mark.contrato
def test_tc02_contrato_estricto_precio(catalogo_precio):
    p = catalogo_precio["precio"]
    errores = []
    esperados = {"id": str, "object": str, "currency": str, "type": str,
                 "unit_amount": int, "active": bool, "livemode": bool, "product": str}
    for campo, tipo in esperados.items():
        if campo not in p:
            errores.append(f"falta '{campo}'")
        elif type(p[campo]) is not tipo:
            errores.append(f"'{campo}' es {type(p[campo]).__name__}, se esperaba {tipo.__name__}")
    if not str(p.get("id", "")).startswith("price_"):
        errores.append("id sin prefijo price_")
    if p.get("object") != "price":
        errores.append("object distinto de 'price'")
    if not (isinstance(p.get("unit_amount"), int) and p["unit_amount"] > 0):
        errores.append("unit_amount debe ser entero > 0")
    if not (isinstance(p.get("currency"), str) and len(p["currency"]) == 3 and p["currency"].islower()):
        errores.append("currency debe ser código ISO de 3 letras en minúscula")
    if p.get("livemode") is not False:
        errores.append("livemode debe ser False")
    assert not errores, "Violaciones de contrato:\n- " + "\n- ".join(errores)


# ---------------------------------------------------------------- TC-03

def test_tc03_creacion_de_carrito(carrito, catalogo_precio):
    cuerpo = carrito.json()
    assert carrito.status_code == 200, cuerpo
    assert cuerpo["id"].startswith("cs_test_")
    assert cuerpo["status"] == "open"
    assert cuerpo["payment_status"] == "unpaid"
    assert cuerpo["mode"] == "payment"
    assert cuerpo["currency"] == catalogo_precio["precio"]["currency"]


@pytest.mark.contrato
def test_tc03_contrato_sesion(carrito):
    c = carrito.json()
    assert type(c["id"]) is str
    assert type(c["amount_total"]) is int
    assert type(c["livemode"]) is bool and c["livemode"] is False
    assert type(c["url"]) is str and c["url"].startswith("https://")


# ---------------------------------------------------------------- TC-04

@pytest.mark.contrato
def test_tc04_consulta_de_carrito(api, carrito):
    cart_id = carrito.json()["id"]
    r = api.get(f"{BASE_URL}/checkout/sessions/{cart_id}", timeout=TIMEOUT)
    s = r.json()
    assert r.status_code == 200
    assert s["id"] == cart_id
    assert s["status"] == "open"
    assert s["mode"] == "payment"
    assert type(s["amount_total"]) is int
    assert s["amount_total"] == carrito.json()["amount_total"]  # persistió igual


# ---------------------------------------------------------------- TC-05

def test_tc05_lineas_cantidad_y_total(api, carrito, catalogo_precio, total_esperado):
    cart_id = carrito.json()["id"]
    r = api.get(f"{BASE_URL}/checkout/sessions/{cart_id}/line_items", timeout=TIMEOUT)
    cuerpo = r.json()
    assert r.status_code == 200
    assert cuerpo["object"] == "list"
    assert len(cuerpo["data"]) == 1

    linea = cuerpo["data"][0]
    assert linea["quantity"] == CANTIDAD
    assert linea["price"]["id"] == catalogo_precio["precio"]["id"]
    assert linea["amount_total"] == total_esperado, (
        f"Total de la API {linea['amount_total']} != esperado {total_esperado}"
    )


def test_tc05_total_linea_coincide_con_sesion(api, carrito, total_esperado):
    cart_id = carrito.json()["id"]
    r = api.get(f"{BASE_URL}/checkout/sessions/{cart_id}/line_items", timeout=TIMEOUT)
    linea = r.json()["data"][0]
    assert linea["amount_total"] == carrito.json()["amount_total"] == total_esperado


# ---------------------------------------------------------------- TC-06

def test_tc06_pago_exitoso(pago, total_esperado, catalogo_precio):
    cuerpo = pago.json()
    assert pago.status_code == 200, cuerpo
    assert cuerpo["status"] == "succeeded"
    assert cuerpo["amount"] == total_esperado
    assert cuerpo["amount_received"] == total_esperado
    assert cuerpo["currency"] == catalogo_precio["precio"]["currency"]


@pytest.mark.contrato
def test_tc06_contrato_payment_intent(pago):
    c = pago.json()
    assert c["id"].startswith("pi_")
    assert c["object"] == "payment_intent"
    assert type(c["amount"]) is int
    assert c["livemode"] is False
    assert c["metadata"]["origen"] == "qa_api_lab"