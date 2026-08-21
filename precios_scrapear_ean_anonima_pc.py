"""
precios_scrapear_ean_anonima_pc.py

Version del scraper de EAN pensada para correr desde la PC, no desde
el VPS. Motivo: la IP del VPS quedo bloqueada por CloudFront el
21/8/2026 (bloqueo de todo el dominio laanonima.com.ar, confirmado
con robots.txt devolviendo 403) - la IP de la PC de Agustin SI puede
acceder sin problema (confirmado a mano en el navegador).

Como funciona (en 3 pasos, con 2 scripts):
    1. En el VPS: exportar los pendientes a un CSV (ver instrucciones
       en el chat - un SELECT con sqlite3 -csv).
    2. Bajar ese CSV a la PC, correr ESTE script - lee el CSV, elige
       una muestra al AZAR de N productos (no siempre los mismos, ni
       en el mismo orden - menos predecible), busca el EAN de cada
       uno, y guarda el resultado en otro CSV.
    3. Subir ese CSV de resultados al VPS y correr
       precios_importar_ean_csv.py para cargarlo a la base real.

HEADERS/COOKIES/SEGUNDOS_ENTRE_PEDIDOS: copiados identicos de
precios_armar_catalogo_anonima.py (mismo sitio, mismas reglas de
acceso - ver ese archivo para el detalle de cada cookie).

Requiere (instalar una sola vez en la PC):
    pip install requests beautifulsoup4

Como correrlo:
    python precios_scrapear_ean_anonima_pc.py pendientes_ean_anonima.csv --muestra 200

Genera:
    resultados_ean_anonima_pc.csv (para subir al VPS despues)
"""

import argparse
import csv
import random
import time

import requests
from bs4 import BeautifulSoup

# --- Constantes (copiadas de precios_armar_catalogo_anonima.py) --------

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

SEGUNDOS_ENTRE_PEDIDOS = 2
ARCHIVO_SALIDA = "resultados_ean_anonima_pc.csv"


def extraer_ean_de_producto(url: str) -> str | None:
    """
    Pide la pagina de UN producto individual y le saca el EAN del
    bloque JSON-LD tipo "Product" (campo "gtin"). Devuelve None si
    algo falla - nunca rompe el flujo.
    """
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
            import json
            datos = json.loads(bloque.string)
        except Exception:
            continue

        if datos.get("@type") != "Product":
            continue

        gtin = datos.get("gtin") or datos.get("gtin13")
        if gtin:
            return str(gtin)

    return None


def leer_pendientes(ruta_csv: str) -> list[dict]:
    with open(ruta_csv, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def correr(ruta_csv: str, tamano_muestra: int) -> None:
    pendientes = leer_pendientes(ruta_csv)

    if not pendientes:
        print(f"No hay productos en {ruta_csv}.")
        return

    muestra = random.sample(pendientes, min(tamano_muestra, len(pendientes)))

    print(f"Total pendientes en el CSV: {len(pendientes)}")
    print(f"Muestra al azar elegida: {len(muestra)}\n")

    resultados = []
    encontrados = 0

    for indice, producto in enumerate(muestra, start=1):
        codigo = producto["codigo_producto"]
        nombre = producto["nombre"]
        url = producto.get("url")

        print(f"[{indice}/{len(muestra)}] {nombre}")

        if not url:
            print("    Sin URL - se salta.")
            continue

        ean = extraer_ean_de_producto(url)

        if ean:
            print(f"    EAN encontrado: {ean}")
            resultados.append({"codigo_producto": codigo, "ean": ean})
            encontrados += 1
        else:
            print("    No se encontro EAN.")

        if indice < len(muestra):
            time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=["codigo_producto", "ean"])
        escritor.writeheader()
        escritor.writerows(resultados)

    print(f"\n--- Resumen ---")
    print(f"EAN encontrados: {encontrados} de {len(muestra)}")
    print(f"Guardado en: {ARCHIVO_SALIDA}")
    print("Subi este archivo al VPS y corre precios_importar_ean_csv.py")


def main():
    parser = argparse.ArgumentParser(
        description="Scrapea EAN de una muestra al azar de productos pendientes (para correr desde la PC)."
    )
    parser.add_argument("csv_pendientes", help="CSV exportado del VPS con los productos pendientes.")
    parser.add_argument("--muestra", type=int, default=200, help="Cantidad de productos a probar (default: 200).")
    args = parser.parse_args()

    correr(args.csv_pendientes, args.muestra)


if __name__ == "__main__":
    main()
