"""
analisis_dias_suben_precios.py

Analiza historico_catalogo_completo para responder: ¿que dias de la
semana / del mes suben mas los precios, y en que super?

Logica:
  1. Para cada (codigo_producto, tienda_id), se ordenan sus precios
     por fecha y se compara cada dia con el dia anterior EN QUE ESE
     MISMO PRODUCTO FUE VISTO (no asume que sea siempre el dia de
     calendario anterior -- si un producto desaparecio unos dias del
     scraping, el salto se ignora en vez de contarse como "una
     subida" falsa).
  2. Cada comparacion es una "transicion": sube, baja o queda igual.
  3. Se agrupan las transiciones por dia de semana / dia del mes del
     precio NUEVO (el dia en que se registro el cambio).
  4. El resultado clave no es "cuantas subidas hubo ese dia" sino
     "que % de las transiciones observadas ese dia fueron subida" --
     asi un dia con mas datos no parece que sube mas solo por tener
     mas observaciones.

Uso:
    python3 analisis_dias_suben_precios.py \
        --db /home/lcv/indice-lcv/precios_historico.db \
        --dias 180 \
        --salida-csv resumen_dias_suben.csv

Requiere: pandas
"""

import argparse
import sqlite3
from datetime import date, timedelta

import pandas as pd

DIAS_SEMANA_ES = {
    0: "Lunes", 1: "Martes", 2: "Miercoles", 3: "Jueves",
    4: "Viernes", 5: "Sabado", 6: "Domingo",
}


def cargar_datos(db_path: str, dias_atras: int, fecha_desde_manual: str = None) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    fecha_desde = fecha_desde_manual or (date.today() - timedelta(days=dias_atras)).isoformat()

    query = """
        SELECT
            h.fecha,
            h.tienda_id,
            t.nombre AS tienda_nombre,
            h.codigo_producto,
            h.nombre AS producto_nombre,
            h.precio,
            h.precio_lista
        FROM historico_catalogo_completo h
        JOIN tiendas t ON t.id = h.tienda_id
        WHERE h.fecha >= ?
        ORDER BY h.tienda_id, h.codigo_producto, h.fecha
    """
    df = pd.read_sql_query(query, con, params=(fecha_desde,))
    con.close()

    if df.empty:
        raise SystemExit(
            f"No hay datos en historico_catalogo_completo desde {fecha_desde}. "
            "Revisa la ruta de la base o el parametro --dias."
        )

    df["fecha"] = pd.to_datetime(df["fecha"])

    # precio_lista es el precio "de lista" (sin promocion) en VTEX.
    # precio puede incluir descuentos temporales que entran y salen
    # de un dia a otro y generan subidas/bajadas falsas que no son
    # ajustes reales -- por eso preferimos precio_lista cuando esta
    # disponible, y solo caemos a precio si no lo tiene (ej. La
    # Anonima, que no es VTEX).
    df["precio_efectivo"] = df["precio_lista"].fillna(df["precio"])

    return df


def calcular_transiciones(df: pd.DataFrame) -> pd.DataFrame:
    """Por cada (tienda_id, codigo_producto), compara cada precio con
    el precio anterior de ESE MISMO producto en ESA MISMA tienda.
    Devuelve una fila por transicion (no por precio absoluto)."""

    df = df.sort_values(["tienda_id", "codigo_producto", "fecha"])

    grupo = df.groupby(["tienda_id", "codigo_producto"], sort=False)
    df["precio_anterior"] = grupo["precio_efectivo"].shift(1)
    df["fecha_anterior"] = grupo["fecha"].shift(1)

    # Descartamos la primera aparicion de cada producto (no tiene
    # "anterior" con el cual compararse).
    transiciones = df.dropna(subset=["precio_anterior"]).copy()

    transiciones["variacion_pct"] = (
        (transiciones["precio_efectivo"] - transiciones["precio_anterior"])
        / transiciones["precio_anterior"] * 100
    )
    transiciones["subio"] = transiciones["variacion_pct"] > 0
    transiciones["bajo"] = transiciones["variacion_pct"] < 0

    transiciones["dia_semana_num"] = transiciones["fecha"].dt.weekday
    transiciones["dia_semana"] = transiciones["dia_semana_num"].map(DIAS_SEMANA_ES)
    transiciones["dia_mes"] = transiciones["fecha"].dt.day

    return transiciones


