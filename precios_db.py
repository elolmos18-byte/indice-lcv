"""
precios_db.py

Modulo de acceso a precios_historico.db. Ningun otro script escribe
SQL directo - todo pasa por las funciones de aca, igual que en LCdV
el bot nunca toca la base directamente y todo pasa por la API.

Funciones para la canasta oficial (curada, lo que se ve en la web):
- poblar_rubros(archivo_rubros)         -> llena la tabla rubros
- guardar_foto_dia(fecha, resultados)   -> guarda los precios de un dia
- obtener_historico(rubro_id, ...)      -> consulta evolucion en el tiempo
- obtener_ultima_fecha()                -> la fecha mas reciente con datos
- obtener_resumen_dia(fecha)            -> reconstruye un dia completo

Funciones para el catalogo completo (backend, no se muestra en la
web - ver precios_schema.sql, tabla historico_catalogo_completo):
- extraer_codigo_producto(url)          -> codigo estable de un producto
- guardar_catalogo_completo(fecha, productos) -> guarda TODO lo scrapeado

Funciones para productos_maestro (backend, datos ESTATICOS por
producto - marca, EAN, categoria IA, normalizacion. Ver
precios_schema.sql para el porque de esta tabla separada del
historico diario) [NUEVO - sesion 19/8/2026]:
- upsert_producto_maestro(...)          -> crea/actualiza fila basica (auto, desde el scraping)
- guardar_ean(...)                      -> guarda EAN de un producto (job de tandas)
- guardar_clasificacion_ia(...)         -> guarda categoria+normalizacion de Gemini
- obtener_productos_sin_ean(...)        -> productos pendientes de EAN (para el job de tandas)
- obtener_productos_sin_clasificar(...) -> productos pendientes de clasificar (para el job de Gemini)

Como se usa desde precios_buscar_canasta.py:

    import precios_db

    precios_db.poblar_rubros("precios_canasta_rubros.json")
    precios_db.guardar_foto_dia(fecha, resultados_por_rubro)

Archivo de base de datos: precios_historico.db (en el mismo directorio
donde se ejecuta el script). Se crea con precios_schema.sql antes de
usar este modulo por primera vez.
"""

