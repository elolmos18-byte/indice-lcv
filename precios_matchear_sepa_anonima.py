"""
precios_matchear_sepa_anonima.py

Cruza los productos de La Anonima que NO tienen EAN contra el dataset
oficial de SEPA (Sistema Electronico de Publicidad de Precios
Argentinos, datos.produccion.gob.ar) para la sucursal de Puerto
Madryn - sin necesidad de scrapear nada, es informacion publica que
el propio comercio esta obligado a reportar.

Como los formatos de nombre son muy distintos entre la web de La
Anonima ("Harina de Trigo 000 Caserita x 1 Kg.") y SEPA ("HARINA DE
TRIGO 000, CASERITA, 1000 gr"), el match es por SIMILITUD de texto
(SequenceMatcher), no exacto.

Para reducir falsos positivos (confirmado con una muestra de 300:
"Semola Gruesa" matcheaba mal con "Sal Gruesa" al 62%), se agregan
2 salvaguardas:
  1. Umbral de similitud de texto >= 0.75 (calibrado con la muestra)
  2. Chequeo de cantidad: se extrae el numero+unidad de ambos nombres
     (ej. "1 kg", "500 g") y si los dos lo tienen pero NO coinciden,
     se descarta el match aunque el texto sea parecido - evita
     confundir "Harina x 500g" con "Harina x 1Kg" solo porque el
     texto es similar.

Genera un CSV de resultados para REVISAR antes de importar (mismo
principio de "no inventar, no confiar a ciegas" del resto del
proyecto) - no importa nada solo, deja el CSV listo para que
precios_importar_ean_csv.py lo cargue despues de confirmar.

Uso:
    python3 precios_matchear_sepa_anonima.py
"""

import re
import sqlite3
import unicodedata
from difflib import SequenceMatcher

BASE = "/home/lcv/indice-lcv/precios_historico.db"
ARCHIVO_SEPA = "/home/lcv/indice-lcv/sepa_anonima_madryn.csv"
ARCHIVO_SALIDA = "matches_sepa_anonima.csv"

UMBRAL_ACEPTAR = 0.80   # match automatico, alta confianza
UMBRAL_REVISAR = 0.65   # zona gris, queda marcado para revisar a mano


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def extraer_cantidad(texto_normalizado: str):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kg\b", texto_normalizado)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*g(?:r|rs)?\b", texto_normalizado)
    if m:
        return float(m.group(1).replace(",", "."))

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*l(?:t|ts)?\b", texto_normalizado)
    if m:
        return float(m.group(1).replace(",", ".")) * 1000

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ml|cc)\b", texto_normalizado)
    if m:
        return float(m.group(1).replace(",", "."))

    return None


def cantidades_compatibles(cant_mia, cant_sepa) -> bool:
    if cant_mia is None or cant_sepa is None:
        return True
    if cant_mia == 0:
        return False
    diferencia_pct = abs(cant_mia - cant_sepa) / cant_mia
    return diferencia_pct < 0.05


def main():
    conn = sqlite3.connect(BASE)

    pendientes = conn.execute("""
        SELECT codigo_producto, nombre
        FROM productos_maestro
        WHERE tienda_id = (SELECT id FROM tiendas WHERE nombre = 'La Anonima')
        AND (ean IS NULL OR ean = '')
    """).fetchall()

    print(f"Productos pendientes de EAN: {len(pendientes)}")

    sepa_lista = []
    with open(ARCHIVO_SEPA, encoding="latin-1") as f:
        for linea in f:
            partes = linea.strip().split("|")
            if len(partes) >= 6:
                ean = partes[3]
                descripcion = partes[5]
                desc_norm = normalizar(descripcion)
                sepa_lista.append((ean, descripcion, desc_norm, extraer_cantidad(desc_norm)))

    print(f"Productos en SEPA (Puerto Madryn): {len(sepa_lista)}")
    print("Comparando (puede tardar unos minutos)...\n")

    resultados = []

    for indice, (codigo, nombre) in enumerate(pendientes, start=1):
        nombre_norm = normalizar(nombre)
        cantidad_mia = extraer_cantidad(nombre_norm)

        primera_palabra = nombre_norm.split(" ")[0] if nombre_norm else ""
        candidatos = [s for s in sepa_lista if primera_palabra in s[2]] or sepa_lista

        mejor_score = 0
        mejor = None
        for ean, desc, desc_norm, cant_sepa in candidatos:
            if not cantidades_compatibles(cantidad_mia, cant_sepa):
                continue
            score = SequenceMatcher(None, nombre_norm, desc_norm).ratio()
            if score > mejor_score:
                mejor_score = score
                mejor = (ean, desc)

        if mejor_score >= UMBRAL_ACEPTAR:
            estado = "alta_confianza"
        elif mejor_score >= UMBRAL_REVISAR:
            estado = "revisar"
        else:
            estado = "sin_match"
            mejor = (None, None)

        resultados.append({
            "codigo_producto": codigo,
            "nombre_mio": nombre,
            "ean_sepa": mejor[0],
            "descripcion_sepa": mejor[1],
            "score": round(mejor_score, 3),
            "estado": estado,
        })

        if indice % 500 == 0:
            print(f"  {indice}/{len(pendientes)} procesados...")

    conn.close()

    import csv
    with open(ARCHIVO_SALIDA, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=[
            "codigo_producto", "nombre_mio", "ean_sepa",
            "descripcion_sepa", "score", "estado"
        ])
        escritor.writeheader()
        escritor.writerows(resultados)

    alta = sum(1 for r in resultados if r["estado"] == "alta_confianza")
    revisar = sum(1 for r in resultados if r["estado"] == "revisar")
    sin_match = sum(1 for r in resultados if r["estado"] == "sin_match")

    print(f"\n--- Resumen ---")
    print(f"Alta confianza (>={UMBRAL_ACEPTAR:.0%}): {alta}")
    print(f"Para revisar ({UMBRAL_REVISAR:.0%}-{UMBRAL_ACEPTAR:.0%}): {revisar}")
    print(f"Sin match (<{UMBRAL_REVISAR:.0%}): {sin_match}")
    print(f"\nGuardado en: {ARCHIVO_SALIDA}")
    print("Revisar antes de importar - los de 'alta_confianza' son los")
    print("mas seguros de cargar directo, los de 'revisar' conviene")
    print("mirarlos a mano primero.")


if __name__ == "__main__":
    main()
