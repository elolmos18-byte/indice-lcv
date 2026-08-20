"""
precios_calcular_estadisticas.py

Calcula, para cada categoria y el dia de hoy (o una fecha puntual),
la distribucion de precio_normalizado de todos los productos de esa
categoria en las 4 tiendas juntas: minimo, Q1, mediana, Q3, maximo y
desvio estandar. Ademas encuentra el "producto representativo" de
cada cuartil - el producto real cuyo precio esta mas cerca de ese
valor (ver arquitectura del Observatorio, seccion 5.4 punto 9).

Por que esto necesita que productos_maestro este clasificado: sin
categoria_ia y cantidad_normalizada (que pone Gemini, ver
precios_clasificar_ia.py) no hay forma de agrupar productos por
categoria ni de calcular un precio comparable (precio/kg, precio/L).
Los productos que todavia no fueron clasificados simplemente no
entran en el calculo de ese dia - no rompen nada, solo quedan afuera
hasta que se clasifiquen.

Por que no calcular esto al vuelo cada vez que alguien mira el
dashboard: ver docstring de la tabla estadisticas_categoria_diaria
en precios_schema.sql.

Como correrlo (para el dia de hoy):
    python precios_calcular_estadisticas.py

Para una fecha puntual (por si hay que recalcular un dia viejo):
    python precios_calcular_estadisticas.py --fecha 2026-08-19
"""

import argparse
import statistics
from datetime import date

import precios_db


def producto_mas_cercano(valor_objetivo: float, productos: list[tuple[str, float]]) -> str:
    """
    De una lista de (codigo_producto, precio_normalizado), devuelve
    el codigo_producto cuyo precio esta MAS CERCA de valor_objetivo.
    Usado para encontrar el producto representativo de cada cuartil.
    """
    return min(productos, key=lambda p: abs(p[1] - valor_objetivo))[0]


def calcular_estadisticas_categoria(productos: list[tuple[str, float]]) -> dict:
    """
    Recibe la lista de (codigo_producto, precio_normalizado) de UNA
    categoria, y devuelve todas las estadisticas + los 3 productos
    representativos (Q1, mediana, Q3).

    Requiere al menos 1 producto. Con muy pocos productos (1 o 2) los
    cuartiles pueden coincidir entre si o con el min/max - es
    matematicamente correcto, no un bug, simplemente hay poca
    variedad todavia en esa categoria.
    """
    precios = sorted(p[1] for p in productos)

    precio_min = precios[0]
    precio_max = precios[-1]
    precio_mediana = statistics.median(precios)

    if len(precios) >= 2:
        # quantiles con n=4 devuelve [Q1, mediana, Q3] cuando se le
        # pide method="inclusive" - usamos esos primeros 2 valores
        # (Q1 y Q3) y calculamos mediana aparte con statistics.median
        # para no depender de que coincida exactamente.
        cuartiles = statistics.quantiles(precios, n=4, method="inclusive")
        precio_q1 = cuartiles[0]
        precio_q3 = cuartiles[2]
        desvio_estandar = statistics.stdev(precios) if len(precios) >= 2 else 0.0
    else:
        # Con un solo producto, Q1/Q3/desvio no tienen sentido
        # estadistico real - se dejan iguales al unico precio que hay.
        precio_q1 = precio_min
        precio_q3 = precio_max
        desvio_estandar = 0.0

    return {
        "cantidad_productos": len(productos),
        "precio_min": precio_min,
        "precio_q1": precio_q1,
        "precio_mediana": precio_mediana,
        "precio_q3": precio_q3,
        "precio_max": precio_max,
        "desvio_estandar": desvio_estandar,
        "producto_q1": producto_mas_cercano(precio_q1, productos),
        "producto_mediana": producto_mas_cercano(precio_mediana, productos),
        "producto_q3": producto_mas_cercano(precio_q3, productos),
    }


def correr(fecha: str) -> None:
    print(f"Calculando estadisticas para {fecha}...\n")

    por_categoria = precios_db.obtener_precios_normalizados_del_dia(fecha)

    if not por_categoria:
        print("No hay productos clasificados con precio para esta fecha todavia.")
        print("(Necesita que precios_clasificar_ia.py haya corrido antes.)")
        return

    print(f"{len(por_categoria)} categorias con datos.\n")

    for categoria, productos in sorted(por_categoria.items()):
        stats = calcular_estadisticas_categoria(productos)

        precios_db.guardar_estadisticas_categoria_diaria(
            fecha=fecha,
            categoria=categoria,
            **stats,
        )

        print(
            f"  {categoria}: {stats['cantidad_productos']} productos | "
            f"min={stats['precio_min']:.2f} Q1={stats['precio_q1']:.2f} "
            f"med={stats['precio_mediana']:.2f} Q3={stats['precio_q3']:.2f} "
            f"max={stats['precio_max']:.2f}"
        )

    print(f"\nListo: estadisticas guardadas para {len(por_categoria)} categorias.")


def main():
    parser = argparse.ArgumentParser(
        description="Calcula estadisticas diarias por categoria (cuartiles, mediana, desvio)."
    )
    parser.add_argument(
        "--fecha",
        type=str,
        default=date.today().isoformat(),
        help="Fecha a calcular, formato YYYY-MM-DD (default: hoy).",
    )
    args = parser.parse_args()

    correr(args.fecha)


if __name__ == "__main__":
    main()