import json
import re
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
    """Busca el id de una tienda por su nombre. Las tiendas ya
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
    los supers. Util para graficos de evolucion.

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


def obtener_fecha_anterior(fecha_actual: str) -> str | None:
    """
    Devuelve la fecha mas reciente guardada en el historico que sea
    ANTERIOR a fecha_actual, o None si no hay ninguna (primera
    corrida). Sirve para saber contra que dia comparar y calcular si
    un precio subio, bajo o quedo igual (ver tendencia en la web).
    """
    with _conectar() as conn:
        fila = conn.execute(
            "SELECT MAX(fecha) FROM historico_precios WHERE fecha < ?",
            (fecha_actual,),
        ).fetchone()

    return fila[0] if fila and fila[0] else None


def obtener_precios_fecha(fecha: str) -> dict:
    """
    Devuelve todos los precios_normalizado guardados para una fecha
    puntual, como un diccionario facil de consultar:

        {(rubro_id, "Carrefour"): 819.0, (rubro_id, "La Anonima"): 1100.0, ...}

    Pensado para comparar "hoy" contra "la corrida anterior" sin
    tener que reconstruir todo el resumen del dia (a diferencia de
    obtener_resumen_dia, que devuelve mas datos de los que hacen
    falta solo para comparar precios).
    """
    with _conectar() as conn:
        filas = conn.execute(
            """
            SELECT hp.rubro_id, t.nombre AS tienda, hp.precio_normalizado
            FROM historico_precios hp
            JOIN tiendas t ON t.id = hp.tienda_id
            WHERE hp.fecha = ?
            """,
            (fecha,),
        ).fetchall()

    return {(rubro_id, tienda): pn for rubro_id, tienda, pn in filas}


def obtener_rubros() -> list[dict]:
    """
    Devuelve la lista completa de rubros de la canasta (id, nombre,
    unidad), ordenada por id. Pensada para poblar selectores en la
    web (ej. el dropdown de "elegir producto" del dashboard) sin
    tener que leer el .json de rubros por separado.
    """
    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            "SELECT id, nombre, unidad FROM rubros ORDER BY id"
        ).fetchall()

    return [dict(fila) for fila in filas]


def obtener_evolucion_totales() -> dict:
    """
    Devuelve la evolucion del total de la canasta por tienda, dia a
    dia, sumando el precio_normalizado de todos los rubros
    disponibles ese dia para esa tienda. Pensada para el grafico de
    "quien fue mas barato a lo largo del tiempo" del dashboard.

    Solo suma rubros con precio_normalizado valido (no NULL) - un
    rubro faltante ese dia simplemente no se cuenta, en vez de
    reventar el total con un cero falso.

    Devuelve:
        {
            "fechas": ["2026-07-01", "2026-07-03", ...],
            "por_tienda": {
                "La Anonima": [62972.0, 63500.0, ...],
                "Carrefour": [55000.0, null, ...],   // null = sin datos ese dia
                ...
            }
        }
    """
    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            """
            SELECT hp.fecha, t.nombre AS tienda,
                   SUM(hp.precio_normalizado) AS total,
                   COUNT(*) AS rubros_contados
            FROM historico_precios hp
            JOIN tiendas t ON t.id = hp.tienda_id
            WHERE hp.precio_normalizado IS NOT NULL
            GROUP BY hp.fecha, t.nombre
            ORDER BY hp.fecha ASC
            """
        ).fetchall()

    fechas = sorted({fila["fecha"] for fila in filas})
    tiendas = sorted({fila["tienda"] for fila in filas})

    indice_fecha = {fecha: i for i, fecha in enumerate(fechas)}
    por_tienda = {tienda: [None] * len(fechas) for tienda in tiendas}

    for fila in filas:
        i = indice_fecha[fila["fecha"]]
        por_tienda[fila["tienda"]][i] = round(fila["total"], 2)

    return {"fechas": fechas, "por_tienda": por_tienda}


def obtener_evolucion_todos_los_rubros() -> dict:
    """
    Devuelve, para CADA rubro, su evolucion de precio_normalizado por
    tienda a lo largo del tiempo - todo junto en una sola consulta,
    para no golpear la base una vez por rubro.

    Devuelve:
        {
            "1": {
                "La Anonima": [{"fecha": "2026-07-01", "precio": 1100.0}, ...],
                "Carrefour": [...],
                ...
            },
            "2": { ... },
            ...
        }
    """
    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            """
            SELECT hp.rubro_id, hp.fecha, t.nombre AS tienda,
                   hp.precio_normalizado
            FROM historico_precios hp
            JOIN tiendas t ON t.id = hp.tienda_id
            WHERE hp.precio_normalizado IS NOT NULL
            ORDER BY hp.rubro_id, hp.fecha ASC
            """
        ).fetchall()

    resultado: dict = {}
    for fila in filas:
        rubro_id = str(fila["rubro_id"])
        resultado.setdefault(rubro_id, {})
        resultado[rubro_id].setdefault(fila["tienda"], [])
        resultado[rubro_id][fila["tienda"]].append({
            "fecha": fila["fecha"],
            "precio": round(fila["precio_normalizado"], 2),
        })

    return resultado


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


# ============================================================
# Catalogo completo (backend, no se muestra en la web)
#
# A diferencia de las funciones de arriba (que trabajan sobre la
# canasta oficial curada), estas guardan TODO lo que el scraper
# trae cada dia, sin filtrar - ver precios_schema.sql para el
# porque de esta tabla separada.
# ============================================================

def extraer_codigo_producto(url: str) -> str:
    """
    Saca un codigo identificador estable a partir de la URL de un
    producto, para poder reconocer "es el mismo producto" dia a dia
    aunque el nombre cambie un poco (un espacio, una coma, un typo
    corregido).

    La Anonima:  .../algo-x-500-g/art_2318246/   -> "anonima_2318246"
    Carrefour:   .../algo-720108/p                -> "vtex_720108"

    Changomas (masonline) es un caso especial: muchas de sus URLs
    terminan en un numero CORTO que no es un codigo de producto, sino
    un simple sufijo de desambiguacion del sitio (ej. "...-290g-2/p",
    "...-400-g-2/p" - el "2" se repite en cientos de productos sin
    relacion entre si). Si confiaramos en ese numero como codigo,
    productos distintos terminarian pisandose unos a otros en la
    base. Por eso, si el numero encontrado tiene menos de 4 digitos,
    lo descartamos y usamos la URL completa como respaldo - menos
    prolijo, pero no genera colisiones falsas.
    """
    if not url:
        return "sin_url"

    m = re.search(r"art_(\d+)", url)
    if m:
        return f"anonima_{m.group(1)}"

    m = re.search(r"-(\d+)/p$", url)
    if m:
        numero = m.group(1)
        if len(numero) >= 4:
            return f"vtex_{numero}"

    return url


def guardar_catalogo_completo(fecha: str, productos: list[dict]) -> int:
    """
    Guarda en historico_catalogo_completo TODOS los productos de una
    corrida (no solo los de la canasta oficial).

    Cada producto en la lista debe tener:
        {
            "tienda": "La Anonima" | "Carrefour" | "Changomas" | "Vea",
            "categoria": "carniceria" (puede venir vacio),
            "nombre": "Carne Picada Best x 500 g.",
            "precio": 7980.0,
            "precio_lista": 7980.0 (opcional, None si no aplica),
            "url": "https://...",
            "marca": "Best" (opcional, None si no viene - VTEX la trae,
                              La Anonima no la trae en el listado hoy),
        }

    Es idempotente igual que guardar_foto_dia: si se corre dos veces
    el mismo dia, actualiza en vez de duplicar (usa fecha + tienda +
    codigo_producto como clave).

    Ademas de guardar el historico diario, cada producto alimenta
    automaticamente productos_maestro (crea la fila si no existe, o
    actualiza nombre/marca si cambiaron) - ver upsert_producto_maestro.
    Esto NO pisa ean/categoria_ia/normalizacion, que se completan por
    procesos aparte.

    Devuelve la cantidad de filas insertadas/actualizadas.
    """
    filas_procesadas = 0

    with _conectar() as conn:
        for prod in productos:
            tienda_id = _id_tienda(conn, prod["tienda"])
            codigo = extraer_codigo_producto(prod.get("url", ""))

            conn.execute(
                """
                INSERT INTO historico_catalogo_completo
                    (fecha, tienda_id, codigo_producto, categoria,
                     nombre, precio, precio_lista, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fecha, tienda_id, codigo_producto) DO UPDATE SET
                    categoria = excluded.categoria,
                    nombre = excluded.nombre,
                    precio = excluded.precio,
                    precio_lista = excluded.precio_lista,
                    url = excluded.url
                """,
                (
                    fecha,
                    tienda_id,
                    codigo,
                    prod.get("categoria", ""),
                    prod["nombre"],
                    prod["precio"],
                    prod.get("precio_lista"),
                    prod.get("url", ""),
                ),
            )
            filas_procesadas += 1

            # Alimenta productos_maestro con lo que ya tenemos gratis
            # del scraping (nombre, marca). EAN/categoria_ia/
            # normalizacion se completan despues, por procesos aparte.
            #
            # OJO: se le pasa conn=conn (la misma conexion abierta de
            # este for) para NO abrir una segunda conexion aca adentro
            # - eso causaba "database is locked" (ver docstring de
            # upsert_producto_maestro).
            upsert_producto_maestro(
                codigo_producto=codigo,
                tienda_id=tienda_id,
                nombre=prod["nombre"],
                marca=prod.get("marca"),
                conn=conn,
            )

        conn.commit()

    return filas_procesadas


def obtener_historico_producto(
    codigo_producto: str, desde: str | None = None, hasta: str | None = None
) -> list[dict]:
    """
    Devuelve la evolucion de precios de UN producto puntual en el
    tiempo (identificado por su codigo estable, ver
    extraer_codigo_producto).

    Devuelve una lista de dicts:
        [
            {"fecha": "2026-06-24", "tienda": "La Anonima",
             "nombre": "...", "precio": 7980.0, "precio_lista": None,
             "categoria": "carniceria", "url": "..."},
            ...
        ]
    """
    condiciones = ["hc.codigo_producto = ?"]
    parametros = [codigo_producto]

    if desde:
        condiciones.append("hc.fecha >= ?")
        parametros.append(desde)

    if hasta:
        condiciones.append("hc.fecha <= ?")
        parametros.append(hasta)

    where = " AND ".join(condiciones)

    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            f"""
            SELECT hc.fecha, t.nombre AS tienda, hc.nombre,
                   hc.precio, hc.precio_lista, hc.categoria, hc.url
            FROM historico_catalogo_completo hc
            JOIN tiendas t ON t.id = hc.tienda_id
            WHERE {where}
            ORDER BY hc.fecha ASC
            """,
            parametros,
        ).fetchall()

    return [dict(fila) for fila in filas]


# ============================================================
# productos_maestro: datos ESTATICOS por producto (marca, EAN,
# categoria IA, normalizacion). Un renglon por producto, no por dia
# - ver precios_schema.sql para el porque de esta tabla separada
# del historico diario.  [NUEVO - sesion 19/8/2026]
# ============================================================

def _upsert_producto_maestro_sql(
    conn: sqlite3.Connection,
    codigo_producto: str,
    tienda_id: int,
    nombre: str,
    marca: str | None,
) -> None:
    """
    Ejecuta el INSERT/UPDATE de productos_maestro sobre una conexion
    YA ABIERTA que me pasan (no abre ni cierra nada, no hace commit -
    eso lo maneja quien la llama). Separada de upsert_producto_maestro
    para poder reusarla desde adentro de guardar_catalogo_completo sin
    abrir una segunda conexion (ver comentario mas abajo, bug de
    'database is locked' encontrado el 19/8/2026).
    """
    conn.execute(
        """
        INSERT INTO productos_maestro (codigo_producto, tienda_id, nombre, marca)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(codigo_producto) DO UPDATE SET
            nombre = excluded.nombre,
            marca = COALESCE(excluded.marca, productos_maestro.marca),
            actualizado_en = CURRENT_TIMESTAMP
        """,
        (codigo_producto, tienda_id, nombre, marca),
    )


def upsert_producto_maestro(
    codigo_producto: str,
    tienda_id: int,
    nombre: str,
    marca: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """
    Crea o actualiza la fila basica de un producto en productos_maestro.

    A proposito NO toca ean/categoria_ia/cantidad_normalizada/
    unidad_normalizada - esos campos los completan procesos aparte
    (tandas de EAN, clasificacion con Gemini) y no queremos que una
    corrida diaria de scraping los pise con NULL por accidente. Por
    eso el UPDATE usa COALESCE en marca (si el scraping no trae marca
    esta vez, se conserva la que ya estaba guardada).

    Parametro `conn` [agregado 19/8/2026, fix de bug]: si se llama a
    esta funcion SOLA (por ejemplo desde una consola de prueba), abre
    su propia conexion y hace commit, como cualquier otra funcion de
    este modulo. Pero si se llama desde ADENTRO de otra funcion que ya
    tiene una conexion abierta con cambios sin confirmar (como
    guardar_catalogo_completo, que llama a esto una vez por producto
    en un loop) hay que pasarle esa misma conexion con `conn=...` -
    SQLite no permite que una segunda conexion escriba mientras la
    primera tiene una transaccion abierta sobre el mismo archivo, y
    abrir una nueva ahi adentro producia "database is locked".
    """
    if conn is not None:
        _upsert_producto_maestro_sql(conn, codigo_producto, tienda_id, nombre, marca)
        return

    with _conectar() as conn_propia:
        _upsert_producto_maestro_sql(conn_propia, codigo_producto, tienda_id, nombre, marca)
        conn_propia.commit()


def guardar_ean(codigo_producto: str, ean: str) -> None:
    """
    Guarda el EAN de un producto puntual. Pensado para el job de
    tandas de La Anonima (200-300 productos/dia, ver
    obtener_productos_sin_ean).
    """
    with _conectar() as conn:
        conn.execute(
            """
            UPDATE productos_maestro
            SET ean = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo_producto = ?
            """,
            (ean, codigo_producto),
        )
        conn.commit()


def guardar_clasificacion_ia(
    codigo_producto: str,
    categoria_ia: str,
    cantidad_normalizada: float | None,
    unidad_normalizada: str | None,
) -> None:
    """
    Guarda el resultado de Gemini (categoria + normalizacion) para
    un producto puntual. Pensado para el job diario que clasifica
    productos nuevos (ver obtener_productos_sin_clasificar).
    """
    with _conectar() as conn:
        conn.execute(
            """
            UPDATE productos_maestro
            SET categoria_ia = ?, cantidad_normalizada = ?,
                unidad_normalizada = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo_producto = ?
            """,
            (categoria_ia, cantidad_normalizada, unidad_normalizada, codigo_producto),
        )
        conn.commit()


def obtener_productos_sin_ean(tienda_nombre: str, limite: int = 250) -> list[dict]:
    """
    Devuelve hasta `limite` productos de una tienda que todavia no
    tienen EAN guardado. Pensado para el job de tandas de La Anonima
    (200-300 productos/dia) - cada corrida retoma donde quedo la
    anterior, sin repetir productos ya completados.

    Devuelve:
        [{"codigo_producto": "anonima_2318246", "nombre": "..."}, ...]
    """
    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            """
            SELECT pm.codigo_producto, pm.nombre
            FROM productos_maestro pm
            JOIN tiendas t ON t.id = pm.tienda_id
            WHERE t.nombre = ? AND (pm.ean IS NULL OR pm.ean = '')
            ORDER BY pm.codigo_producto
            LIMIT ?
            """,
            (tienda_nombre, limite),
        ).fetchall()

    return [dict(fila) for fila in filas]


def obtener_productos_sin_clasificar(limite: int = 500) -> list[dict]:
    """
    Devuelve hasta `limite` productos que todavia no tienen
    categoria_ia asignada (de cualquier tienda). Pensado para el job
    diario que le manda productos nuevos a Gemini (categoria +
    normalizacion).

    Devuelve:
        [{"codigo_producto": "vtex_720108", "nombre": "..."}, ...]
    """
    with _conectar() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute(
            """
            SELECT codigo_producto, nombre
            FROM productos_maestro
            WHERE categoria_ia IS NULL
            ORDER BY codigo_producto
            LIMIT ?
            """,
            (limite,),
        ).fetchall()

    return [dict(fila) for fila in filas]
