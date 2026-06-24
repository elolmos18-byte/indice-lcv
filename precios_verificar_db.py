"""
precios_verificar_db.py

Script de un solo uso para confirmar que precios_historico.db tiene
las tablas esperadas despues de correr precios_schema.sql.

Como correrlo:
    python precios_verificar_db.py
"""

import sqlite3

conn = sqlite3.connect("precios_historico.db")

tablas = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()

print("Tablas encontradas:")
for (nombre,) in tablas:
    print(f"  - {nombre}")

print("\nTiendas insertadas:")
for fila in conn.execute("SELECT id, nombre FROM tiendas"):
    print(f"  {fila}")

conn.close()