def resumen_por_dia_semana(transiciones: pd.DataFrame, por_tienda: bool = False) -> pd.DataFrame:
    claves = ["dia_semana_num", "dia_semana"]
    if por_tienda:
        claves = ["tienda_nombre"] + claves

    resumen = transiciones.groupby(claves).agg(
        transiciones_totales=("subio", "count"),
        subidas=("subio", "sum"),
        variacion_pct_promedio_subidas=(
            "variacion_pct", lambda s: s[s > 0].mean()
        ),
        variacion_pct_mediana_subidas=(
            "variacion_pct", lambda s: s[s > 0].median()
        ),
    ).reset_index()

    resumen["pct_transiciones_que_suben"] = (
        resumen["subidas"] / resumen["transiciones_totales"] * 100
    ).round(2)
    resumen["variacion_pct_promedio_subidas"] = resumen["variacion_pct_promedio_subidas"].round(2)
    resumen["variacion_pct_mediana_subidas"] = resumen["variacion_pct_mediana_subidas"].round(2)

    orden = ["tienda_nombre"] if por_tienda else []
    resumen = resumen.sort_values(orden + ["dia_semana_num"])
    return resumen.drop(columns=["dia_semana_num"])


def resumen_por_dia_mes(transiciones: pd.DataFrame, por_tienda: bool = False) -> pd.DataFrame:
    claves = ["dia_mes"]
    if por_tienda:
        claves = ["tienda_nombre"] + claves

    resumen = transiciones.groupby(claves).agg(
        transiciones_totales=("subio", "count"),
        subidas=("subio", "sum"),
        variacion_pct_promedio_subidas=(
            "variacion_pct", lambda s: s[s > 0].mean()
        ),
        variacion_pct_mediana_subidas=(
            "variacion_pct", lambda s: s[s > 0].median()
        ),
    ).reset_index()

    resumen["pct_transiciones_que_suben"] = (
        resumen["subidas"] / resumen["transiciones_totales"] * 100
    ).round(2)
    resumen["variacion_pct_promedio_subidas"] = resumen["variacion_pct_promedio_subidas"].round(2)
    resumen["variacion_pct_mediana_subidas"] = resumen["variacion_pct_mediana_subidas"].round(2)

    orden = ["tienda_nombre"] if por_tienda else []
    resumen = resumen.sort_values(orden + ["dia_mes"])
    return resumen


def imprimir_top(resumen: pd.DataFrame, columna_dia: str, titulo: str, n: int = 5):
    print(f"\n=== {titulo} ===")
    top = resumen.sort_values("pct_transiciones_que_suben", ascending=False).head(n)
    for _, fila in top.iterrows():
        tienda = f"[{fila['tienda_nombre']}] " if "tienda_nombre" in fila else ""
        print(
            f"{tienda}{fila[columna_dia]}: "
            f"{fila['pct_transiciones_que_suben']}% de las veces sube "
            f"(n={int(fila['transiciones_totales'])}, "
            f"promedio {fila['variacion_pct_promedio_subidas']}%, "
            f"mediana {fila['variacion_pct_mediana_subidas']}%)"
        )


def main():
    ap = argparse.ArgumentParser(description="Analiza que dias suben mas los precios.")
    ap.add_argument("--db", required=True, help="Ruta a precios_historico.db")
    ap.add_argument("--dias", type=int, default=180, help="Ventana de dias hacia atras a analizar (default 180). Ignorado si se pasa --fecha-desde.")
    ap.add_argument("--fecha-desde", default=None, help="Fecha exacta de inicio (YYYY-MM-DD), para evitar mezclar con periodos donde el catalogo tenia menos productos. Si se pasa, ignora --dias.")
    ap.add_argument("--salida-csv", default=None, help="Si se pasa, guarda el resumen por dia de semana y tienda en este CSV")
    args = ap.parse_args()

    print(f"Cargando historico_catalogo_completo (desde {args.fecha_desde or f'{args.dias} dias atras'})...")
    df = cargar_datos(args.db, args.dias, args.fecha_desde)
    print(f"{len(df):,} filas cargadas.")

    transiciones = calcular_transiciones(df)
    print(f"{len(transiciones):,} transiciones de precio calculadas (producto visto 2+ veces).")

    # --- General (todas las tiendas juntas) ---
    resumen_semana_general = resumen_por_dia_semana(transiciones, por_tienda=False)
    resumen_mes_general = resumen_por_dia_mes(transiciones, por_tienda=False)

    imprimir_top(resumen_semana_general, "dia_semana", "Dias de la semana que MAS suben (todas las tiendas)")
    imprimir_top(resumen_mes_general, "dia_mes", "Dias del mes que MAS suben (todas las tiendas)", n=7)

    # --- Por tienda ---
    resumen_semana_tienda = resumen_por_dia_semana(transiciones, por_tienda=True)
    print("\n=== Detalle por dia de semana y tienda ===")
    print(resumen_semana_tienda.to_string(index=False))

    if args.salida_csv:
        resumen_semana_tienda.to_csv(args.salida_csv, index=False)
        print(f"\nGuardado: {args.salida_csv}")


if __name__ == "__main__":
    main()
