-- precios_schema.sql
--
-- Esquema de la base de datos historica de precios para Indice LCV.
-- SQLite. Se corre UNA SOLA VEZ para crear la base desde cero, y se
-- puede volver a correr despues sin riesgo (todo es IF NOT EXISTS) -
-- asi se pueden agregar tablas nuevas a una base que ya existe.
--
-- Por que varias tablas y no una sola:
-- Si guardaramos "rubro_nombre" y "tienda" como texto repetido en
-- cada fila del historico, el archivo pesaria mas de lo necesario y
-- las consultas serian mas lentas. Separando en tablas de referencia
-- (rubros, tiendas) + tablas de hechos, cada fila del historico solo
-- guarda numeros (rubro_id, tienda_id) en vez de texto repetido.
-- Mismo principio que ya usa la base de datos de LCdV (ver
-- BASE_DATOS.md).
--
-- Como correrlo (una sola vez, para crear la base, o de nuevo para
-- agregar tablas nuevas a una base existente sin perder datos):
--   sqlite3 precios_historico.db < precios_schema.sql
--
-- O desde Python:
--   python -c "import sqlite3; sqlite3.connect('precios_historico.db').executescript(open('precios_schema.sql').read())"


-- ============================================================
-- Tabla: rubros
-- Los productos de la canasta oficial (CCV). Cambia muy poco -
-- solo cuando agregamos o quitamos un rubro de la canasta.
-- ============================================================
CREATE TABLE IF NOT EXISTS rubros (
    id              INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL,
    unidad          TEXT NOT NULL          -- 'kg' | 'L' | 'unidad'
);


-- ============================================================
-- Tabla: tiendas
-- Los supermercados que comparamos. Fijo: 4 filas para siempre,
-- salvo que sumemos otro super en el futuro.
-- ============================================================
CREATE TABLE IF NOT EXISTS tiendas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL UNIQUE   -- 'La Anonima' | 'Carrefour' | 'Changomas' | 'Vea'
);


-- ============================================================
-- Tabla: historico_precios
-- El corazon de la canasta oficial. Una fila por cada (fecha, rubro,
-- tienda) que el script de busqueda diaria encontro como "el mas
-- barato". Esto es lo que alimenta precios_ultimo.json (la web).
-- ============================================================
CREATE TABLE IF NOT EXISTS historico_precios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha               DATE NOT NULL,
    rubro_id            INTEGER NOT NULL REFERENCES rubros(id),
    tienda_id           INTEGER NOT NULL REFERENCES tiendas(id),
    producto            TEXT NOT NULL,      -- nombre exacto del producto elegido ese dia
    precio_envase       REAL NOT NULL,      -- precio tal cual aparece en la gondola
    precio_normalizado  REAL,               -- precio por kg/L/unidad. NULL si no se pudo calcular
    url                 TEXT,               -- link al producto en el super
    creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Esta restriccion hace que la tabla sea "idempotente": si el
    -- script se corre dos veces el mismo dia (por error, o porque
    -- alguien lo reintenta a mano despues de una falla), la segunda
    -- corrida actualiza la fila existente en vez de crear una
    -- duplicada. Sin esto, un reintento accidental duplicaria datos
    -- y arruinaria cualquier grafico de evolucion.
    UNIQUE(fecha, rubro_id, tienda_id)
);

CREATE INDEX IF NOT EXISTS idx_historico_rubro_fecha
    ON historico_precios(rubro_id, fecha);

CREATE INDEX IF NOT EXISTS idx_historico_fecha
    ON historico_precios(fecha);


-- ============================================================
-- Tabla: historico_catalogo_completo
-- A diferencia de historico_precios (solo los productos curados
-- de la canasta oficial), esta tabla guarda TODOS los productos
-- que el scraper trae cada dia en cualquier categoria, sin filtrar.
--
-- Para que sirve: la canasta oficial de hoy solo usa una fraccion
-- de todo lo que ya scrapeamos. Guardando todo, el dia que se
-- decida sumar un rubro nuevo (o armar un buscador de precios, o
-- canastas personalizadas por Guardian) ya vamos a tener el
-- historico completo desde antes, en vez de arrancar de cero.
--
-- Esta tabla es deliberadamente "backend only": nada de esto se
-- muestra en precios.html. Solo precios_ultimo.json (armado desde
-- historico_precios) alimenta la web.
--
-- codigo_producto: identificador estable extraido de la URL del
-- producto (ver precios_db.extraer_codigo_producto). Sirve para
-- reconocer el mismo producto dia a dia aunque el nombre cambie un
-- poco (ej. un espacio, una coma). Si no se pudo extraer un codigo
-- de la URL, se usa la URL completa como fallback. Es la misma
-- clave que usa productos_maestro (abajo), asi que las dos tablas
-- se pueden cruzar con un JOIN simple.
-- ============================================================
CREATE TABLE IF NOT EXISTS historico_catalogo_completo (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha               DATE NOT NULL,
    tienda_id           INTEGER NOT NULL REFERENCES tiendas(id),
    codigo_producto      TEXT NOT NULL,
    categoria           TEXT,
    nombre              TEXT NOT NULL,
    precio              REAL NOT NULL,      -- precio tal cual viene del listado/catalogo
    precio_lista        REAL,               -- precio de lista (VTEX); NULL si no aplica/no esta
    url                 TEXT,
    creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Idempotente igual que historico_precios: si se corre dos
    -- veces el mismo dia, actualiza en vez de duplicar.
    UNIQUE(fecha, tienda_id, codigo_producto)
);

