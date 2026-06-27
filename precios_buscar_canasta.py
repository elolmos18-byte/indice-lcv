"""
precios_buscar_canasta.py

Genera una "foto semanal" de precios para la canasta CCV-37.

Para cada uno de los 37 rubros definidos en precios_canasta_rubros.json,
busca el producto MAS BARATO disponible en cada super y lo registra.
La marca puede cambiar semana a semana - lo que se compara es el precio
minimo accesible para cada tipo de producto, no una marca fija.

NORMALIZACION DE PRECIOS:
Los precios se normalizan a unidad metrica ($/kg, $/L, $/unidad) antes
de comparar. Asi un paquete de 500g a $800 y uno de 1kg a $1200 se
comparan como $1600/kg vs $1200/kg. El de 1kg gana aunque su precio
de gondola sea mas caro. Esto evita el problema de comparar tamaños
distintos entre supers.

El total de la canasta se calcula multiplicando el precio normalizado
por la cantidad de referencia de cada rubro (ej: 1kg de harina, 500g
de fideos, 6 huevos). Asi el total refleja "cuanto cuesta comprar
la canasta completa" en cada super.

CORRECCION DE PRECIO DE LISTA (La Anonima):
El listado de categoria de La Anonima (lo que lee
precios_armar_catalogo_anonima.py) a veces trae un "price" que es
promocional o esta desactualizado, distinto del precio real que se ve
en la pagina del producto. La pagina individual de cada producto si
expone el precio de lista real, pero visitar la pagina individual de
TODOS los productos del catalogo seria muy pesado. Como compromiso,
una vez elegido el producto MAS BARATO de La Anonima en cada rubro
(maximo 37 productos, uno por rubro), visitamos solo esa pagina
individual puntual para confirmar/corregir su precio antes de armar
el resumen final. Ver corregir_precio_lista_anonima().

Dependencias:
- precios_canasta_rubros.json (definicion de rubros con palabras clave)
- catalogo_anonima.csv (generado por precios_armar_catalogo_anonima.py)
- catalogo_vtex.csv (generado por precios_armar_catalogo_vtex.py)

Los dos catalogos tienen que estar actualizados ANTES de correr este
script. El flujo completo de una corrida semanal es:

    1. python precios_armar_catalogo_anonima.py categorias.txt
    2. python precios_armar_catalogo_vtex.py
    3. python precios_buscar_canasta.py

El paso 3 es este script. Los pasos 1 y 2 actualizan los catalogos
con precios frescos.

Salida:
- foto_semanal_YYYY-MM-DD.csv  (un archivo por corrida, con fecha)
- Resumen en consola: tabla comparativa + detalle de productos por rubro

Como correrlo:
    python precios_buscar_canasta.py
"""

import csv
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import precios_db

ARCHIVO_RUBROS = "precios_canasta_rubros.json"
ARCHIVO_ANONIMA = "catalogo_anonima.csv"
ARCHIVO_VTEX = "catalogo_vtex.csv"

TIENDAS = ["La Anonima", "Carrefour", "Changomas"]

# Headers para visitar paginas individuales de producto de La Anonima
# (corregir_precio_lista_anonima). Los mismos que usa
# precios_armar_catalogo_anonima.py - el sitio rechaza con 403 los
# pedidos que no tienen estos headers basicos.
HEADERS_ANONIMA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


# --- Normalizacion de texto --------------------------------------------
# Este es el fix critico que encontramos: sin normalizar acentos,
# "azucar" no matchea "Azucar", "te" no matchea "Te", "atun" no
# matchea "Atun". Eso hacia que rubros enteros aparecieran vacios
# en Carrefour y Changomas (que usan acentos en sus nombres).

