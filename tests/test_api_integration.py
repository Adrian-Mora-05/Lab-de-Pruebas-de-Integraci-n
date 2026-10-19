import pytest

from conftest import BASE_URL, TIMEOUT

UMBRAL_MS = 1000  # criterio de la matriz para GET (TC-17)

# Contrato estricto del objeto Product: campo -> tipos exactos permitidos.
# Se compara con type() y no con isinstance(), porque en Python bool es
# subclase de int y isinstance(True, int) daría True (falso positivo).
CONTRATO_PRODUCTO = {
    "id": (str,),
    "object": (str,),
    "name": (str,),
    "active": (bool,),
    "created": (int,),
    "images": (list,),
    "metadata": (dict,),
    "livemode": (bool,),
    "description": (str, type(None)),
    "default_price": (str, type(None)),
}


@pytest.fixture(scope="module")
def respuesta_catalogo(api):
    """Una sola consulta al catálogo, compartida por las pruebas de este módulo."""
    return api.get(
        f"{BASE_URL}/products",
        params={"active": "true", "limit": 10},
        timeout=TIMEOUT,
    )


@pytest.fixture(scope="module")
def productos(respuesta_catalogo):
    return respuesta_catalogo.json().get("data", [])


# ---------------------------------------------------------------- TC-01

@pytest.mark.contrato
def test_tc01_status_tiempo_y_formato(respuesta_catalogo):
    assert respuesta_catalogo.status_code == 200
    assert "application/json" in respuesta_catalogo.headers["Content-Type"]
    assert "Request-Id" in respuesta_catalogo.headers
    ms = respuesta_catalogo.elapsed.total_seconds() * 1000
    assert ms < UMBRAL_MS, f"Respuesta lenta: {ms:.0f} ms (umbral {UMBRAL_MS} ms)"


@pytest.mark.contrato
def test_tc01_estructura_de_lista(respuesta_catalogo, productos):
    cuerpo = respuesta_catalogo.json()
    assert cuerpo["object"] == "list"
    assert cuerpo["url"] == "/v1/products"
    assert isinstance(cuerpo["has_more"], bool)
    assert isinstance(productos, list)
    assert len(productos) > 0, "El catálogo está vacío: cree productos en Stripe"


@pytest.mark.contrato
def test_tc01_filtro_active_se_respeta(productos):
    inactivos = [p["id"] for p in productos if p["active"] is not True]
    assert inactivos == [], f"Productos inactivos en un filtro active=true: {inactivos}"


@pytest.mark.contrato
def test_tc01_limit_se_respeta(api):
    response = api.get(f"{BASE_URL}/products", params={"limit": 3}, timeout=TIMEOUT)
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 3


# ----------------------------------------------- Contrato estricto (Product)

@pytest.mark.contrato
def test_contrato_estricto_producto(productos):
    assert len(productos) > 0, "Sin productos no hay contrato que validar"
    errores = []

    for p in productos:
        pid = p.get("id", "<sin id>")

        # 1. Campos presentes y con tipo exacto
        for campo, tipos in CONTRATO_PRODUCTO.items():
            if campo not in p:
                errores.append(f"{pid}: falta el campo '{campo}'")
            elif type(p[campo]) not in tipos:
                nombres = "/".join(t.__name__ for t in tipos)
                errores.append(
                    f"{pid}: '{campo}' es {type(p[campo]).__name__}, se esperaba {nombres}"
                )

        # 2. Reglas de valor
        if not str(p.get("id", "")).startswith("prod_"):
            errores.append(f"{pid}: el id no tiene prefijo prod_")
        if p.get("object") != "product":
            errores.append(f"{pid}: object distinto de 'product'")
        if p.get("livemode") is not False:
            errores.append(f"{pid}: livemode debe ser False en Test Mode")
        if isinstance(p.get("name"), str) and not p["name"].strip():
            errores.append(f"{pid}: name vacío")
        if isinstance(p.get("images"), list):
            for url in p["images"]:
                if not (isinstance(url, str) and url.startswith("http")):
                    errores.append(f"{pid}: images contiene un valor que no es URL: {url!r}")

    assert not errores, "Violaciones de contrato:\n- " + "\n- ".join(errores)

# ------------------------------------------ Metadata: category y stock

CATALOGO_ESPERADO = {
    "Earphones": ("audio", "25"),
    "Smartwatch": ("wearables", "20"),
    "Laptop": ("tech", "15"),
    "Tablet": ("tech", "10"),
    "Smartphone": ("tech", "5"),
}


@pytest.fixture(scope="module")
def productos_por_nombre(api):
    r = api.get(f"{BASE_URL}/products", params={"active": "true", "limit": 100}, timeout=TIMEOUT)
    assert r.status_code == 200
    return {p["name"]: p for p in r.json()["data"]}


@pytest.mark.contrato
def test_catalogo_esperado_presente(productos_por_nombre):
    faltantes = [n for n in CATALOGO_ESPERADO if n not in productos_por_nombre]
    assert not faltantes, f"Faltan productos en el catálogo: {faltantes}"


@pytest.mark.contrato
def test_metadata_category_y_stock(productos_por_nombre):
    errores = []
    for nombre, (categoria, stock) in CATALOGO_ESPERADO.items():
        meta = productos_por_nombre.get(nombre, {}).get("metadata", {})
        if meta.get("category") != categoria:
            errores.append(f"{nombre}: category={meta.get('category')!r}, esperada {categoria!r}")
        if meta.get("stock") != stock:
            errores.append(f"{nombre}: stock={meta.get('stock')!r}, esperado {stock!r}")
    assert not errores, "Metadata incorrecta:\n- " + "\n- ".join(errores)


@pytest.mark.contrato
def test_metadata_stock_llega_como_string(productos_por_nombre):
    for nombre in CATALOGO_ESPERADO:
        stock = productos_por_nombre[nombre]["metadata"]["stock"]
        assert type(stock) is str, f"{nombre}: stock es {type(stock).__name__}"
        assert stock.isdigit() and int(stock) > 0, f"{nombre}: stock no convertible a entero"