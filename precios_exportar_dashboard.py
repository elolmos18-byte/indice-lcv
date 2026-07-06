"""
precios_exportar_dashboard.py

Genera dashboard_datos.json - el archivo que lee dashboard.html para
mostrar graficos de evolucion de precios y el estado general del
sistema.

Por que un archivo aparte de precios_ultimo.json: precios_ultimo.json
solo tiene la foto de HOY. El dashboard necesita el historico
completo (todas las fechas guardadas), que sale de consultar
precios_historico.db - una tarea mas pesada que no tiene sentido
repetir en cada visita a precios.html, asi que se genera una vez por
corrida y se guarda como archivo estatico, igual que precios_ultimo.json.

Se ejecuta como parte de precios_corrida_diaria.sh, despues de
precios_buscar_canasta.py (que es quien deja precios_historico.db
actualizado con los datos del dia).

Como correrlo a mano:
    python3 precios_exportar_dashboard.py
"""

import json
from datetime import datetime, timezone

import precios_db

ARCHIVO_SALIDA = "dashboard_datos.json"


def armar_estado_general() -> dict:
    """
    Lee precios_ultimo.json (la foto de hoy) para armar el resumen
    de "estado del sistema": fecha de la ultima corrida, cuantos
    rubros hay, y la cobertura de cada tienda (en cuantos rubros
    aparece con precio, sobre el total).
    """
    try:
        with open("precios_ultimo.json", encoding="utf-8") as f:
            datos_hoy = json.load(f)
    except FileNotFoundError:
        return {}

    rubros = datos_hoy.get("rubros", [])
    total_rubros = len(rubros)

    tiendas = sorted({
        tienda
        for rubro in rubros
        for tienda in rubro.get("precios", {}).keys()
    })

    cobertura = {}
    for tienda in tiendas:
        con_precio = sum(
            1 for rubro in rubros if tienda in rubro.get("precios", {})
        )
        cobertura[tienda] = {
            "con_precio": con_precio,
            "total_rubros": total_rubros,
            "porcentaje": round(100 * con_precio / total_rubros, 1) if total_rubros else 0,
        }

    return {
        "fecha_ultima_corrida": datos_hoy.get("fecha"),
        "total_rubros": total_rubros,
        "mas_barato_hoy": datos_hoy.get("mas_barato"),
        "cobertura_por_tienda": cobertura,
    }


def main():
    rubros = precios_db.obtener_rubros()
    evolucion_totales = precios_db.obtener_evolucion_totales()
    evolucion_por_rubro = precios_db.obtener_evolucion_todos_los_rubros()
    estado_general = armar_estado_general()

    salida = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "estado_general": estado_general,
        "rubros": rubros,
        "evolucion_totales": evolucion_totales,
        "evolucion_por_rubro": evolucion_por_rubro,
    }

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(f"Listo: {ARCHIVO_SALIDA} generado con {len(rubros)} rubros "
          f"y {len(evolucion_totales.get('fechas', []))} fechas de historico.")


if __name__ == "__main__":
    main()