def normalizar(texto: str) -> str:
    """Quita acentos, pasa a minusculas. Para comparar nombres."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return sin_acentos.lower()


# --- Extraccion de tamano ----------------------------------------------
# Para comparar precios entre presentaciones distintas (500g vs 1kg),
# necesitamos saber cuanto pesa/mide cada producto.
#
# Bugs encontrados y corregidos en esta version:
# 1. "500 Kg" en vez de "500 g" (typo en catalogo) -> sanity check,
#    si pesa mas de 50kg lo descartamos como dato invalido.
# 2. "2, 255 L" (coma con espacio) -> regex que acepta ", " entre
#    digitos como separador decimal.
# 3. Yogur bebible dice "100 gr" pero el rubro mide en litros ->
#    para rubros en litros, si no encontramos ml/L, probamos con
#    gramos asumiendo densidad ≈ 1 (valido para lacteos y liquidos).
# 4. Jugo en polvo es 1 sobre pero no dice "x1" -> para rubros en
#    "unidad", si no encontramos cantidad, asumimos 1.


# Limite de sanidad: ningun producto individual de supermercado pesa
# mas de 50 kilos. Si el extractor calcula mas, es un typo en el
# catalogo (ej: "500 Kg" en vez de "500 g").
PESO_MAXIMO_GRAMOS = 50_000
VOLUMEN_MAXIMO_ML = 50_000


def extraer_gramos(nombre_norm: str) -> float | None:
    """Extrae el peso en gramos de un nombre normalizado."""
    # Primero buscamos kg (con coma, punto, o coma+espacio como decimal)
    m = re.search(r"(\d+(?:[.,]\s?\d+)?)\s*(?:kg|kilo)", nombre_norm)
    if m:
        valor = m.group(1).replace(" ", "").replace(",", ".")
        gramos = float(valor) * 1000
        if gramos > PESO_MAXIMO_GRAMOS:
            return None  # Typo: "500 Kg" en vez de "500 g"
        return gramos

    # Despues buscamos gramos directos
    m = re.search(r"(\d+(?:[.,]\s?\d+)?)\s*(?:grs|gr|g)\b", nombre_norm)
    if m:
        valor = m.group(1).replace(" ", "").replace(",", ".")
        gramos = float(valor)
        if gramos > PESO_MAXIMO_GRAMOS:
            return None
        return gramos

    # Fallback: productos vendidos a granel por kilo, sin un numero
    # adelante de "kg" (ej: "Picada especial Novillito x kg.",
    # "Vacio Envasado al Vacio FB MEATS (Kg)"). Es comun en carnes
    # frescas, donde el precio del catalogo ya viene expresado por
    # kilogramo en vez de por un envase de tamano fijo.
    if re.search(r"\bkg\b|\bkilo\b", nombre_norm):
        return 1000.0

    return None


def extraer_mililitros(nombre_norm: str) -> float | None:
    """Extrae el volumen en mililitros de un nombre normalizado."""
    # Buscamos litros (con coma, punto, o coma+espacio como decimal)
    m = re.search(r"(\d+(?:[.,]\s?\d+)?)\s*(?:litros?|lts|lt|l)\b", nombre_norm)
    if m:
        valor = m.group(1).replace(" ", "").replace(",", ".")
        ml = float(valor) * 1000
        if ml > VOLUMEN_MAXIMO_ML:
            return None
        return ml

    # Buscamos ml o cc directos
    m = re.search(r"(\d+(?:[.,]\s?\d+)?)\s*(?:ml|cc)\b", nombre_norm)
    if m:
        valor = m.group(1).replace(" ", "").replace(",", ".")
        ml = float(valor)
        if ml > VOLUMEN_MAXIMO_ML:
            return None
        return ml

    return None


def extraer_unidades(nombre_norm: str) -> int | None:
    """Extrae la cantidad de unidades (huevos x6, saquitos x25, etc.)."""
    # Primer intento: numero seguido de palabra que indica unidades.
    # Incluye "u" suelto porque los supers argentinos abrevian asi
    # ("Huevos Check 6 U", "Te Taragui 25 Un").
    m = re.search(r"(\d+)\s*(?:unidades?|uni|un|u|saquitos?|sobres?)\b", nombre_norm)
    if m:
        return int(m.group(1))

    # Segundo intento: patron "x N" (ej: "x 6", "x 30").
    # El \b despues de \d+ evita que el regex se confunda con pesos:
    # sin \b, "x 15 g" podria matchear como "x 1" (backtracking).
    # Con \b, solo matchea el numero completo "15", y el negative
    # lookahead lo descarta si es seguido por una unidad de peso.
    m = re.search(r"x\s*(\d+)\b(?!\s*(?:grs|gr|g|kg|kilo|ml|cc|lt|lts|l)\b)", nombre_norm)
    if m:
        return int(m.group(1))

    return None


def calcular_precio_normalizado(precio: float, nombre_norm: str, rubro: dict) -> float | None:
    """
    Calcula el precio por unidad estandar (por kg, por L, o por unidad)
    para poder comparar presentaciones distintas del mismo rubro.

    Devuelve None si no puede calcular (no detecta el tamano).
    """
    unidad = rubro.get("unidad", "")

    if unidad == "kg":
        gramos = extraer_gramos(nombre_norm)
        if gramos and gramos > 0:
            return precio / gramos * 1000  # precio por kg

    elif unidad == "L":
        ml = extraer_mililitros(nombre_norm)
        if ml and ml > 0:
            return precio / ml * 1000  # precio por litro

        # Fallback: para lacteos y liquidos, si no encontramos ml/L
        # pero si encontramos gramos, asumimos densidad ≈ 1 (1g ≈ 1ml).
        # Esto cubre "Yogur Danonino 100 gr" que mide en gramos pero
        # el rubro es en litros.
        gramos = extraer_gramos(nombre_norm)
        if gramos and gramos > 0:
            return precio / gramos * 1000  # precio por "litro" ≈ por kg

    elif unidad == "unidad":
        unidades = extraer_unidades(nombre_norm)
        if unidades and unidades > 0:
            return precio / unidades  # precio por unidad

        # Fallback: si el rubro mide en unidades pero no detectamos
        # cantidad en el nombre, asumimos que es 1 unidad individual.
        # Esto cubre "Jugo en polvo Tang Naranja 15g" que es un sobre
        # suelto sin indicador "x1".
        return precio  # 1 unidad = el precio del envase

    return None


# --- Correccion de precio de lista (La Anonima) -------------------------

def _precio_lista_de_pagina_individual(url: str) -> float | None:
    """
    Visita la pagina individual de un producto de La Anonima y
    devuelve su precio de lista (priceSpecification.price), si esta
    disponible en el JSON-LD de esa pagina.

    Por que esto hace falta: el listado de categoria (lo que lee
    precios_armar_catalogo_anonima.py) solo expone "offers.price",
    que a veces es un precio promocional o desactualizado. La pagina
    individual del producto si expone ademas "priceSpecification"
    con el precio de lista real (el que efectivamente se ve y se
    cobra). Por eso, para el producto que gano como mas barato,
    confirmamos su precio visitando esta pagina puntual.

    Devuelve None si no se pudo obtener (timeout, sin JSON-LD de tipo
    Product, sin priceSpecification, etc.) - en ese caso quien llama
    debe seguir usando el precio que ya tenia del listado.
    """
    try:
        respuesta = requests.get(url, headers=HEADERS_ANONIMA, timeout=10)
        respuesta.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(respuesta.text, "html.parser")

    for bloque in soup.find_all("script", type="application/ld+json"):
        if not bloque.string:
            continue
        try:
            datos = json.loads(bloque.string)
        except json.JSONDecodeError:
            continue

        if datos.get("@type") != "Product":
            continue

        oferta = datos.get("offers", {})
        spec = oferta.get("priceSpecification")
        if spec and spec.get("price"):
            return spec["price"]

    return None


def corregir_precio_lista_anonima(elegido: dict) -> dict:
    """
    Dado el producto elegido como mas barato de La Anonima en un
    rubro, intenta corregir su precio visitando su pagina individual
    (ver _precio_lista_de_pagina_individual).

    Si el precio de lista real es distinto al que vino del listado
    de categoria, actualiza "precio" y reescala "precio_normalizado"
    en la misma proporcion (sin volver a parsear el peso del nombre,
    ya que la normalizacion es lineal respecto al precio).

    Si no se pudo obtener un precio de lista (pagina caida, sin
    promo, etc.), devuelve el producto sin modificar.
    """
    url = elegido.get("url")
    if not url:
        return elegido

    precio_lista = _precio_lista_de_pagina_individual(url)

    if precio_lista is None or precio_lista == elegido["precio"]:
        return elegido

    precio_viejo = elegido["precio"]
    elegido["precio"] = precio_lista

    if elegido.get("precio_normalizado") is not None:
        elegido["precio_normalizado"] = (
            elegido["precio_normalizado"] * precio_lista / precio_viejo
        )

    return elegido


# --- Carga de datos ----------------------------------------------------

def cargar_rubros() -> list[dict]:
    try:
        with open(ARCHIVO_RUBROS, encoding="utf-8") as f:
            data = json.load(f)
        return data["rubros"]
    except FileNotFoundError:
        print(f"No se encontro {ARCHIVO_RUBROS}.")
        sys.exit(1)


def cargar_productos() -> list[dict]:
    productos = []

    try:
        with open(ARCHIVO_ANONIMA, encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                try:
                    precio = float(fila["precio"])
                except (ValueError, KeyError):
                    continue
                productos.append({
                    "tienda": "La Anonima",
                    "nombre": fila["nombre"],
                    "precio": precio,
                    "url": fila.get("url", ""),
                })
    except FileNotFoundError:
        print(f"No se encontro {ARCHIVO_ANONIMA}. Corre precios_armar_catalogo_anonima.py primero.")
        sys.exit(1)

    try:
        with open(ARCHIVO_VTEX, encoding="utf-8-sig") as f:
            for fila in csv.DictReader(f):
                try:
                    precio = float(fila["precio"])
                except (ValueError, KeyError):
                    continue

                # VTEX expone ademas el precio de lista (sin descuentos
                # ni promociones de tarjeta) en la columna "precio_lista".
                # Lo usamos cuando esta disponible, para comparar de
                # forma pareja contra La Anonima (que tambien se corrige
                # a precio de lista en corregir_precio_lista_anonima).
                # Si la columna esta vacia o es 0, nos quedamos con el
                # "precio" normal tal cual.
                try:
                    precio_lista = float(fila.get("precio_lista") or 0)
                except ValueError:
                    precio_lista = 0
                if precio_lista > 0:
                    precio = precio_lista

                productos.append({
                    "tienda": fila["tienda"],
                    "nombre": fila["nombre"],
                    "precio": precio,
                    "url": fila.get("url", ""),
                })
    except FileNotFoundError:
        print(f"No se encontro {ARCHIVO_VTEX}. Corre precios_armar_catalogo_vtex.py primero.")
        sys.exit(1)

    return productos


# --- Busqueda por rubro ------------------------------------------------

def _contiene_palabra(clave: str, texto_norm: str) -> bool:
    """
    Chequea si 'clave' aparece en 'texto_norm' empezando en un limite
    de palabra (no como sufijo de otra palabra). Esto evita falsos
    positivos como "asado" matcheando dentro de "envasado", o "te"
    matcheando dentro de cualquier palabra que termine en "te".

    A proposito NO exigimos limite de palabra al final de la clave:
    asi "saquito" sigue matcheando "saquitos" (plural), que es el
    comportamiento que ya usaban varios rubros (ej. "Te en saquitos",
    cuya clave esta en singular pero el catalogo dice plural).
    """
    patron = r"\b" + re.escape(clave)
    return re.search(patron, texto_norm) is not None


def buscar_mas_barato(productos: list[dict], rubro: dict) -> dict[str, dict]:
    """
    Para un rubro dado, busca en cada tienda el producto mas barato
    que matchee con las palabras clave (normalizado, sin acentos).

    Devuelve un dict {tienda: {nombre, precio, precio_normalizado, url}}.
    Solo incluye tiendas donde encontro al menos un match.

    Para La Anonima, antes de devolver el resultado, corrige el
    precio del ganador con corregir_precio_lista_anonima() - ver esa
    funcion para el porque.
    """
    claves = [normalizar(c) for c in rubro["claves"]]
    excluir = [normalizar(e) for e in rubro["excluir"]]

    candidatos_por_tienda: dict[str, list] = {t: [] for t in TIENDAS}

    for prod in productos:
        nombre_norm = normalizar(prod["nombre"])

        if not all(_contiene_palabra(c, nombre_norm) for c in claves):
            continue

        if any(_contiene_palabra(e, nombre_norm) for e in excluir):
            continue

        precio_norm = calcular_precio_normalizado(
            prod["precio"], nombre_norm, rubro
        )

        candidatos_por_tienda[prod["tienda"]].append({
            "nombre": prod["nombre"],
            "precio": prod["precio"],
            "precio_normalizado": precio_norm,
            "url": prod.get("url", ""),
        })

    # Para cada tienda, elegimos el mas barato.
    # Priorizamos por precio_normalizado (por kg/L/unidad) si esta
    # disponible, para comparar presentaciones distintas de forma justa.
    resultado = {}
    for tienda, candidatos in candidatos_por_tienda.items():
        if not candidatos:
            continue

        con_norm = [c for c in candidatos if c["precio_normalizado"] is not None]
        if con_norm:
            elegido = min(con_norm, key=lambda c: c["precio_normalizado"])
        else:
            elegido = min(candidatos, key=lambda c: c["precio"])

        if tienda == "La Anonima":
            elegido = corregir_precio_lista_anonima(elegido)
            time.sleep(1)  # cortesia: no golpear el sitio sin pausa

        resultado[tienda] = elegido

    return resultado


# --- Salida ------------------------------------------------------------

def guardar_foto_semanal(resultados: list[dict], fecha: str):
    archivo = f"foto_semanal_{fecha}.csv"
    columnas = [
        "fecha", "rubro_id", "rubro_nombre", "tienda",
        "producto", "precio", "precio_por_unidad", "unidad", "url",
    ]

    with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        for fila in resultados:
            escritor.writerow(fila)

    return archivo


def imprimir_resumen(resultados_por_rubro: list[dict], rubros: list[dict]):
    """
    Imprime dos cosas:
    1. Tabla comparativa con precios normalizados ($/kg, $/L, $/un)
    2. Detalle de cada rubro mostrando el producto concreto elegido
       en cada super (marca + nombre completo) — esto es lo que el
       Guardian necesita para saber que producto buscar.
    """

    # --- Tabla comparativa con precios normalizados ---
    print(f"\n{'ID':>3} {'RUBRO':<28} {'LA ANONIMA':>12} {'CARREFOUR':>12} {'CHANGOMAS':>12}  {'MAS BARATO':<12}")
    print("-" * 95)

    # Para calcular el total de la canasta, usamos precio normalizado
    # multiplicado por la cantidad de referencia del rubro. Asi los
    # totales son comparables aunque cada super venda tamaños distintos.
    total_por_tienda = {t: 0.0 for t in TIENDAS}
    rubros_con_precio = {t: 0 for t in TIENDAS}

    # Mapeo rubro_id -> dict del rubro para acceder a tamano_objetivo
    rubros_por_id = {r["id"]: r for r in rubros}

    for dato in resultados_por_rubro:
        rubro_id = dato["rubro_id"]
        nombre = dato["rubro_nombre"]
        precios = dato["precios"]
        rubro_def = rubros_por_id.get(rubro_id, {})
        unidad = rubro_def.get("unidad", "")

        # Un rubro solo suma al total si esta completo en los 3
        # supers. Si le falta uno (ej. "Pollo" en Changomas), lo
        # seguimos mostrando en la tabla con su "---", pero no se
        # incluye en el total - de lo contrario, al super al que le
        # falta ese producto le "ahorrariamos" sumarlo, y parecería
        # mas barato en total sin serlo realmente. Asi el total
        # siempre compara la misma canasta entre los 3.
        rubro_completo = len(precios) == len(TIENDAS)

        celdas = {}
        min_pn = float("inf")
        min_tienda = ""

        for tienda in TIENDAS:
            if tienda not in precios:
                celdas[tienda] = "---"
                continue

            pn = precios[tienda].get("precio_normalizado")
            precio_abs = precios[tienda]["precio"]

            if pn is not None:
                # Mostramos precio por unidad metrica
                if unidad == "kg":
                    celdas[tienda] = f"${pn:.0f}/kg"
                elif unidad == "L":
                    celdas[tienda] = f"${pn:.0f}/L"
                elif unidad == "unidad":
                    celdas[tienda] = f"${pn:.0f}/u"
                else:
                    celdas[tienda] = f"${pn:.0f}"

                # Para el total, calculamos el costo de la cantidad
                # de referencia del rubro usando el precio normalizado.
                # Ej: si el rubro es "Harina 000" con tamano_objetivo_g=1000
                # y el precio normalizado es $690/kg, sumamos $690.
                # Solo si el rubro esta completo en los 3 (ver arriba).
                if rubro_completo:
                    costo_referencia = _costo_referencia(pn, rubro_def)
                    total_por_tienda[tienda] += costo_referencia
                    rubros_con_precio[tienda] += 1

                if pn < min_pn:
                    min_pn = pn
                    min_tienda = tienda
            else:
                # Si no pudimos normalizar, usamos precio absoluto
                celdas[tienda] = f"${precio_abs:.0f}*"
                if rubro_completo:
                    total_por_tienda[tienda] += precio_abs
                    rubros_con_precio[tienda] += 1

                if precio_abs < min_pn:
                    min_pn = precio_abs
                    min_tienda = tienda

        marca_barato = f"<- {min_tienda[:10]}" if min_tienda else ""
        print(f"{rubro_id:3} {nombre:<28} {celdas['La Anonima']:>12} {celdas['Carrefour']:>12} {celdas['Changomas']:>12}  {marca_barato}")

    print("-" * 95)
    print(f"{'':3} {'TOTAL CANASTA (referencia)':<28}", end="")
    for tienda in TIENDAS:
        if rubros_con_precio[tienda] > 0:
            print(f" ${total_por_tienda[tienda]:>10.0f}", end="")
        else:
            print(f" {'---':>11}", end="")
    print()
    print(f"{'':3} {'(* = precio sin normalizar)'}")

    totales = {t: total_por_tienda[t] for t in TIENDAS if rubros_con_precio[t] > 0}
    if totales:
        mas_barato = min(totales, key=totales.get)
        print(f"\n  Super mas barato en total: {mas_barato} (${totales[mas_barato]:.0f})")

        print(f"\n  Rubros donde cada super es el mas barato:")
        for tienda in TIENDAS:
            gana = 0
            for d in resultados_por_rubro:
                if tienda not in d["precios"]:
                    continue
                pn_tienda = d["precios"][tienda].get("precio_normalizado")
                if pn_tienda is None:
                    # Si no tiene precio normalizado, usamos precio absoluto
                    pn_tienda = d["precios"][tienda]["precio"]

                es_mas_barato = True
                for t2 in TIENDAS:
                    if t2 == tienda:
                        continue
                    if t2 not in d["precios"]:
                        continue
                    pn_otro = d["precios"][t2].get("precio_normalizado")
                    if pn_otro is None:
                        pn_otro = d["precios"][t2]["precio"]
                    if pn_otro < pn_tienda:
                        es_mas_barato = False
                        break

                if es_mas_barato:
                    gana += 1

            print(f"    {tienda}: {gana} rubros")

    # --- Detalle de productos por rubro ---
    # Esto es lo que el Guardian necesita: que producto concreto es el
    # mas barato en cada super, con nombre completo y marca.
    print(f"\n\n{'='*80}")
    print("DETALLE: PRODUCTO MAS BARATO POR RUBRO EN CADA SUPER")
    print(f"{'='*80}")

    for dato in resultados_por_rubro:
        rubro_id = dato["rubro_id"]
        nombre = dato["rubro_nombre"]
        precios = dato["precios"]
        rubro_def = rubros_por_id.get(rubro_id, {})
        unidad = rubro_def.get("unidad", "")

        print(f"\n  {rubro_id}. {nombre}")
        for tienda in TIENDAS:
            if tienda not in precios:
                print(f"     {tienda:<12}  ---")
                continue

            prod = precios[tienda]
            pn = prod.get("precio_normalizado")
            precio_abs = prod["precio"]
            nombre_prod = prod["nombre"]

            if pn is not None:
                if unidad == "kg":
                    precio_str = f"${pn:.0f}/kg"
                elif unidad == "L":
                    precio_str = f"${pn:.0f}/L"
                elif unidad == "unidad":
                    precio_str = f"${pn:.0f}/u"
                else:
                    precio_str = f"${pn:.0f}"
                envase_str = f"(envase ${precio_abs:.0f})"
            else:
                precio_str = f"${precio_abs:.0f}"
                envase_str = ""

            print(f"     {tienda:<12}  {precio_str:>10}  {envase_str:>16}  {nombre_prod}")


def _costo_referencia(precio_normalizado: float, rubro: dict) -> float:
    """
    Dado un precio normalizado (por kg, por L, por unidad) y la
    definicion del rubro, calcula cuanto cuesta la cantidad de
    referencia del rubro.

    Ejemplo: harina 000 con tamano_objetivo_g=1000 y precio $690/kg
    devuelve $690 (1kg × $690/kg).

    Ejemplo: fideos con tamano_objetivo_g=500 y precio $1600/kg
    devuelve $800 (0.5kg × $1600/kg).
    """
    unidad = rubro.get("unidad", "")

    if unidad == "kg":
        gramos = rubro.get("tamano_objetivo_g", 1000)
        return precio_normalizado * gramos / 1000

    elif unidad == "L":
        ml = rubro.get("tamano_objetivo_ml", 1000)
        return precio_normalizado * ml / 1000

    elif unidad == "unidad":
        unidades = rubro.get("tamano_objetivo_unidades", 1)
        return precio_normalizado * unidades

    # Si no hay unidad definida, devolvemos el precio tal cual
    return precio_normalizado


# --- Orquestacion ------------------------------------------------------

ARCHIVO_JSON_WEB = "precios_ultimo.json"


def guardar_json_web(resumen: list[dict], rubros: list[dict], fecha: str):
    """
    Genera precios_ultimo.json — el archivo que la pagina web lee
    para mostrar la tabla comparativa. Siempre se llama igual (se
    sobreescribe cada corrida) para que la pagina no tenga que
    adivinar la fecha.

    Estructura:
    {
      "fecha": "2026-06-24",
      "rubros": [ ... ],
      "totales": { "La Anonima": 62972, ... },
      "mas_barato": "Carrefour"
    }
    """
    rubros_por_id = {r["id"]: r for r in rubros}

    rubros_json = []
    totales = {t: 0.0 for t in TIENDAS}
    rubros_con_precio = {t: 0 for t in TIENDAS}

    for dato in resumen:
        rubro_id = dato["rubro_id"]
        rubro_def = rubros_por_id.get(rubro_id, {})
        unidad = rubro_def.get("unidad", "")

        # Mismo criterio que en imprimir_resumen: un rubro solo suma
        # al total si esta completo en los 3 supers.
        rubro_completo = len(dato["precios"]) == len(TIENDAS)

        precios_json = {}
        for tienda in TIENDAS:
            if tienda not in dato["precios"]:
                continue

            prod = dato["precios"][tienda]
            pn = prod.get("precio_normalizado")
            precio_abs = prod["precio"]

            precios_json[tienda] = {
                "precio_normalizado": round(pn, 2) if pn is not None else None,
                "precio_envase": round(precio_abs, 2),
                "producto": prod["nombre"],
                "url": prod.get("url", ""),
            }

            # Sumar al total usando precio normalizado × referencia,
            # solo si el rubro esta completo en los 3 supers.
            if rubro_completo:
                if pn is not None:
                    costo = _costo_referencia(pn, rubro_def)
                    totales[tienda] += costo
                else:
                    totales[tienda] += precio_abs
                rubros_con_precio[tienda] += 1

        rubros_json.append({
            "id": rubro_id,
            "nombre": dato["rubro_nombre"],
            "grupo": rubro_def.get("grupo", "Almacen"),
            "unidad": unidad,
            "precios": precios_json,
        })

    # Redondear totales
    totales_redondeados = {
        t: round(totales[t])
        for t in TIENDAS
        if rubros_con_precio[t] > 0
    }

    mas_barato = min(totales_redondeados, key=totales_redondeados.get) if totales_redondeados else None

    datos = {
        "fecha": fecha,
        "rubros": rubros_json,
        "totales": totales_redondeados,
        "mas_barato": mas_barato,
    }

    with open(ARCHIVO_JSON_WEB, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    return ARCHIVO_JSON_WEB


def main():
    print("Cargando datos...")
    rubros = cargar_rubros()
    productos = cargar_productos()
    fecha = date.today().isoformat()

    print(f"  {len(rubros)} rubros definidos")
    print(f"  {len(productos)} productos en los catalogos")
    print(f"  Fecha de la foto: {fecha}")

    # Sincronizamos la tabla "rubros" de la base con el JSON. Si el
    # JSON cambio (se agrego o edito un rubro), esto lo refleja sin
    # que haya que correr nada a mano.
    precios_db.poblar_rubros(ARCHIVO_RUBROS)

    filas_csv = []
    resumen = []

    for rubro in rubros:
        mas_barato = buscar_mas_barato(productos, rubro)

        precios_resumen = {}
        for tienda in TIENDAS:
            if tienda not in mas_barato:
                continue

            elegido = mas_barato[tienda]
            precios_resumen[tienda] = elegido

            filas_csv.append({
                "fecha": fecha,
                "rubro_id": rubro["id"],
                "rubro_nombre": rubro["nombre"],
                "tienda": tienda,
                "producto": elegido["nombre"],
                "precio": elegido["precio"],
                "precio_por_unidad": (
                    f"{elegido['precio_normalizado']:.2f}"
                    if elegido.get("precio_normalizado")
                    else ""
                ),
                "unidad": rubro.get("unidad", ""),
                "url": elegido.get("url", ""),
            })

        resumen.append({
            "rubro_id": rubro["id"],
            "rubro_nombre": rubro["nombre"],
            "precios": precios_resumen,
        })

    archivo = guardar_foto_semanal(filas_csv, fecha)
    print(f"\nFoto semanal guardada en: {archivo}")

    archivo_json = guardar_json_web(resumen, rubros, fecha)
    print(f"JSON para la web guardado en: {archivo_json}")

    filas_guardadas = precios_db.guardar_foto_dia(fecha, resumen)
    print(f"Historico actualizado en precios_historico.db: {filas_guardadas} filas")

    imprimir_resumen(resumen, rubros)

    completos = sum(1 for r in resumen if len(r["precios"]) == 3)
    parciales = sum(1 for r in resumen if 0 < len(r["precios"]) < 3)
    vacios = sum(1 for r in resumen if len(r["precios"]) == 0)
    print(f"\n  Rubros completos (3/3): {completos}")
    if parciales:
        print(f"  Rubros parciales:       {parciales}")
    if vacios:
        print(f"  Rubros sin datos:       {vacios}")


if __name__ == "__main__":
    main()
