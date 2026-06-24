-- precios_schema.sql
--
-- Esquema de la base de datos historica de precios para Indice LCV.
-- SQLite. Se corre UNA SOLA VEZ para crear la base desde cero.
--
-- Por que 3 tablas y no una sola:
-- Si guardaramos "rubro_nombre" y "tienda" como texto repetido en
-- cada fila del historico, el archivo pesaria mas de lo necesario y
-- las consultas serian mas lentas. Separando en tablas de referencia
-- (rubros, tiendas) + una tabla de hechos (historico_precios), cada
-- fila del historico solo guarda numeros (rubro_id, tienda_id) en
-- vez de texto repetido. Mismo principio que ya usa la base de datos
-- de LCdV (ver BASE_DATOS.md).
--
-- Como correrlo (una sola vez, para crear la base):
--   sqlite3 precios_historico.db < precios_schema.sql
--
-- O desde Python:
--   python -c "import sqlite3; sqlite3.connect('precios_historico.db').executescript(open('precios_schema.sql').read())"


-- ============================================================
-- Tabla: rubros
-- Los 37 productos de la canasta CCV-37. Cambia muy poco -
-- solo cuando agregamos o quitamos un rubro de la canasta.
-- ============================================================
CREATE TABLE IF NOT EXISTS rubros (
    id              INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL,
    unidad          TEXT NOT NULL          -- 'kg' | 'L' | 'unidad'
);


-- ============================================================
-- Tabla: tiendas
-- Los supermercados que comparamos. Fijo: 3 filas para siempre,
-- salvo que sumemos un cuarto super en el futuro.
-- ============================================================
CREATE TABLE IF NOT EXISTS tiendas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL UNIQUE   -- 'La Anonima' | 'Carrefour' | 'Changomas'
);


-- ============================================================
-- Tabla: historico_precios
-- El corazon de la base. Una fila por cada (fecha, rubro, tienda)
-- que el script de busqueda diaria encontro.
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

-- Indices para que las consultas de "evolucion de un rubro en el
-- tiempo" y "todos los precios de una fecha" sean rapidas, incluso
-- con miles de filas acumuladas con el tiempo.
CREATE INDEX IF NOT EXISTS idx_historico_rubro_fecha
    ON historico_precios(rubro_id, fecha);

CREATE INDEX IF NOT EXISTS idx_historico_fecha
    ON historico_precios(fecha);


-- ============================================================
-- Datos iniciales: las 3 tiendas (fijas, se insertan una sola vez)
-- ============================================================
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('La Anonima');
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('Carrefour');
INSERT OR IGNORE INTO tiendas (nombre) VALUES ('Changomas');
