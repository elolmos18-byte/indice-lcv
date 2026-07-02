"""
precios_armar_catalogo_anonima.py

Lee una LISTA de categorias de La Anonima y junta todo en un solo
archivo CSV - el catalogo de productos de La Anonima que despues se
usa como insumo para armar la canasta CCV-37.

Por que un archivo de texto separado para las URLs (categorias.txt) y
no una lista fija adentro del codigo:
- Las categorias que nos interesan van a cambiar a medida que decidamos
  que productos comparar. Es mas facil agregar o sacar una linea de un
  archivo de texto que editar el codigo cada vez.
- Las URLs se consiguen navegando el sitio (las copia de la barra de
  direcciones), no hace falta que Claude las adivine.

Que hace, paso por paso:
1. Lee categorias.txt - una URL por linea, las que empiezan con # se
   ignoran.
2. Para cada URL: chequea el robots.txt, pide la pagina con headers
   de navegador, y extrae los productos del bloque JSON-LD que el
   sitio publica para Google.
3. Junta todo en catalogo_anonima.csv, con columnas:
   categoria, nombre, precio, url.

Por que JSON-LD y no clases CSS: el sitio puede cambiar el diseno de
las tarjetas de producto en cualquier momento sin avisar, pero el
JSON-LD lo necesitan estable porque lo usa Google para mostrar
precios en los resultados de busqueda - es mucho menos probable que
rompan ese formato de un dia para el otro.

Por que el archivo es autosuficiente (incluye la funcion de
obtener_productos_de_categoria en vez de importarla): esto vive en
la carpeta del proyecto Indice LCV, separado del cuaderno de
investigacion inicial. No depende de archivos sueltos afuera.

Como correrlo:
    pip install requests beautifulsoup4
    python precios_armar_catalogo_anonima.py categorias.txt
"""

import csv
import json
import sys
import time
import urllib.robotparser
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --- Constantes ---------------------------------------------------------

BASE_URL = "https://www.laanonima.com.ar"
ARCHIVO_SALIDA = "catalogo_anonima.csv"

# Headers que imitan un navegador real. El sitio rechaza con 403 los
# pedidos que no tienen estos headers basicos.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

# Cookies de sucursal. Sin esto, La Anonima devuelve el catalogo de
# una sucursal por defecto que no es Puerto Madryn - confirmado con
# diagnostico_cookie_sucursal.py: sin estas cookies, "Fideos Spaguetti
# Pastasole" (y otros productos) no aparecen en el listado, aunque
# existen en el catalogo real de la sucursal de Puerto Madryn.
# Sacado del panel de cookies del navegador (DevTools -> Application
# -> Storage -> Cookies -> laanonima.com.ar) con la sucursal "Puerto
# Madryn (9120)" fijada. Se usa el set completo en vez de aislar la
# minima necesaria, para replicar exactamente el estado de un
# navegador real en vez de adivinar cual cookie sola alcanza.
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

# Pausa entre pedidos a cada categoria. No es por miedo a que nos
# bloqueen - es simplemente buena practica no golpear un servidor
# ajeno con pedidos uno detras de otro sin pausa.
SEGUNDOS_ENTRE_PEDIDOS = 2


# --- Lectura del robots.txt ---------------------------------------------

def sitio_permite_scrapear(url_objetivo: str) -> bool:
    """
    Chequea el robots.txt del sitio antes de pedir nada.

    Usamos requests con los mismos headers de navegador que el resto
    del script para pedir el robots.txt, en vez de dejar que
    RobotFileParser lo pida solo - si lo dejamos solo, usa un
    User-Agent generico de Python que el sitio bloquea con un 403.
    """
    try:
        respuesta = requests.get(BASE_URL + "/robots.txt", headers=HEADERS, timeout=10)
    except requests.RequestException:
        print("No se pudo conectar para chequear robots.txt. Por las dudas, no continuamos.")
        return False

    contenido = respuesta.text

    # Si el sitio devuelve la home (HTML completo) para cualquier ruta
    # que no reconoce, en vez de un robots.txt real, no hay reglas
    # explicitas que prohiban nada - interpretamos que esta permitido.
    if "<html" in contenido.lower()[:300]:
        return True

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(contenido.splitlines())
    return parser.can_fetch(HEADERS["User-Agent"], url_objetivo)


# --- Lectura de una pagina de categoria ---------------------------------

def obtener_productos_de_categoria(url: str) -> list[dict]:
    """
    Pide una pagina de categoria y devuelve los productos listados en
    su bloque JSON-LD (nombre, precio y URL del producto).

    Devuelve lista vacia si el sitio bloquea el pedido, no permite el
    scraping, o la pagina no tiene un bloque ItemList - nunca rompe el
    flujo, solo informa por consola.
    """
    if not sitio_permite_scrapear(url):
        print(f"  robots.txt no permite scrapear: {url}")
        return []

    try:
        respuesta = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=10)
        respuesta.raise_for_status()
    except requests.RequestException as error:
        print(f"  No se pudo acceder: {error}")
        return []

    return _extraer_productos_json_ld(respuesta.text)


