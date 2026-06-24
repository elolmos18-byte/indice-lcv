"""
precios_armar_catalogo_vtex.py

Catalogo de precios para los supermercados que usan la plataforma
VTEX en Madryn - hoy Carrefour y Changomas.

Esta version lee las categorias a buscar desde dos archivos de texto
separados, uno por super:
- precios_categorias_carrefour_canasta.txt
- precios_categorias_changomas_canasta.txt

Por que la lectura externa: antes las categorias estaban hardcodeadas
adentro del codigo, lo que obligaba a editar Python cada vez que
queriamos sumar o sacar una. Asi es mas comodo: editas un .txt, no
tocas el .py.

Bonus de la plataforma VTEX respecto a La Anonima: expone el "precio
de lista" (precio sin descuento) ademas del precio actual. Si un
producto tiene precio_lista > precio, es una oferta real declarada
por el propio sitio - no necesitamos calcular un promedio historico
para detectarlo.

Filtros que aplicamos a cada producto, en orden:
1. Que tenga precio mayor a cero (los sin stock vienen con precio 0).
2. Que VTEX lo marque como IsAvailable = true.
3. Que tenga AvailableQuantity > 0 - encontramos productos sin stock
   con precio viejo pegado que pasaban los otros dos chequeos.

Si un producto no cumple los tres filtros se descarta, sin error -
no nos sirve para comparar precios actuales.

Como correrlo:
    pip install requests
    python precios_armar_catalogo_vtex.py
"""

import csv
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

TAMANO_PAGINA = 50
SEGUNDOS_ENTRE_PEDIDOS = 2
ARCHIVO_SALIDA = "catalogo_vtex.csv"

# Cada tienda: nombre legible + dominio + archivo con sus categorias.
# Si en el futuro sumamos otro super VTEX, alcanza con agregarlo aca
# y crear su archivo de canasta correspondiente.
TIENDAS = [
    {
        "nombre": "Changomas",
        "dominio": "www.masonline.com.ar",
        "archivo_categorias": "precios_categorias_changomas_canasta.txt",
    },
    {
        "nombre": "Carrefour",
        "dominio": "www.carrefour.com.ar",
        "archivo_categorias": "precios_categorias_carrefour_canasta.txt",
    },
]

# Cache para no pedir el robots.txt de cada dominio mas de una vez.
_robots_por_dominio: dict[str, urllib.robotparser.RobotFileParser] = {}


# --- Lectura del archivo de categorias ---------------------------------

def leer_categorias_del_archivo(ruta_archivo: str) -> list[tuple[str, str]]:
    """
    Lee un archivo de texto con lineas "nombre|url" y devuelve una
    lista de tuplas (nombre_categoria, ruta_relativa).

    Ignora lineas vacias y las que empiezan con # (comentarios).
    Tambien convierte la URL completa a ruta relativa, porque la API
    de VTEX se llama con la ruta solamente, sin dominio.
    Ejemplo: https://www.masonline.com.ar/almacen/aceites -> almacen/aceites
    """
    categorias = []
    contenido = Path(ruta_archivo).read_text(encoding="utf-8")

    for linea in contenido.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue

        if "|" not in linea:
            print(f"  Ignorando linea sin formato nombre|url: {linea}")
            continue

        nombre, url = linea.split("|", 1)
        nombre = nombre.strip()
        url = url.strip()

        # Convertimos la URL completa en ruta relativa, que es lo que
        # necesitamos para llamar a la API de VTEX.
        ruta = urlparse(url).path.strip("/")
        if ruta:
            categorias.append((nombre, ruta))

    return categorias


# --- Robots.txt --------------------------------------------------------