CREATE INDEX IF NOT EXISTS idx_catalogo_completo_codigo
    ON historico_catalogo_completo(codigo_producto, fecha);

CREATE INDEX IF NOT EXISTS idx_catalogo_completo_fecha
    ON historico_catalogo_completo(fecha);


-- ============================================================
-- Tabla: productos_maestro   [NUEVA - sesion 19/8/2026]
-- Un renglon POR PRODUCTO (no por dia, a diferencia de las tablas
-- de arriba). Guarda los datos que NO cambian dia a dia: marca,
-- codigo de barras (EAN), categoria asignada por IA, y la cantidad/
-- unidad normalizada para calcular precio comparable (precio/kg,
-- precio/L, etc).
--
-- Por que separada de historico_catalogo_completo: esa tabla tiene
-- una fila NUEVA cada dia por cada producto (es un historico). Si
-- guardaramos la marca/EAN ahi, se repetirian miles de veces sin
-- necesidad. Aca en cambio hay una sola fila por producto, que se
-- va completando de a poco:
--   - marca: sale gratis del scraping diario (VTEX trae "brand",
--     La Anonima trae "brand.name" en el JSON-LD de cada producto)
--   - ean: se completa por tandas (200-300 productos/dia para La
--     Anonima, que requiere 1 request extra por producto)
--   - categoria_ia, cantidad_normalizada, unidad_normalizada: los
--     completa Gemini, una sola vez por producto nuevo
-- ============================================================
CREATE TABLE IF NOT EXISTS productos_maestro (
    codigo_producto       TEXT PRIMARY KEY,
    tienda_id             INTEGER NOT NULL REFERENCES tiendas(id),
    nombre                TEXT,                -- ultimo nombre conocido
    marca                 TEXT,                -- viene del scraping (VTEX/JSON-LD), gratis
    ean                   TEXT,                -- codigo de barras, se completa por tandas
    categoria_ia          TEXT,                -- NULL hasta que Gemini la clasifique
    cantidad_normalizada  REAL,                -- NULL hasta que Gemini la calcule
    unidad_normalizada    TEXT,                -- 'kg' | 'l' | 'unidad'
    actualizado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Para buscar rapido productos de una tienda sin importar el resto
CREATE INDEX IF NOT EXISTS idx_productos_maestro_tienda
    ON productos_maestro(tienda_id);

-- Para el job de tandas: "dame productos de tal tienda sin EAN"
CREATE INDEX IF NOT EXISTS idx_productos_maestro_sin_ean
    ON productos_maestro(tienda_id, ean);

-- Para el job de Gemini: "dame productos sin categoria todavia"
CREATE INDEX IF NOT EXISTS idx_productos_maestro_sin_categoria
    ON productos_maestro(categoria_ia);


-- ============================================================
-- Datos iniciales: las 4 tiendas (fijas, se insertan una sola vez)
-- ============================================================
-- Tabla: estadisticas_categoria_diaria   [NUEVA - sesion 20/8/2026]
-- Una fila por (categoria, fecha): resume la distribucion de
-- precio_normalizado (precio/kg, precio/L o precio/unidad segun la
-- categoria) de TODOS los productos de esa categoria ese dia, en
-- las 4 tiendas juntas.
--
-- Por que una tabla aparte y no calcular todo al vuelo cada vez que
-- alguien abre el dashboard: con miles de productos por categoria y
-- pensando en graficos de evolucion historica (ej. "como vino
-- subiendo la mediana de Gaseosas en los ultimos 3 meses"), calcular
-- cuartiles on-demand cada visita seria lento. Se calcula UNA vez
-- por dia (despues de que categoria_ia y normalizacion ya estan
-- completos para el dia) y se guarda.
--
-- Sirve de base para el indice base 100 (ver arquitectura del
-- Observatorio, seccion 5.4 punto 11) - el indice se calcula sobre
-- estos valores, no hace falta una fuente de datos aparte.
--
-- producto_q1/mediana/q3: el codigo_producto real mas cercano a cada
-- cuartil ese dia (ver "producto representativo", arquitectura
-- seccion 5.4 punto 9) - permite mostrar un producto concreto como
-- ejemplo de cada segmento, no solo el numero.
-- ============================================================
CREATE TABLE IF NOT EXISTS estadisticas_categoria_diaria (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha               DATE NOT NULL,
    categoria           TEXT NOT NULL,
    cantidad_productos  INTEGER NOT NULL,   -- cuantos productos entraron en el calculo ese dia
    precio_min          REAL,
    precio_q1           REAL,
    precio_mediana      REAL,
    precio_q3           REAL,
    precio_max          REAL,
    desvio_estandar     REAL,
    producto_q1         TEXT,               -- codigo_producto mas cercano a Q1 ese dia
    producto_mediana    TEXT,               -- codigo_producto mas cercano a la mediana ese dia
    producto_q3         TEXT,               -- codigo_producto mas cercano a Q3 ese dia
    creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Idempotente: si se corre 2 veces el mismo dia, actualiza en
    -- vez de duplicar (mismo criterio que el resto de las tablas).
    UNIQUE(fecha, categoria)
);

CREATE INDEX IF NOT EXISTS idx_estadisticas_categoria_fecha
    ON estadisticas_categoria_diaria(categoria, fecha);


-- ============================================================
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('La Anonima');
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('Carrefour');
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('Changomas');
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('Vea');
