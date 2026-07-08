"""
precios_normalizar_unidades.py

Funciones puras para normalizar precios a una unidad metrica estandar
($/kg, $/L, $/unidad, $/metro, $/pano) a partir del nombre de un
producto tal como aparece en el catalogo de cada super.

Por que un archivo aparte: estas funciones empezaron chiquitas, pero
fueron creciendo con cada caso raro que encontramos (typos de "500 Kg"
en vez de "500 g", comas con espacio como separador decimal, rollos
de cocina donde "360 Paños x 3 Un" es ambiguo segun el super, etc.).
Separarlas de precios_buscar_canasta.py hace mas facil encontrar y
testear el proximo caso raro sin tener que leer todo el script de
busqueda de precios.

Todas las funciones de aca son "puras": reciben texto/numeros y
devuelven un numero o None, sin tocar archivos, la base de datos, ni
internet. Eso las hace faciles de probar sueltas, por ejemplo:

    >>> from precios_normalizar_unidades import extraer_gramos
    >>> extraer_gramos("harina de trigo 000 caserita x 1 kg")
    1000.0

Funciones:
- normalizar(texto)                    -> saca acentos, pasa a minusculas
- extraer_gramos(nombre_norm)          -> peso en gramos, o None
- extraer_mililitros(nombre_norm)      -> volumen en ml, o None
- extraer_unidades(nombre_norm)        -> cantidad de unidades, o None
- extraer_metros_totales(nombre_norm)  -> metros totales (papel), o None
- extraer_panos_totales(nombre_norm)   -> paños totales (rollo cocina), o None
- calcular_precio_normalizado(...)     -> combina todo lo anterior segun
                                           la unidad del rubro (kg/L/unidad/m/panos)
"""

import re
import unicodedata

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


def extraer_metros_totales(nombre_norm: str) -> float | None:
    """
    Extrae el total de metros de un producto de papel (servilletas
    no, pero papel higienico/cocina si vienen en rollos de N metros,
    vendidos en paquetes de M rollos). El total = metros_por_rollo x
    cantidad_de_rollos.

    Los catalogos usan 3 formatos distintos para esto:
      1. "4 x 80 metros"      (cantidad, x, largo)
      2. "30 m x 4 un"        (largo, x, cantidad)
      3. "30 m 4 un"          (largo y cantidad sueltos, sin "x")
         "x4 80 mts"          (cantidad con x pegado, largo despues)

    Si no se encuentra ninguna cantidad de rollos, asumimos 1 rollo
    (ej. "Elegante megamax x 120 mts" - un solo rollo grande, el "x"
    ahi no es multiplicador sino que acompaña al numero de metros).
    Ese ultimo caso es justamente el que hay que tener cuidado de NO
    confundir con el formato 3 - ver el negative lookahead mas abajo.
    """
    UNIDAD_METROS = r"(?:mts?\.?|metros?|m)\b"

    # Formato 1: "N x M mts" (cantidad antes del x, largo despues)
    m = re.search(rf"(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*{UNIDAD_METROS}", nombre_norm)
    if m:
        rollos = float(m.group(1))
        metros_por_rollo = float(m.group(2).replace(",", "."))
        return rollos * metros_por_rollo

    # Formato 2: "M mts x N" (largo antes del x, cantidad despues)
    m = re.search(rf"(\d+(?:[.,]\d+)?)\s*{UNIDAD_METROS}\s*x\s*(\d+)", nombre_norm)
    if m:
        metros_por_rollo = float(m.group(1).replace(",", "."))
        rollos = float(m.group(2))
        return metros_por_rollo * rollos

    # Formato 3: largo y cantidad sueltos (sin "x" entre ellos).
    # Primero buscamos el largo por rollo en cualquier parte del nombre.
    m_largo = re.search(rf"(\d+(?:[.,]\d+)?)\s*{UNIDAD_METROS}", nombre_norm)
    if not m_largo:
        return None
    metros_por_rollo = float(m_largo.group(1).replace(",", "."))

    # Despues buscamos la cantidad de rollos, en dos pasadas:
    # primero "N un/uni" (forma mas explicita), y si no aparece,
    # "xN" suelto (ej. "x4 80 mts"). El negative lookahead en el
    # segundo intento es clave: evita que "x 120 mts" (un solo rollo
    # de 120m, sin cantidad separada) se interprete como "120 rollos"
    # - si el numero que sigue al "x" es inmediatamente el mismo que
    # ya usamos como largo (seguido directo por la unidad de metros),
    # no es una cantidad, es parte de la expresion del largo.
    m_rollos = re.search(r"(\d+)\s*(?:unidades?|uni|un|u)\b", nombre_norm)
    if m_rollos:
        rollos = float(m_rollos.group(1))
    else:
        m_x = re.search(rf"\bx\s*(\d+)\b(?!\s*{UNIDAD_METROS})", nombre_norm)
        rollos = float(m_x.group(1)) if m_x else 1.0

    return metros_por_rollo * rollos


