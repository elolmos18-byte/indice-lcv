"""
precios_probar_db.py

Prueba rapida de precios_db.py: llena la tabla rubros desde el JSON
y muestra cuantos quedaron cargados. Script de un solo uso para
verificar que todo funciona antes de integrar con
precios_buscar_canasta.py.

Como correrlo:
    python precios_probar_db.py
"""

import precios_db

cantidad = precios_db.poblar_rubros("precios_canasta_rubros.json")
print(f"Rubros procesados: {cantidad}")

import sqlite3
conn = sqlite3.connect("precios_historico.db")
filas = conn.execute("SELECT id, nombre, unidad FROM rubros ORDER BY id").fetchall()
conn.close()

print(f"\nRubros en la base ({len(filas)}):")
for fila in filas[:5]:
    print(f"  {fila}")
print("  ...")
for fila in filas[-3:]:
    print(f"  {fila}")