def sitio_permite_scrapear(dominio: str, ruta: str) -> bool:
    """
    Chequea el robots.txt del dominio (una sola vez, despues queda
    en cache) antes de pedir una ruta puntual.
    """
    if dominio not in _robots_por_dominio:
        url_robots = f"https://{dominio}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        try:
            respuesta = requests.get(url_robots, headers=HEADERS, timeout=10)
            parser.parse(respuesta.text.splitlines())
        except requests.RequestException:
            print(f"No se pudo leer robots.txt de {dominio}. Por las dudas, no seguimos con este dominio.")
            parser.parse(["User-agent: *", "Disallow: /"])  # bloquea todo
        _robots_por_dominio[dominio] = parser

    parser = _robots_por_dominio[dominio]
    url_completa = urljoin(f"https://{dominio}", ruta)
    return parser.can_fetch(HEADERS["User-Agent"], url_completa)


# --- API de catalogo VTEX ----------------------------------------------

def pedir_pagina(dominio: str, categoria: str, desde: int, hasta: int):
    url = f"https://{dominio}/api/catalog_system/pub/products/search/{categoria}"
    parametros = {"_from": desde, "_to": hasta}
    respuesta = requests.get(url, headers=HEADERS, params=parametros, timeout=15)
    if respuesta.status_code not in (200, 206):
        return None
    return respuesta.json()


def buscar_categoria(dominio: str, categoria: str) -> list[dict]:
    """
    Pagina sobre la API de VTEX hasta agotar los productos de una
    categoria. Aplica los tres filtros de disponibilidad (ver docstring
    del modulo) y devuelve solo productos con precio actual valido.
    """
    ruta_api = f"/api/catalog_system/pub/products/search/{categoria}"
    if not sitio_permite_scrapear(dominio, ruta_api):
        print(f"  robots.txt no permite leer {dominio}{ruta_api}")
        return []

    productos = []
    desde = 0

    while True:
        hasta = desde + TAMANO_PAGINA - 1
        pagina = pedir_pagina(dominio, categoria, desde, hasta)

        if not pagina:
            break

        for item in pagina:
            try:
                oferta = item["items"][0]["sellers"][0]["commertialOffer"]
                precio = oferta.get("Price")
                disponible = oferta.get("IsAvailable")
                cantidad_disponible = oferta.get("AvailableQuantity", 0)

                if not precio or not disponible or cantidad_disponible <= 0:
                    continue

                productos.append({
                    "nombre": item.get("productName"),
                    "marca": item.get("brand"),
                    "precio": precio,
                    "precio_lista": oferta.get("ListPrice"),
                    "url": f"https://{dominio}/{item.get('linkText')}/p",
                })
            except (KeyError, IndexError):
                continue

        if len(pagina) < TAMANO_PAGINA:
            break

        desde += TAMANO_PAGINA
        time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    return productos


# --- Orquestacion ------------------------------------------------------

def armar_catalogo() -> list[dict]:
    catalogo = []

    for tienda in TIENDAS:
        print(f"\n=== {tienda['nombre']} ===")

        try:
            categorias = leer_categorias_del_archivo(tienda["archivo_categorias"])
        except FileNotFoundError:
            print(f"  No se encontro {tienda['archivo_categorias']} - salteando esta tienda")
            continue

        for nombre_categoria, ruta_categoria in categorias:
            print(f"[{tienda['nombre']}] Leyendo '{nombre_categoria}'...")
            productos = buscar_categoria(tienda["dominio"], ruta_categoria)
            print(f"  -> {len(productos)} productos encontrados")

            for producto in productos:
                producto["tienda"] = tienda["nombre"]
                producto["categoria"] = nombre_categoria
                catalogo.append(producto)

            time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    return catalogo


def guardar_csv(catalogo: list[dict], ruta_salida: str):
    columnas = ["tienda", "categoria", "nombre", "marca", "precio", "precio_lista", "url"]
    with open(ruta_salida, "w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(catalogo)


def main():
    catalogo = armar_catalogo()

    if not catalogo:
        print("\nNo se junto ningun producto. Revisemos que paso.")
        return

    guardar_csv(catalogo, ARCHIVO_SALIDA)
    print(f"\nListo: {len(catalogo)} productos guardados en {ARCHIVO_SALIDA}")


if __name__ == "__main__":
    main()
