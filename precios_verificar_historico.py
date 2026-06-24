"""
precios_verificar_historico.py

Script de un solo uso para confirmar que guardar_foto_dia() guardo
bien los datos en precios_historico.db. Consulta:
1. Las filas del rubro 1 (Harina 000) guardadas hoy.
2. Un resumen general: cuantas filas hay en total, cuantos dias
   distintos, y la ultima fecha con datos.

Como correrlo:
    python precios_verificar_historico.py
"""

import precios_db
import sqlite3

print("=== Rubro 1 (Harina 000) - usando precios_db.obtener_historico() ===\n")

filas = precios_db.obtener_historico(rubro_id=1)
for fila in filas:
    print(f"  {fila['fecha']} | {fila['tienda']:<12} | "
          f"${fila['precio_normalizado']:.0f}/kg | {fila['producto']}")
    if fila['url']:
        print(f"      url: {fila['url']}")

print(f"\n=== Resumen general de la base ===\n")

conn = sqlite3.connect("precios_historico.db")

total_filas = conn.execute("SELECT COUNT(*) FROM historico_precios").fetchone()[0]
print(f"  Total de filas en historico_precios: {total_filas}")

dias_distintos = conn.execute(
    "SELECT COUNT(DISTINCT fecha) FROM historico_precios"
).fetchone()[0]
print(f"  Dias distintos con datos: {dias_distintos}")

ultima_fecha = precios_db.obtener_ultima_fecha()
print(f"  Ultima fecha con datos: {ultima_fecha}")

filas_por_tienda = conn.execute(
    """
    SELECT t.nombre, COUNT(*)
    FROM historico_precios hp
    JOIN tiendas t ON t.id = hp.tienda_id
    GROUP BY t.nombre
    """
).fetchall()
print(f"\n  Filas por tienda:")
for nombre, cantidad in filas_por_tienda:
    print(f"    {nombre}: {cantidad}")

conn.close()
