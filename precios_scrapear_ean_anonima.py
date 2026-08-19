"""
precios_scrapear_ean_anonima.py

Completa el codigo de barras (EAN) de productos de La Anonima en
productos_maestro, de a TANDAS chicas por corrida (no todo el
catalogo de una vez).

Por que en tandas y no todo junto: el EAN esta disponible en la
pagina de CADA producto individual (no en el listado de categoria,
que es liviano y es lo unico que se scrapea hoy). Investigado y
confirmado en la sesion del 19/8/2026 - ver bloque JSON-LD tipo
"Product" de una pagina de producto, campo "gtin". Pedir esa pagina
para ~4000 productos de una sola corrida es lento y arriesga que
CloudFront empiece a bloquear por volumen. En cambio, pidiendo un
puñado por dia (por defecto 250), en 2-3 semanas se completa todo el
catalogo actual sin sobresaltos, y de ahi en mas solo hay que pedir
el EAN de los productos NUEVOS que van apareciendo (pocos por dia).

Como retoma donde quedo: cada corrida le pide a la base
(precios_db.obtener_productos_sin_ean) los productos de La Anonima
que TODAVIA no tienen EAN guardado. Como guardar_ean() va marcando
cada uno a medida que se completa, la proxima corrida automaticamente
salta los que ya estan listos - no hace falta llevar un archivo de
progreso aparte.

HEADERS/COOKIES/sitio_permite_scrapear: son una copia exacta de los
de precios_armar_catalogo_anonima.py (mismo sitio, mismas reglas de
acceso). Se duplican aca en vez de importarlos porque cada script de
este proyecto es autosuficiente (mismo criterio que ya se usaba en
ese archivo).

Como correrlo (con un limite chico primero, para probar sin arriesgar
nada):
    python precios_scrapear_ean_anonima.py --limite 3

Corrida normal (tanda diaria completa):
    python precios_scrapear_ean_anonima.py

Pensado para sumarse a precios_corrida_diaria.sh o a un cron propio
mas adelante - por ahora se corre a mano hasta confirmar que anda
bien unos dias seguidos.
"""

import argparse
import json
import time

import requests
import urllib.robotparser
from bs4 import BeautifulSoup

import precios_db

# --- Constantes (copiadas de precios_armar_catalogo_anonima.py) --------

BASE_URL = "https://www.laanonima.com.ar"
LIMITE_POR_DEFECTO = 250

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

COOKIES = {
    "descripcionLocalidadCabezal": "Puerto Madryn",
    "Id-Sucursal-Super": "41",
    "Id-Sucursal-Super-DisponibleYa": "41",
    "idZonaPrecio": "8",
    "operadorLogistico": "AND",
    "provincia": "Neuquén",
    "provincia_id": "16",
    "seleccionocp": "1",
    "tipoEnvioUnificado": "3",
}

# Pausa entre pedidos a cada producto individual. Mas conservadora que
# la de armar_catalogo (2s) porque aca son muchos mas pedidos chicos
# seguidos (uno por producto, no uno por categoria).
SEGUNDOS_ENTRE_PEDIDOS = 2


# --- Robots.txt (copiado de precios_armar_catalogo_anonima.py) ---------

def sitio_permite_scrapear(url_objetivo: str) -> bool:
    """Ver docstring identico en precios_armar_catalogo_anonima.py."""
    try:
        respuesta = requests.get(BASE_URL + "/robots.txt", headers=HEADERS, timeout=10)
    except requests.RequestException:
        print("No se pudo conectar para chequear robots.txt. Por las dudas, no continuamos.")
        return False

    contenido = respuesta.text

    if "<html" in contenido.lower()[:300]:
        return True

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(contenido.splitlines())
    return parser.can_fetch(HEADERS["User-Agent"], url_objetivo)


# --- Extraccion del EAN de una pagina de producto -----------------------

def extraer_ean_de_producto(url: str) -> str | None:
    """
    Pide la pagina de UN producto individual y le saca el EAN del
    bloque JSON-LD tipo "Product" (distinto del bloque "ItemList" que
    usa el listado de categoria - ver investigacion 19/8/2026).

    Devuelve None si el sitio bloquea el pedido, no hay bloque
    "Product", o no tiene campo "gtin" - nunca rompe el flujo, solo
    informa por consola y el producto queda pendiente para la
    proxima corrida.
    """
    if not sitio_permite_scrapear(url):
        print(f"    robots.txt no permite leer: {url}")
        return None

    try:
        respuesta = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=10)
        respuesta.raise_for_status()
    except requests.RequestException as error:
        print(f"    No se pudo acceder: {error}")
        return None

    soup = BeautifulSoup(respuesta.text, "html.parser")

    for bloque in soup.find_all("script", type="application/ld+json"):
        if not bloque.string:
            continue
        try:
            datos = json.loads(bloque.string)
        except json.JSONDecodeError:
            continue

        if datos.get("@type") != "Product":
            continue

        gtin = datos.get("gtin") or datos.get("gtin13")
        if gtin:
            return str(gtin)

    return None


# --- Orquestacion ---------------------------------------------------------

def correr_tanda(limite: int) -> None:
    """
    Le pide a la base hasta `limite` productos de La Anonima sin EAN,
    y para cada uno intenta sacarle el EAN de su pagina individual.
    """
    productos = precios_db.obtener_productos_sin_ean("La Anonima", limite=limite)

    if not productos:
        print("No hay productos de La Anonima pendientes de EAN. Todo al dia.")
        return

    print(f"Tanda de hoy: {len(productos)} productos de La Anonima sin EAN.\n")

    encontrados = 0
    sin_url = 0
    no_encontrados = 0

    for indice, producto in enumerate(productos, start=1):
        codigo = producto["codigo_producto"]
        nombre = producto["nombre"]
        url = producto.get("url")

        print(f"[{indice}/{len(productos)}] {nombre}")

        if not url:
            print("    Sin URL guardada en historico_catalogo_completo - se salta.")
            sin_url += 1
            continue

        ean = extraer_ean_de_producto(url)

        if ean:
            precios_db.guardar_ean(codigo, ean)
            print(f"    EAN encontrado: {ean}")
            encontrados += 1
        else:
            print("    No se encontro EAN en esta pagina.")
            no_encontrados += 1

        if indice < len(productos):
            time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    print("\n--- Resumen de la tanda ---")
    print(f"  EAN encontrados y guardados: {encontrados}")
    print(f"  Sin EAN en la pagina:        {no_encontrados}")
    print(f"  Sin URL (no se pudo pedir):  {sin_url}")


def main():
    parser = argparse.ArgumentParser(
        description="Completa el EAN de productos de La Anonima, de a tandas."
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=LIMITE_POR_DEFECTO,
        help=f"Cantidad maxima de productos a procesar en esta corrida (default: {LIMITE_POR_DEFECTO}).",
    )
    args = parser.parse_args()

    correr_tanda(args.limite)


if __name__ == "__main__":
    main()
