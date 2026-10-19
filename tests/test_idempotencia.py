import uuid

import pytest

from conftest import BASE_URL, TIMEOUT


def crear_pago(api, key=None, amount=1000):
    data = {
        "amount": amount,
        "currency": "usd",
        "payment_method": "pm_card_visa",
        "confirm": "true",
        "automatic_payment_methods[enabled]": "true",
        "automatic_payment_methods[allow_redirects]": "never",
        "metadata[origen]": "qa_api_lab_idempotencia",
    }
    headers = {"Idempotency-Key": key} if key else {}
    return api.post(f"{BASE_URL}/payment_intents", data=data, headers=headers, timeout=TIMEOUT)


def nueva_key():
    # Stripe recuerda las keys 24 h: una key fija repetiría la respuesta de ejecuciones anteriores
    return f"lab-{uuid.uuid4()}"


def test_tc14_misma_key_no_duplica(api):
    key = nueva_key()
    r1 = crear_pago(api, key)
    r2 = crear_pago(api, key)

    assert r1.status_code == r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"], "La misma key creó dos pagos distintos"
    assert r1.json()["amount"] == r2.json()["amount"]
    assert "Idempotent-Replayed" not in r1.headers
    assert r2.headers.get("Idempotent-Replayed") == "true"


def test_tc14_sin_key_genera_duplicados(api):
    r1 = crear_pago(api)
    r2 = crear_pago(api)

    assert r1.status_code == r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"], "Sin key se esperaba un pago nuevo en cada intento"
    assert "Idempotent-Replayed" not in r2.headers


@pytest.mark.negativa
def test_tc14_misma_key_con_otros_parametros_es_error(api):
    key = nueva_key()
    r1 = crear_pago(api, key, amount=1000)
    r2 = crear_pago(api, key, amount=2000)

    assert r1.status_code == 200
    assert r2.status_code == 400
    assert r2.json()["error"]["type"] == "idempotency_error"