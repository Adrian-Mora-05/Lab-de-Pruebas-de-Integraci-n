import statistics

import pytest

from conftest import BASE_URL, TIMEOUT

UMBRAL_MS = 1000
N_MUESTRAS = 10


def medir(api, url, params=None, n=N_MUESTRAS):
    """Devuelve la lista de tiempos en ms de n llamadas consecutivas."""
    tiempos = []
    for _ in range(n):
        r = api.get(url, params=params, timeout=TIMEOUT)
        assert r.status_code == 200
        tiempos.append(r.elapsed.total_seconds() * 1000)
    return tiempos


@pytest.mark.rendimiento
def test_tc17_tiempo_get_products(api):
    tiempos = medir(api, f"{BASE_URL}/products", {"active": "true", "limit": 10})
    promedio = statistics.mean(tiempos)
    # Se informa con -s para dejar evidencia; el criterio es el promedio, no una llamada aislada
    print(
        f"\nGET /products  n={len(tiempos)}  "
        f"min={min(tiempos):.0f}  prom={promedio:.0f}  max={max(tiempos):.0f} ms  "
        f"primera={tiempos[0]:.0f} ms"
    )
    assert promedio < UMBRAL_MS, f"Promedio {promedio:.0f} ms supera {UMBRAL_MS} ms"


UMBRAL_POST_MS = 2000  # definido tras la medición inicial; ver 6.3.5
N_POST = 5


def _precio_valido(api):
    r = api.get(f"{BASE_URL}/prices",
                params={"active": "true", "type": "one_time", "limit": 10}, timeout=TIMEOUT)
    for p in r.json()["data"]:
        if isinstance(p.get("unit_amount"), int) and p["unit_amount"] >= 100:
            return p
    pytest.fail("No hay un precio utilizable")


def _medir_post(api, url, data, n=N_POST):
    tiempos = []
    for _ in range(n):
        r = api.post(url, data=data, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        tiempos.append(r.elapsed.total_seconds() * 1000)
    return tiempos


@pytest.mark.rendimiento
def test_tc17_tiempo_post_checkout_sessions(api):
    precio = _precio_valido(api)
    data = {"mode": "payment", "line_items[0][price]": precio["id"],
            "line_items[0][quantity]": 2,
            "success_url": "https://example.com/exito",
            "cancel_url": "https://example.com/cancelar"}
    t = _medir_post(api, f"{BASE_URL}/checkout/sessions", data)
    prom = statistics.mean(t)
    print(f"\nPOST /checkout/sessions  n={len(t)}  min={min(t):.0f}  "
          f"prom={prom:.0f}  max={max(t):.0f} ms")
    assert prom < UMBRAL_POST_MS


@pytest.mark.rendimiento
def test_tc17_tiempo_post_payment_intents(api):
    data = {"amount": 1000, "currency": "usd", "payment_method": "pm_card_visa",
            "confirm": "true", "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
            "metadata[origen]": "qa_api_lab_tiempos"}
    t = _medir_post(api, f"{BASE_URL}/payment_intents", data)
    prom = statistics.mean(t)
    print(f"\nPOST /payment_intents  n={len(t)}  min={min(t):.0f}  "
          f"prom={prom:.0f}  max={max(t):.0f} ms")
    assert prom < UMBRAL_POST_MS