def _extraer_productos_json_ld(html: str) -> list[dict]:
    """
    Busca todos los bloques <script type="application/ld+json"> del
    HTML y se queda con el que tiene "@type": "ItemList" - ese es el
    que el sitio usa para listar productos con nombre, precio y url.
    """
    soup = BeautifulSoup(html, "html.parser")
    productos = []

    for bloque in soup.find_all("script", type="application/ld+json"):
        if not bloque.string:
            continue
        try:
            datos = json.loads(bloque.string)
        except json.JSONDecodeError:
            continue

        if datos.get("@type") != "ItemList":
            continue

        for elemento in datos.get("itemListElement", []):
            item = elemento.get("item", {})
            oferta = item.get("offers", {})
            productos.append({
                "nombre": item.get("name"),
                "precio": _precio_de_lista(oferta),
                "url": item.get("url"),
            })

    return productos


def _precio_de_lista(oferta: dict) -> float | None:
    """
    Devuelve el precio de lista (sin descuentos de tarjeta/promo) de
    una oferta del JSON-LD de La Anonima.

    El sitio publica dos precios distintos en el mismo bloque "offers":
    - "price": el precio promocional/con descuento de tarjeta, que es
      el que se ve mas grande en la pagina pero no es el precio real
      sin tarjeta especifica.
    - "priceSpecification.price" (con priceType ListPrice): el precio
      de lista real, el mismo que paga cualquier persona sin
      necesitar una tarjeta puntual.

    Para comparar de forma pareja contra Carrefour y Changomas (que
    no siempre distinguen este tipo de descuento de la misma forma),
    usamos siempre el precio de lista cuando esta disponible. Si no
    esta (producto sin promo), caemos al "price" normal, que en ese
    caso es el mismo valor.
    """
    spec = oferta.get("priceSpecification")
    if spec and spec.get("price"):
        return spec["price"]
    return oferta.get("price")


# --- Orquestacion del catalogo completo ---------------------------------

def leer_urls_de_categorias(ruta_archivo: str) -> list[str]:
    """
    Lee el archivo de texto con las URLs de categoria, una por linea.
    Ignora lineas vacias y lineas que empiecen con # (para poder dejar
    comentarios o desactivar una URL sin borrarla).
    """
    contenido = Path(ruta_archivo).read_text(encoding="utf-8")
    urls = []
    for linea in contenido.splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            urls.append(linea)
    return urls


def nombre_categoria_desde_url(url: str) -> str:
    """
    Saca un nombre legible de la categoria a partir de la URL, para
    poder identificar de donde vino cada producto en el CSV final.
    Ejemplo: https://www.laanonima.com.ar/leches/n3_722/ -> "leches"
    """
    partes = [p for p in url.rstrip("/").split("/") if p]
    # La ultima parte suele ser el codigo (n3_722), la anteultima el
    # nombre legible de la categoria.
    return partes[-2] if len(partes) >= 2 else url


def armar_catalogo(urls: list[str]) -> list[dict]:
    """
    Recorre todas las URLs de categoria, junta los productos de cada
    una, y devuelve una sola lista con todo.
    """
    catalogo_completo = []

    for indice, url in enumerate(urls, start=1):
        categoria = nombre_categoria_desde_url(url)
        print(f"[{indice}/{len(urls)}] Leyendo categoria '{categoria}'...")

        productos = obtener_productos_de_categoria(url)
        print(f"  -> {len(productos)} productos encontrados")

        for producto in productos:
            producto["categoria"] = categoria
            catalogo_completo.append(producto)

        # Pausa antes del siguiente pedido, salvo que sea el ultimo.
        if indice < len(urls):
            time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    return catalogo_completo


def guardar_csv(catalogo: list[dict], ruta_salida: str):
    """
    Guarda el catalogo completo en un CSV con columnas fijas, en el
    orden que tiene mas sentido para leer en una planilla.
    """
    with open(ruta_salida, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=["categoria", "nombre", "precio", "url"],
        )
        escritor.writeheader()
        escritor.writerows(catalogo)


def main():
    if len(sys.argv) < 2:
        print("Uso: python precios_armar_catalogo_anonima.py <archivo-con-urls.txt>")
        sys.exit(1)

    ruta_urls = sys.argv[1]
    urls = leer_urls_de_categorias(ruta_urls)

    if not urls:
        print(f"No se encontraron URLs en {ruta_urls}")
        sys.exit(1)

    print(f"Se van a leer {len(urls)} categorias.\n")
    catalogo = armar_catalogo(urls)

    if not catalogo:
        print("\nNo se junto ningun producto. Revisemos que paso.")
        return

    guardar_csv(catalogo, ARCHIVO_SALIDA)
    print(f"\nListo: {len(catalogo)} productos guardados en {ARCHIVO_SALIDA}")


if __name__ == "__main__":
    main()
