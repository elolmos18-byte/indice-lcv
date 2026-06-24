"""
precios_db.py

Modulo de acceso a precios_historico.db. Ningun otro script escribe
SQL directo - todo pasa por las funciones de aca, igual que en LCdV
el bot nunca toca la base directamente y todo pasa por la API.

Funciones:
- poblar_rubros(archivo_rubros)         -> llena la tabla rubros
- guardar_foto_dia(fecha, resultados)   -> guarda los precios de un dia
- obtener_historico(rubro_id, ...)      -> consulta evolucion en el tiempo
- obtener_ultima_fecha()                -> la fecha mas reciente con datos

Como se usa desde precios_buscar_canasta.py:

    import precios_db

    precios_db.poblar_rubros("precios_canasta_rubros.json")
    precios_db.guardar_foto_dia(fecha, resultados_por_rubro)

Archivo de base de datos: precios_historico.db (en el mismo directorio
donde se ejecuta el script). Se crea con precios_schema.sql antes de
usar este modulo por primera vez.
"""

import json
import sqlite3
from pathlib import Path

ARCHIVO_DB = "precios_historico.db"


def _conectar() -> sqlite3.Connection:
    """
    Abre una conexion a la base. Se usa adentro de un 'with' en cada
    funcion para que la conexion se cierre sola, incluso si algo
    falla a mitad de camino.
    """
    return sqlite3.connect(ARCHIVO_DB)


def poblar_rubros(archivo_rubros: str = "precios_canasta_rubros.json") -> int:
    """
    Lee la definicion de rubros desde el JSON y los inserta (o
    actualiza) en la tabla rubros. Se puede correr las veces que sea
    necesario - si un rubro ya existe, actualiza su nombre/unidad en
    vez de duplicarlo.

    Devuelve la cantidad de rubros procesados.
    """
    with open(archivo_rubros, encoding="utf-8") as f:
        data = json.load(f)

    rubros = data["rubros"]

    with _conectar() as conn:
        for rubro in rubros:
            conn.execute(
                """
                INSERT INTO rubros (id, nombre, unidad)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    nombre = excluded.nombre,
                    unidad = excluded.unidad
                """,
                (rubro["id"], rubro["nombre"], rubro.get("unidad", "")),
            )
        conn.commit()

    return len(rubros)


def _id_tienda(conn: sqlite3.Connection, nombre_tienda: str) -> int:
    """Busca el id de una tienda por su nombre. Las 3 tiendas ya
    estan insertadas por precios_schema.sql, asi que esto siempre
    deberia encontrar algo."""
    fila = conn.execute(
        "SELECT id FROM tiendas WHERE nombre = ?", (nombre_tienda,)
    ).fetchone()

    if fila is None:
        raise ValueError(
            f"Tienda '{nombre_tienda}' no existe en la tabla tiendas. "
            f"Revisar precios_schema.sql o el nombre exacto usado."
        )

    return fila[0]


def guardar_foto_dia(fecha: str, resultados_por_rubro: list[dict]) -> int:
    """
    Guarda en historico_precios los precios encontrados un dia
    determinado.

    resultados_por_rubro tiene esta forma (la misma que ya arma
    precios_buscar_canasta.py para el resumen en consola):

        [
            {
                "rubro_id": 1,
                "rubro_nombre": "Harina 000",
                "precios": {
                    "La Anonima": {
                        "nombre": "Harina de Trigo 000 Morixe x 1 Kg.",
                        "precio": 690.0,
                        "precio_normalizado": 690.0,
                        "url": "https://..."
                    },
                    "Carrefour": { ... },
                    "Changomas": { ... }
                }
            },
            ...
        ]

    Es idempotente: si ya hay una fila para (fecha, rubro_id, tienda_id),
    la actualiza en vez de duplicarla. Esto permite re-correr el script
    el mismo dia sin generar filas repetidas.

    Devuelve la cantidad de filas insertadas/actualizadas.
    """
    filas_procesadas = 0

    with _conectar() as conn:
        for dato in resultados_por_rubro:
            rubro_id = dato["rubro_id"]

            for tienda_nombre, info in dato["precios"].items():
                tienda_id = _id_tienda(conn, tienda_nombre)

                conn.execute(
                    """
                    INSERT INTO historico_precios
                        (fecha, rubro_id, tienda_id, producto,
                         precio_envase, precio_normalizado, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fecha, rubro_id, tienda_id) DO UPDATE SET
                        producto = excluded.producto,
                        precio_envase = excluded.precio_envase,
                        precio_normalizado = excluded.precio_normalizado,
                        url = excluded.url
                    """,
                    (
                        fecha,
                        rubro_id,
                        tienda_id,
                        info["nombre"],
                        info["precio"],
                        info.get("precio_normalizado"),
                        info.get("url", ""),
                    ),
                )
                filas_procesadas += 1

        conn.commit()

    return filas_procesadas


def obtener_historico(
    rubro_id: int, desde: str | None = None, hasta: str | None = None
) -> list[dict]:
    """
    Devuelve la evolucion de precios de un rubro en el tiempo, para
    los 3 supers. Util para graficos de evolucion (pendiente de usar
    todavia, pero la funcion ya queda lista).

    desde/hasta son fechas en formato 'YYYY-MM-DD'. Si se omiten,
    devuelve todo el historico disponible para ese rubro.

    Devuelve una lista de dicts:
        [
            {"fecha": "2026-06-24", "tienda": "La Anonima",
             "producto": "...", "precio_envase": 690.0,
             "precio_normalizado": 690.0, "url": "..."},
            ...
        ]
    """
    condiciones = ["hp.rubro_id = ?"]
    parametros = [rubro_id]

    if desde:
        condiciones.append("hp.fecha >= ?")
        parametros.append(desde)

    if hasta:
        condiciones.append("hp.fecha <= ?")
        parametros.append(hasta)

    where = " AND ".join(condiciones)

    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            f"""
            SELECT hp.fecha, t.nombre AS tienda, hp.producto,
                   hp.precio_envase, hp.precio_normalizado, hp.url
            FROM historico_precios hp
            JOIN tiendas t ON t.id = hp.tienda_id
            WHERE {where}
            ORDER BY hp.fecha ASC, t.nombre ASC
            """,
            parametros,
        ).fetchall()

    return [dict(fila) for fila in filas]


def obtener_ultima_fecha() -> str | None:
    """
    Devuelve la fecha mas reciente que tiene datos en el historico,
    o None si la tabla esta vacia. Util para que la pagina web sepa
    cual es el ultimo dia con informacion.
    """
    with _conectar() as conn:
        fila = conn.execute(
            "SELECT MAX(fecha) FROM historico_precios"
        ).fetchone()

    return fila[0] if fila else None


def obtener_resumen_dia(fecha: str) -> list[dict]:
    """
    Devuelve todos los precios guardados para una fecha puntual,
    organizados por rubro. Pensado para reconstruir el JSON de la
    pagina web a partir de la base, si alguna vez se necesita
    regenerar precios_ultimo.json sin volver a scrapear.
    """
    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            """
            SELECT r.id AS rubro_id, r.nombre AS rubro_nombre, r.unidad,
                   t.nombre AS tienda, hp.producto,
                   hp.precio_envase, hp.precio_normalizado, hp.url
            FROM historico_precios hp
            JOIN rubros r ON r.id = hp.rubro_id
            JOIN tiendas t ON t.id = hp.tienda_id
            WHERE hp.fecha = ?
            ORDER BY r.id ASC, t.nombre ASC
            """,
            (fecha,),
        ).fetchall()

    return [dict(fila) for fila in filas]
