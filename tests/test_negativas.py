import pytest
import requests

from conftest import BASE_URL, TIMEOUT

URL_EXITO = "https://example.com/exito"
URL_CANCELAR = "https://example.com/cancelar"


# ------------------------------------------------------------------ Helpers

@pytest.fixture(scope="module")
def price_id(api):
    """Un precio válido (pago único, monto fijo) para armar los requests."""
    r = api.get(
        f"{BASE_URL}/prices",
        params={"active": "true", "type": "one_time", "limit": 10},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200
    for p in r.json()["data"]:
        if isinstance(p.get("unit_amount"), int) and p["unit_amount"] >= 100:
            return p["id"]
    pytest.fail("No hay un precio de pago único utilizable. Cree productos en Stripe.")


def datos_sesion(price_id, quantity):
    return {
        "mode": "payment",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": quantity,
        "success_url": URL_EXITO,
        "cancel_url": URL_CANCELAR,
    }


def ultima_sesion(api):
    """Id de la sesión más reciente (Stripe lista de la más nueva a la más vieja)."""
    r = api.get(f"{BASE_URL}/checkout/sessions", params={"limit": 1}, timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()["data"]
    return data[0]["id"] if data else None


# ---------------------------------------------------------------- TC-07

def datos_pago(payment_method):
    return {
        "amount": 1000,
        "currency": "usd",
        "payment_method": payment_method,
        "confirm": "true",
        "automatic_payment_methods[enabled]": "true",
        "automatic_payment_methods[allow_redirects]": "never",
    }


@pytest.mark.negativa
def test_tc07_pago_rechazado(api):
    r = api.post(f"{BASE_URL}/payment_intents",
                 data=datos_pago("pm_card_chargeDeclined"), timeout=TIMEOUT)
    error = r.json()["error"]
    assert r.status_code == 402
    assert error["type"] == "card_error"
    assert error["code"] == "card_declined"
    assert isinstance(error["message"], str) and error["message"].strip()


@pytest.mark.negativa
def test_tc07_pago_rechazado_no_queda_cobrado(api):
    r = api.post(f"{BASE_URL}/payment_intents",
                 data=datos_pago("pm_card_chargeDeclined"), timeout=TIMEOUT)
    error = r.json()["error"]
    assert error.get("decline_code"), "Se esperaba un decline_code"
    # El PaymentIntent asociado no debe quedar como pagado
    assert error["payment_intent"]["status"] != "succeeded"
    assert error["payment_intent"].get("amount_received", 0) == 0


# ---------------------------------------------------------------- TC-08

@pytest.mark.negativa
def test_tc08_producto_inexistente(api):
    r = api.get(f"{BASE_URL}/products/prod_inexistente", timeout=TIMEOUT)
    error = r.json()["error"]
    assert r.status_code == 404
    assert error["type"] == "invalid_request_error"
    assert error["code"] == "resource_missing"
    assert "prod_inexistente" in error["message"]
    assert "application/json" in r.headers["Content-Type"]


# ------------------------------------------- TC-09, TC-10, TC-12 (cantidad)

@pytest.mark.negativa
@pytest.mark.parametrize(
    "cantidad",
    [
        pytest.param("0", id="tc09_cero"),
        pytest.param("-1", id="tc10_negativa"),
        pytest.param("abc", id="tc12_tipo_incorrecto"),
    ],
)
def test_cantidad_invalida_es_rechazada(api, price_id, cantidad):
    antes = ultima_sesion(api)
    r = api.post(f"{BASE_URL}/checkout/sessions",
                 data=datos_sesion(price_id, cantidad), timeout=TIMEOUT)
    cuerpo = r.json()
    print(f"\nquantity={cantidad!r} -> {r.status_code} | {cuerpo.get('error', {}).get('message')}")

    assert 400 <= r.status_code < 500
    assert r.status_code == 400
    assert cuerpo["error"]["type"] == "invalid_request_error"
    assert cuerpo["error"]["message"].strip()
    assert "id" not in cuerpo, "Se creó una sesión con una cantidad inválida"
    assert ultima_sesion(api) == antes, "Apareció una sesión nueva en la cuenta"


# ---------------------------------------------------------------- TC-11

def datos_sin_items():
    return {"mode": "payment", "success_url": URL_EXITO, "cancel_url": URL_CANCELAR}


@pytest.mark.negativa
def test_tc11_body_incompleto_es_rechazado(api):
    r = api.post(f"{BASE_URL}/checkout/sessions", data=datos_sin_items(), timeout=TIMEOUT)
    cuerpo = r.json()
    print(f"\nTC-11 -> {r.status_code} | {cuerpo.get('error')}")
    assert r.status_code == 400
    assert cuerpo["error"]["type"] == "invalid_request_error"
    assert cuerpo["error"]["message"].strip()
    assert "id" not in cuerpo


@pytest.mark.negativa
def test_tc11_error_indica_parametro_faltante(api):
    r = api.post(f"{BASE_URL}/checkout/sessions", data=datos_sin_items(), timeout=TIMEOUT)
    error = r.json()["error"]
    assert "line_items" in error["message"]
    assert "required" in error["message"]
    assert error.get("code") is None, "Si Stripe agregó 'code', actualice D-02"


# ---------------------------------------------------------------- TC-13

@pytest.mark.negativa
def test_tc13_sin_token(api):
    # requests.get directo, sin la sesión autenticada
    r = requests.get(f"{BASE_URL}/products", timeout=TIMEOUT)
    error = r.json()["error"]
    assert r.status_code == 401
    assert error["type"] == "invalid_request_error"
    assert "API key" in error["message"]


@pytest.mark.negativa
def test_tc13_token_invalido(api):
    r = requests.get(
        f"{BASE_URL}/products",
        headers={"Authorization": "Bearer sk_test_clave_invalida_de_prueba"},
        timeout=TIMEOUT,
    )
    error = r.json()["error"]
    assert r.status_code == 401
    assert error["type"] == "invalid_request_error"
    assert "Invalid API Key" in error["message"]