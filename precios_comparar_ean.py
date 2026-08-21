"""
precios_comparar_ean.py

Para el dia de hoy (o una fecha puntual), busca todos los EAN que
aparecen en 2 o mas tiendas, y calcula cual es la mas barata y cual
la mas cara para cada uno - version automatizada de la comparacion
manual que se hizo con la Harina Blancaflor (mismo EAN, 22% mas cara
en La Anonima que en Changomas, sesion 20/8/2026).

Por que esto es mas confiable que comparar por nombre: cada tienda
escribe el nombre del producto distinto (ej. "Blancaflor" vs "Fort
Blancaflor" vs "Blancaflor 1kg."). El EAN es el mismo codigo de
barras real del fabricante, no cambia entre tiendas - permite
identificar con certeza que es EXACTAMENTE el mismo producto fisico.

Requiere que productos_maestro ya tenga ean Y cantidad_normalizada
cargados para poder comparar (ver precios_armar_catalogo_vtex.py
para VTEX, precios_scrapear_ean_anonima.py para La Anonima, y
precios_clasificar_ia.py para la normalizacion).

Como correrlo (para el dia de hoy):
    python precios_comparar_ean.py

Para una fecha puntual:
    python precios_comparar_ean.py --fecha 2026-08-20
"""

import argparse
from datetime import date

import precios_db


def correr(fecha: str) -> None:
    print(f"Comparando precios por EAN para {fecha}...\n")

    por_ean = precios_db.obtener_precios_por_ean_del_dia(fecha)

    # Solo interesan los EAN que aparecen en 2+ tiendas ese dia -
    # si esta en una sola tienda, no hay nada que comparar.
    comparables = {ean: precios for ean, precios in por_ean.items() if len(precios) >= 2}

    if not comparables:
        print("No hay EAN comparables (en 2+ tiendas) para esta fecha todavia.")
        return

    print(f"{len(comparables)} productos con EAN comparables entre tiendas.\n")

    guardados = 0
    mayor_diferencia = None

    for ean, precios in comparables.items():
        precio_min_info = min(precios, key=lambda p: p["precio_normalizado"])
        precio_max_info = max(precios, key=lambda p: p["precio_normalizado"])

        precio_min = precio_min_info["precio_normalizado"]
        precio_max = precio_max_info["precio_normalizado"]

        if precio_min <= 0:
            continue

        diferencia_pct = (precio_max - precio_min) / precio_min * 100

        # marca/categoria: se toma de cualquiera de las tiendas (deberia
        # ser la misma, es el mismo producto fisico), priorizando la
        # que tenga marca cargada.
        con_marca = next((p for p in precios if p.get("marca")), precios[0])

        precios_db.guardar_comparacion_ean_diaria(
            fecha=fecha,
            ean=ean,
            nombre_referencia=con_marca["nombre"],
            marca=con_marca.get("marca"),
            categoria_ia=con_marca.get("categoria_ia"),
            cantidad_tiendas=len(precios),
            precio_min=precio_min,
            tienda_mas_barata=precio_min_info["tienda"],
            precio_max=precio_max,
            tienda_mas_cara=precio_max_info["tienda"],
            diferencia_pct=diferencia_pct,
        )
        guardados += 1

        if mayor_diferencia is None or diferencia_pct > mayor_diferencia[0]:
            mayor_diferencia = (diferencia_pct, con_marca["nombre"], precio_min_info["tienda"], precio_max_info["tienda"])

    print(f"Listo: {guardados} comparaciones guardadas.")

    if mayor_diferencia:
        pct, nombre, tienda_barata, tienda_cara = mayor_diferencia
        print(f"\nMayor diferencia encontrada hoy ({pct:.1f}%):")
        print(f"  {nombre}")
        print(f"  Mas barato en {tienda_barata}, mas caro en {tienda_cara}")


def main():
    parser = argparse.ArgumentParser(
        description="Compara precios del mismo producto (por EAN) entre supermercados."
    )
    parser.add_argument(
        "--fecha",
        type=str,
        default=date.today().isoformat(),
        help="Fecha a comparar, formato YYYY-MM-DD (default: hoy).",
    )
    args = parser.parse_args()

    correr(args.fecha)


if __name__ == "__main__":
    main()
