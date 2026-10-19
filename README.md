# QA API Lab: pruebas de integración con Pytest y SQLite

Pruebas de integración sobre la API de Stripe en **Test Mode**, con persistencia
simulada en SQLite en memoria.

## Requisitos
- Python 3.12 o superior
- Una cuenta de Stripe en modo de pruebas y su clave secreta (`sk_test_...` o `rk_test_...`)
- Productos de prueba creados en Stripe: Earphones, Smartwatch, Laptop, Tablet y
  Smartphone, cada uno con precio de pago único, `metadata[stock]` y `metadata[category]`

## Instalación
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
source .venv/bin/activate         # Mac/Linux
python -m pip install -r requirements.txt
```

## Clave de API
La clave se lee de la variable de entorno `STRIPE_API_KEY`. Nunca se escribe en el código.
```powershell
$env:STRIPE_API_KEY = "sk_test_..."     # Windows PowerShell
export STRIPE_API_KEY="sk_test_..."     # Mac/Linux
```
Las claves `sk_live_` son rechazadas por las pruebas.

## Ejecución
```bash
python -m pytest                                    # toda la suite
python -m pytest tests/test_negativas.py -s         # un archivo, mostrando los print
python -m pytest -m negativa                        # por marcador
python -m pytest --html=report.html --self-contained-html   # reporte HTML
```
Ejecutar siempre desde la raíz `qa_api_lab/`.

## Estructura
| Archivo | Contenido |
|---|---|
| `tests/conftest.py` | Fixtures: clave, sesión HTTP, SQLite en memoria |
| `tests/tienda.py` | Lógica de la tienda simulada (reglas de cantidad y stock, compra) |
| `tests/test_00_smoke.py` | Verificación de conexión |
| `tests/test_db_sqlite.py` | Base de datos en memoria y aislamiento |
| `tests/test_api_integration.py` | Catálogo, contrato de Product, metadata |
| `tests/test_flujo_compra.py` | Precio, carrito, total y pago |
| `tests/test_negativas.py` | Errores, cantidades inválidas, autenticación |
| `tests/test_idempotencia.py` | Idempotencia de pagos |
| `tests/test_persistencia.py` | SQLite, stock local y falla parcial |
| `tests/test_tiempos.py` | Tiempos de respuesta de GET y POST |

## Notas
- Cada ejecución crea objetos en la cuenta de pruebas de Stripe (sesiones y pagos).
- `TC-01` (tiempo) puede fallar si se ejecuta solo `test_api_integration.py`,
  porque la primera llamada de la sesión incluye el costo de abrir la conexión.
- Los resultados esperados de errores provienen de Stripe y fueron confirmados al ejecutar.