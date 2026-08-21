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

DETECTOR AUTOMATICO DE INCONSISTENCIAS [agregado 20/8/2026]: al usar
esta herramienta se encontraron varios casos reales donde el mismo
EAN (mismo producto fisico) tenia unidad_normalizada distinta entre
tiendas (ej. "kg" en una, "unidad" en otra) - eso es matematicamente
imposible que sea correcto, siempre es un bug de normalizacion en
alguna de las tiendas. En vez de perseguir cada palabra nueva del
nombre a mano (ya se encontraron "saq", "Un.", "N Grs x N Un" en la
misma sesion), este script detecta la inconsistencia solo: si un EAN
tiene mas de una unidad_normalizada distinta entre tiendas, se queda
con la unidad MAYORITARIA para la comparacion de precios, y resetea
automaticamente (via precios_db.resetear_producto_para_reclasificar)
los productos que quedaron en minoria, para que la proxima corrida
de precios_clasificar_ia.py los reintente. Sistema auto-correctivo:
cuantas mas veces se corra este script despues de clasificar, mas
prolijo va quedando el catalogo, sin trabajo manual por cada caso.

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
from collections import Counter
from datetime import date

import precios_db


def separar_consistentes_e_inconsistentes(
    precios: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Recibe la lista de precios de UN EAN (varias tiendas) y separa
    en dos grupos, aplicando 2 chequeos en orden:

    CHEQUEO 1 - unidad_normalizada distinta entre tiendas (ej. "kg"
    en una, "unidad" en otra) - matematicamente imposible que sea
    correcto para el mismo producto fisico. Se queda con la unidad
    MAYORITARIA; los que no coinciden pasan a inconsistentes.

    Si hay empate en la mayoria (ej. 2 tiendas dicen "kg" y 2 dicen
    "unidad"), no hay forma de saber cual es la correcta - en ese
    caso NINGUNO se marca como inconsistente en este chequeo (mejor
    no tocar nada que arriesgar resetear el que en realidad estaba
    bien).

    CHEQUEO 2 [agregado 20/8/2026, tras el caso "Rollo de Cocina
    Felpita 200 Paños 1 U"] - dentro del grupo que ya coincide en
    unidad, la CANTIDAD puede seguir estando mal (una tienda
    interpreto "1 rollo" y otra "200 unidades", confundiendo la
    cantidad de paños con la cantidad de rollos - las unidades
    coinciden, pero el precio normalizado resultante es absurdo).
    Se descarta cualquier producto cuyo precio normalizado sea mas
    de 10 veces distinto a la mediana del grupo - es matematicamente
    imposible que sea el mismo producto real con esa diferencia.
    """
    conteo_unidades = Counter(p["unidad_normalizada"] for p in precios)
    unidad_mas_comun, cantidad_mas_comun = conteo_unidades.most_common(1)[0]
    empatado = sum(1 for _, c in conteo_unidades.items() if c == cantidad_mas_comun) > 1

    if len(conteo_unidades) == 1:
        consistentes, inconsistentes = list(precios), []
    elif empatado:
        # No hay forma de decidir la mayoria de unidad - no tocar
        # nada, ni siquiera el chequeo 2 (comparar precio_normalizado
        # entre unidades distintas -ej. "por kg" vs "por unidad"- no
        # tiene sentido, son escalas distintas por definicion).
        return list(precios), []
    else:
        consistentes = [p for p in precios if p["unidad_normalizada"] == unidad_mas_comun]
        inconsistentes = [p for p in precios if p["unidad_normalizada"] != unidad_mas_comun]

    # CHEQUEO 2: outliers de precio dentro del grupo consistente.
    if len(consistentes) >= 2:
        precios_normalizados = sorted(p["precio_normalizado"] for p in consistentes)
        mediana = precios_normalizados[len(precios_normalizados) // 2]

        aun_consistentes = []
        for p in consistentes:
            ratio = p["precio_normalizado"] / mediana if mediana > 0 else 1
            if ratio > 10 or ratio < 0.1:
                inconsistentes.append(p)
            else:
                aun_consistentes.append(p)
        consistentes = aun_consistentes

    return consistentes, inconsistentes


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
    reseteados = 0
    mayor_diferencia = None

    for ean, precios_originales in comparables.items():
        consistentes, inconsistentes = separar_consistentes_e_inconsistentes(precios_originales)

        # Resetear los inconsistentes para que se reclasifiquen solos
        # en la proxima corrida de precios_clasificar_ia.py.
        for p in inconsistentes:
            precios_db.resetear_producto_para_reclasificar(p["codigo_producto"])
            reseteados += 1

        # Con solo 1 tienda consistente (o 0, si hubo empate) no hay
        # nada que comparar ese dia - se salta, sin guardar nada raro.
        if len(consistentes) < 2:
            continue

        precios = consistentes
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
    if reseteados:
        print(f"Detectadas {reseteados} inconsistencias de normalizacion entre tiendas "
              f"(mismo EAN, distinta unidad) - reseteadas para reclasificar en la proxima corrida.")

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
