"""
precios_guardar_catalogo_completo.py

Guarda en precios_historico.db TODO lo que el scraper trajo en la
ultima corrida (~5500 productos en todas las categorias), no solo
los 41 rubros curados de la canasta oficial.

Por que un script separado de precios_buscar_canasta.py: ese script
ya tiene su trabajo (elegir el mas barato de cada rubro para la
canasta oficial que se ve en la web) y transforma los datos en el
camino (por ejemplo, sobreescribe "precio" con "precio_lista" para
VTEX). Para el historico completo queremos los datos crudos, sin esa
transformacion - asi que este script lee los CSV de nuevo,
directamente, preservando categoria, precio Y precio_lista por
separado.

Esta tabla es deliberadamente "backend only": nada de lo que guarda
este script se muestra en precios.html. Es insumo para el futuro
(buscador de precios, canastas personalizadas por Guardian - ver
precios_MAESTRO.md).

[MODIFICADO - sesion 19/8/2026]: cargar_catalogo_vtex ahora tambien
lee la columna "marca" del CSV y la pasa a guardar_catalogo_completo.
Antes se leia el CSV pero la marca se descartaba en el camino - VTEX
ya la trae gratis, y ahora alimenta productos_maestro (ver
precios_db.upsert_producto_maestro).

Dependencias (tienen que existir ANTES de correr este script):
- catalogo_anonima.csv (generado por precios_armar_catalogo_anonima.py)
- catalogo_vtex.csv (generado por precios_armar_catalogo_vtex.py)

Como correrlo:
    python precios_guardar_catalogo_completo.py
"""

import csv
import sys
from datetime import date

import precios_db

ARCHIVO_ANONIMA = "catalogo_anonima.csv"
ARCHIVO_VTEX = "catalogo_vtex.csv"


def cargar_catalogo_anonima() -> list[dict]:
    """
    Lee catalogo_anonima.csv tal cual esta, sin transformar nada.
    Columnas del CSV: categoria, nombre, precio, url.

    La Anonima no expone la marca en el listado de categoria (solo
    en la pagina de cada producto individual, ver investigacion de
    la sesion del 19/8) - por eso "marca" no se pasa aca, queda en
    None y productos_maestro.marca se completa despues por otro medio
    si hace falta.
    """
    productos = []
    try:
        with open(ARCHIVO_ANONIMA, encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                try:
                    precio = float(fila["precio"])
                except (ValueError, KeyError):
                    continue

                productos.append({
                    "tienda": "La Anonima",
                    "categoria": fila.get("categoria", ""),
                    "nombre": fila["nombre"],
                    "precio": precio,
                    "precio_lista": None,  # La Anonima no expone esto en el listado
                    "url": fila.get("url", ""),
                })
    except FileNotFoundError:
        print(f"No se encontro {ARCHIVO_ANONIMA}. Corre precios_armar_catalogo_anonima.py primero.")
        sys.exit(1)

    return productos


def cargar_catalogo_vtex() -> list[dict]:
    """
    Lee catalogo_vtex.csv tal cual esta, sin transformar nada.
    Columnas del CSV: tienda, categoria, nombre, marca, precio,
    precio_lista, url.

    [FIX 19/8/2026] Antes esta funcion leia el CSV pero no incluia
    "marca" en el diccionario devuelto, asi que se perdia antes de
    llegar a la base de datos aunque el dato ya estaba disponible
    gratis (VTEX lo trae en el campo "brand"). Ahora se pasa.
    """
    productos = []
    try:
        with open(ARCHIVO_VTEX, encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                try:
                    precio = float(fila["precio"])
                except (ValueError, KeyError):
                    continue

                try:
                    precio_lista = float(fila.get("precio_lista") or 0) or None
                except ValueError:
                    precio_lista = None

                productos.append({
                    "tienda": fila["tienda"],
                    "categoria": fila.get("categoria", ""),
                    "nombre": fila["nombre"],
                    "marca": fila.get("marca") or None,
                    "precio": precio,
                    "precio_lista": precio_lista,
                    "url": fila.get("url", ""),
                })
    except FileNotFoundError:
        print(f"No se encontro {ARCHIVO_VTEX}. Corre precios_armar_catalogo_vtex.py primero.")
        sys.exit(1)

    return productos


def main():
    print("Guardando catalogo completo en el historico...")

    productos = cargar_catalogo_anonima() + cargar_catalogo_vtex()
    fecha = date.today().isoformat()

    print(f"  {len(productos)} productos a guardar")
    print(f"  Fecha: {fecha}")

    filas = precios_db.guardar_catalogo_completo(fecha, productos)

    print(f"\nListo: {filas} filas guardadas en historico_catalogo_completo")


if __name__ == "__main__":
    main()
