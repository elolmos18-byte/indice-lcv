#!/bin/bash
#
# precios_corrida_diaria.sh
#
# Encadena los 3 pasos de la actualizacion diaria de precios:
#   1. Scrapea La Anonima       -> catalogo_anonima.csv
#   2. Scrapea Carrefour+Chango -> catalogo_vtex.csv
#   3. Busca el mas barato      -> CSV + JSON web + base de datos
#
# Pensado para ser llamado por cron, dos veces al dia. La base de
# datos es idempotente (ver precios_schema.sql, UNIQUE(fecha,
# rubro_id, tienda_id)) - si la corrida de la tarde encuentra datos
# de la mañana, los actualiza en vez de duplicarlos. Asi queda
# guardado el precio de la ULTIMA corrida exitosa del dia.
#
# Si algun paso falla, el script se detiene ahi (set -e) y no sigue
# con los pasos siguientes - mejor no actualizar nada a actualizar
# con datos a medio generar.
#
# Todo lo que imprime cada paso queda en el log, con fecha y hora,
# para poder revisar despues si algo fallo durante la noche.

set -e  # si cualquier comando falla, el script se detiene aca

cd /home/lcv/indice-lcv

ARCHIVO_LOG="log_corrida.txt"

echo "" >> "$ARCHIVO_LOG"
echo "========================================" >> "$ARCHIVO_LOG"
echo "Corrida iniciada: $(date '+%Y-%m-%d %H:%M:%S')" >> "$ARCHIVO_LOG"
echo "========================================" >> "$ARCHIVO_LOG"

echo "--- Paso 1: catalogo La Anonima ---" >> "$ARCHIVO_LOG"
python3 precios_armar_catalogo_anonima.py categorias.txt >> "$ARCHIVO_LOG" 2>&1

echo "--- Paso 2: catalogo VTEX (Carrefour + Changomas) ---" >> "$ARCHIVO_LOG"
python3 precios_armar_catalogo_vtex.py >> "$ARCHIVO_LOG" 2>&1

echo "--- Paso 3: buscar canasta y guardar ---" >> "$ARCHIVO_LOG"
python3 precios_buscar_canasta.py >> "$ARCHIVO_LOG" 2>&1

echo "Corrida finalizada: $(date '+%Y-%m-%d %H:%M:%S')" >> "$ARCHIVO_LOG"
