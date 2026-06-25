#!/bin/bash
set -e
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