def extraer_panos_totales(nombre_norm: str) -> float | None:
    """
    Misma logica que extraer_metros_totales(), pero para rollo de
    cocina, que se mide en "paños" en vez de metros (ej. "3 x 60
    paños", "200 paños x 1 un"). Ver esa funcion para el detalle de
    cada formato.
    """
    UNIDAD_PANOS = r"panos?\b"

    m = re.search(rf"(\d+)\s*x\s*(\d+)\s*{UNIDAD_PANOS}", nombre_norm)
    if m:
        rollos = float(m.group(1))
        panos_por_rollo = float(m.group(2))
        return rollos * panos_por_rollo

    # Formato 2: "M paños x N ..." - aca hay una ambiguedad real segun
    # el super: a veces "M" ya es el total del pack y "x N un" es solo
    # una etiqueta describiendo que viene en N unidades (ej. Vea:
    # "360 Panos x 3 Un" = 360 paños TOTALES, en 3 rollos - el propio
    # Vea confirma esto en su pagina, dividiendo el precio por 360).
    # Si en cambio el numero despues del x NO esta etiquetado como
    # unidad (nada de "un/uni/unidad" a continuacion), asumimos que es
    # un multiplicador real (M paños POR rollo, x N rollos) y multiplicamos,
    # como ya se hacia antes.
    m = re.search(rf"(\d+)\s*{UNIDAD_PANOS}\s*x\s*(\d+)\s*(unidades?|uni|un|u)?\b", nombre_norm)
    if m:
        total_declarado = float(m.group(1))
        etiquetado_como_unidad = m.group(3) is not None
        if etiquetado_como_unidad:
            # "360 panos x 3 UN" -> 360 ya es el total del pack.
            return total_declarado
        else:
            # "180 panos x 3" (sin "un" despues) -> multiplicador real.
            multiplicador = float(m.group(2))
            return total_declarado * multiplicador

    m_largo = re.search(rf"(\d+)\s*{UNIDAD_PANOS}", nombre_norm)
    if not m_largo:
        return None
    panos_por_rollo = float(m_largo.group(1))

    m_rollos = re.search(r"(\d+)\s*(?:unidades?|uni|un|u)\b", nombre_norm)
    if m_rollos:
        rollos = float(m_rollos.group(1))
    else:
        m_x = re.search(rf"\bx\s*(\d+)\b(?!\s*{UNIDAD_PANOS})", nombre_norm)
        rollos = float(m_x.group(1)) if m_x else 1.0

    return panos_por_rollo * rollos


def calcular_precio_normalizado(
    precio: float, nombre_norm: str, rubro: dict, medida: str = "un"
) -> float | None:
    """
    Calcula el precio por unidad estandar (por kg, por L, o por unidad)
    para poder comparar presentaciones distintas del mismo rubro.

    El parametro "medida" viene de VTEX (measurementUnit, ver
    precios_armar_catalogo_vtex.py). Cuando un producto es "pesable"
    (measurementUnit == "kg", tipico en frutas/verduras sueltas tipo
    "Tomate Perita 500 G" con compra minima de 0.5kg), el precio que
    entrega la API YA ES por kilo - no es el precio de ese paquete de
    500g puntual. Si igual le aplicaramos la extraccion de gramos del
    nombre, estariamos dividiendo un precio que ya esta normalizado,
    duplicando el precio por error. Por eso, si medida coincide con la
    unidad del rubro, devolvemos el precio tal cual, sin tocar nada.
    La Anonima no expone esta info, asi que siempre llega medida="un"
    para sus productos (comportamiento de siempre, sin cambios).

    Devuelve None si no puede calcular (no detecta el tamano).
    """
    unidad = rubro.get("unidad", "")

    if unidad == "kg" and medida == "kg":
        return precio  # VTEX ya entrega el precio por kg

    if unidad == "L" and medida in ("l", "L"):
        return precio  # VTEX ya entrega el precio por litro

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

    elif unidad == "m":
        metros = extraer_metros_totales(nombre_norm)
        if metros and metros > 0:
            return precio / metros  # precio por metro

    elif unidad == "panos":
        panos = extraer_panos_totales(nombre_norm)
        if panos and panos > 0:
            return precio / panos  # precio por pano

    return None
