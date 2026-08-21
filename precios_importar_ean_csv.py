"""
precios_importar_ean_csv.py

Importa a productos_maestro los EAN que se scrapearon desde la PC
(ver precios_scrapear_ean_anonima_pc.py) - paso 3 del flujo de
respaldo para cuando el VPS tiene bloqueada la IP en La Anonima.

Como correrlo (en el VPS, con el CSV ya subido):
    python precios_importar_ean_csv.py resultados_ean_anonima_pc.csv
"""

import argparse
import csv

import precios_db


def correr(ruta_csv: str) -> None:
    with open(ruta_csv, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))

    if not filas:
        print(f"No hay filas en {ruta_csv}.")
        return

    print(f"Importando {len(filas)} EAN desde {ruta_csv}...\n")

    importados = 0
    for fila in filas:
        codigo = fila["codigo_producto"]
        ean = fila["ean"]

        if not codigo or not ean:
            continue

        precios_db.guardar_ean(codigo, ean)
        importados += 1

    print(f"Listo: {importados} EAN importados a productos_maestro.")


def main():
    parser = argparse.ArgumentParser(
        description="Importa EAN scrapeados desde la PC al VPS."
    )
    parser.add_argument("csv_resultados", help="CSV generado por precios_scrapear_ean_anonima_pc.py")
    args = parser.parse_args()

    correr(args.csv_resultados)


if __name__ == "__main__":
    main()
