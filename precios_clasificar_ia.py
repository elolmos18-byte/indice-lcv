"""
precios_clasificar_ia.py

Completa categoria_ia, cantidad_normalizada y unidad_normalizada en
productos_maestro, usando Gemini - UNA sola llamada por producto (no
se llama de nuevo despues, salvo que el producto cambie de nombre).

Por que una sola llamada para las 3 cosas: pedirle a Gemini categoria
y normalizacion por separado costaria practicamente el doble sin
beneficio real - el nombre del producto ya tiene toda la info que
Gemini necesita para las dos cosas a la vez (ver arquitectura del
Observatorio, sesion 19/8/2026).

Por que una LISTA FIJA de categorias (CATEGORIAS_VALIDAS) en vez de
dejar que Gemini invente libremente: para que las estadisticas por
categoria (cuartiles, indice base 100) tengan sentido, todos los
productos de un mismo tipo necesitan la MISMA categoria exacta. Si
Gemini eligiera el texto libremente, el mismo tipo de producto podria
terminar con "Fideos Secos" un dia y "Pastas" al otro, rompiendo
cualquier agrupacion. La lista se armo el 19/8/2026 juntando las
categorias que ya usan los scrapers de las 4 tiendas (unificando
nombres distintos para lo mismo, ej. "arvejas-en-lata" y
"legumbres-en-lata" -> "Legumbres en Lata"), con la profundidad que
Agustin pidio: separa por TIPO de producto (fideos largos vs cortos)
pero no por variante/sabor (no separa "fideos tallarin" de "fideos
tallarin de espinaca").

Incluye "Otros / Sin Categoria" como catch-all para lo que no encaje
bien en ninguna - pensado para revisar despues que cae ahi y decidir
si hace falta sumar una categoria nueva a la lista.

Como retoma donde quedo: cada corrida le pide a la base
(precios_db.obtener_productos_sin_clasificar) los productos que
TODAVIA no tienen categoria_ia. Como guardar_clasificacion_ia() va
marcando cada uno a medida que se completa, la proxima corrida
automaticamente salta los que ya estan listos.

Configuracion necesaria (ver .env en esta carpeta):
    GEMINI_API_KEY=...   (copiada del .env de La Comunidad del Viento)

Como correrlo (con un limite chico primero, para probar sin gastar
de mas):
    python precios_clasificar_ia.py --limite 5

Corrida normal:
    python precios_clasificar_ia.py --limite 500
"""

import argparse
import json
import os
import re
import time

from dotenv import load_dotenv
from google import genai

import precios_db

# --- Configuracion -------------------------------------------------------

load_dotenv()

MODELO_GEMINI = "gemini-2.5-flash-lite"
LIMITE_POR_DEFECTO = 500

# Pausa entre llamadas a Gemini, para no golpear la API de punta a
# punta sin respiro (buena practica, igual que con los scrapers).
SEGUNDOS_ENTRE_PEDIDOS = 1

# Lista de referencia para que Gemini clasifique. Ver docstring del
# modulo para el porque de esta lista fija y su profundidad.
CATEGORIAS_VALIDAS = [
    "Harinas",
    "Polenta",
    "Fideos Largos",
    "Fideos Cortos",
    "Arroz",
    "Legumbres Secas",
    "Legumbres en Lata",
    "Galletitas Dulces",
    "Galletitas Saladas",
    "Azucar y Endulzantes",
    "Dulce de Leche",
    "Mermeladas y Dulces",
    "Aceites",
    "Manteca y Margarina",
    "Leche Entera",
    "Leche Descremada",
    "Yogures Enteros",
    "Yogures Descremados",
    "Queso Untable",
    "Huevos",
    "Atun y Pescado en Lata",
    "Salsas y Pure de Tomate",
    "Sal",
    "Especias y Condimentos",
    "Vinagre y Limon",
    "Mayonesa",
    "Ketchup",
    "Mostaza",
    "Yerba Mate",
    "Cafe",
    "Te e Infusiones",
    "Gaseosas",
    "Aguas",
    "Jugos y Jugo en Polvo",
    "Carniceria",
    "Limpieza del Hogar",
    "Desodorante de Ambientes",
    "Jabon en Polvo",
    "Papel Higienico",
    "Rollos de Cocina",
    "Frutas",
    "Verduras",
    "Frutos Secos y Semillas",
    "Bebidas Vegetales",
    "Pescados y Mariscos",
    "Delicatessen",
    "Carbon y Elementos para Fuego",
    "Otros / Sin Categoria",
]

UNIDADES_VALIDAS = ["kg", "l", "unidad", "100g"]

PROMPT_TEMPLATE = """Sos un clasificador de productos de supermercado argentino.

Producto: "{nombre_producto}"

Elegi la categoria MAS CERCANA de esta lista (copia el texto EXACTO,
no inventes una nueva):
{lista_categorias}

ACLARACION IMPORTANTE - "Legumbres Secas" es una categoria MUY
especifica, se confunde facil con otras:

"Legumbres Secas" = SOLO estas 5 cosas: lentejas, garbanzos,
porotos (alubias), arvejas secas, soja en grano. NADA MAS entra
aca. Si el producto no es exactamente uno de esos 5, NO es
"Legumbres Secas", sin importar que tambien sea una semilla chica
o se venda de forma parecida (a granel, en bolsa, por kg).

Van en "Frutos Secos y Semillas" en cambio (NUNCA en Legumbres
Secas), estos casos frecuentes:
- Almendras, nueces, castañas, pistachos, avellanas, mani (cualquier
  fruto seco)
- Semillas sueltas de girasol (tambien llamadas "pipas" en
  Argentina), zapallo/calabaza, chia, lino, sesamo
- Quinoa (blanca, roja, o pop) - es una semilla, no una legumbre
- Cualquier "Mix" o "Mezcla" que combine frutos secos y/o semillas
  (ej. "Mix Fitness", "Mix Patagonico", "Mix Europeo", "Mix Vital",
  "Mix de Frutas Secas") - estos productos son SIEMPRE frutos secos/
  semillas mezclados, nunca legumbres, aunque el nombre no lo diga
  explicitamente.

Los hongos secos (ej. "Hongos Secos", "Boletus", "Portobello
deshidratado") tampoco son legumbre ni fruto seco - van en "Otros /
Sin Categoria" si no calzan mejor en otra categoria de la lista.

La grasa animal para cocinar (ej. "Grasa Bovina", "Grasa de Cerdo",
"Grasa Vacuna Refinada") NO es "Aceites" - va en "Manteca y
Margarina" (son todas grasas solidas/semisolidas para cocinar,
distintas del aceite liquido vegetal).

"Atun y Pescado en Lata" es SOLO conservas comunes y economicas:
atun (cualquier marca/presentacion), sardinas, caballa. Los
pescados/mariscos DELICATESSEN o premium (mucho mas caros, en latas
chicas de 90-190g) van en "Delicatessen" en cambio: anchoas,
boquerones, pulpitos, vieiras, langostinos, mejillones, calamares,
choritos/mejillones en escabeche, salmon ahumado, jibias, berberechos
- cualquier marisco o pescado que no sea atun/sardina/caballa comun.
Si tenes dudas de si algo es "premium", el precio por kg suele ser
la pista: si ronda o supera los $50.000/kg, probablemente es
Delicatessen.

"Limpieza del Hogar" es para productos que limpian la CASA
(pisos, baños, ropa, cocina, superficies). Los jabones/geles/
productos de HIGIENE PERSONAL (ej. "Gel de Limpieza Dermaglos",
"Crema de Limpieza Pond's", jabon facial, gel corporal) NO van aca
aunque digan "limpieza" en el nombre - van en "Otros / Sin
Categoria" si no hay una categoria mas especifica en la lista.

Los productos de CUIDADO DE CALZADO (ej. "Renovador de Gamuza y
Nobuck", pomada para zapatos, impermeabilizante de calzado) tampoco
son "Limpieza del Hogar" - van en "Otros / Sin Categoria".

Ademas, calcula la cantidad normalizada y su unidad, para poder
comparar precio por kg, por litro o por unidad segun corresponda.
Aplica estas reglas EN ORDEN - la primera que aplique gana, no sigas
evaluando las siguientes:

1. PRIORIDAD MAXIMA - si el nombre menciona una cantidad de piezas
   individuales vendidas juntas (capsulas, sobres, saquitos, rollos,
   unidades, bultos - ej. "x 12 Un.", "x 10 capsulas", "x 4 rollos",
   "x 25 saquitos"), usa SIEMPRE unidad_normalizada = "unidad" y
   cantidad_normalizada = esa cantidad de piezas (ej. 12, 10, 4, 25).
   Esto aplica AUNQUE el nombre tambien mencione un peso o volumen
   total (ej. "Cafe en Capsula Starbucks x 12 Un." son 12 unidades,
   NO importa cuantos gramos pesen las 12 juntas - normalizar por
   peso en este caso da un precio por kilo sin sentido real, porque
   nadie compra cafe en capsulas por kilo).
1.5. Si el producto es un REPUESTO o RECAMBIO chico de un solo uso
   que se compra como pieza unica y NO se compra "a granel" ni se
   escala a litros/kilos (ej. "Repuesto de Aromatizante 21 cc",
   "Aparato + Repuesto de Ambientes"), usa unidad_normalizada =
   "unidad" y cantidad_normalizada = 1 (a menos que el nombre
   indique explicitamente que son varios repuestos juntos, en cuyo
   caso usa esa cantidad y aplica la regla 1). NO conviertas su
   volumen chico (ej. 21 cc) a litros - un frasquito de 21 cc
   extrapolado a "precio por litro" da un numero sin sentido real,
   porque nadie compra un litro entero de esencia de aromatizante.
2. Si NO aplica ninguna regla anterior, y el producto se vende por
   peso (ej. "500 g", "1 Kg", "2,25 Kg"): unidad_normalizada = "kg",
   cantidad_normalizada = la cantidad convertida a kilogramos
   (ej. "500 g" -> 0.5).
3. Si NO aplica ninguna regla anterior, y se vende por volumen (ej.
   "900 cc", "1,5 Lt", "2 L"): unidad_normalizada = "l",
   cantidad_normalizada = la cantidad convertida a litros
   (ej. "900 cc" -> 0.9).
4. Si no se puede determinar ninguna cantidad del nombre,
   cantidad_normalizada = null.
5. EXCEPCION a las reglas 2 y 3 (no a la 1): si la categoria elegida
   es "Especias y Condimentos", NO uses "kg" - estos productos se
   venden en frascos chicos (10 a 100 g) y nadie los compra por
   kilo, asi que "precio por kilo" no sirve para compararlos. En su
   lugar usa base 100 GRAMOS: unidad_normalizada = "100g",
   cantidad_normalizada = la cantidad convertida a paquetes de 100g
   (ej. "Pimienta 35 g" -> 0.35, "Oregano 100 g" -> 1.0, "Laurel
   10 g" -> 0.1).

Respondé SOLO un JSON con este formato exacto, sin texto antes ni
despues, sin backticks de markdown:
{{"categoria": "...", "cantidad_normalizada": 0.0, "unidad_normalizada": "..."}}
"""


# --- Llamado a Gemini ------------------------------------------------------

def clasificar_producto(cliente: "genai.Client", nombre_producto: str) -> dict | None:
    """
    Le pide a Gemini que clasifique UN producto (categoria +
    normalizacion) en una sola llamada. Devuelve el dict parseado, o
    None si algo fallo (respuesta invalida, error de la API, etc.) -
    nunca rompe el flujo, el producto queda pendiente para la
    proxima corrida.
    """
    prompt = PROMPT_TEMPLATE.format(
        nombre_producto=nombre_producto,
        lista_categorias="\n".join(f"- {c}" for c in CATEGORIAS_VALIDAS),
    )

    try:
        respuesta = cliente.models.generate_content(
            model=MODELO_GEMINI,
            contents=prompt,
        )
    except Exception as error:
        print(f"    ERROR llamando a Gemini: {type(error).__name__}: {error}")
        return None

    texto = (respuesta.text or "").strip()

    # Por si Gemini decide envolver la respuesta en backticks de
    # markdown a pesar de que se lo pedimos que no lo haga.
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        print(f"    Respuesta de Gemini no es JSON valido: {texto[:200]!r}")
        return None

    categoria = datos.get("categoria")
    if categoria not in CATEGORIAS_VALIDAS:
        print(f"    Gemini devolvio una categoria fuera de la lista: {categoria!r} - se descarta.")
        return None

    unidad = datos.get("unidad_normalizada")
    if unidad not in UNIDADES_VALIDAS:
        unidad = None

    cantidad = datos.get("cantidad_normalizada")
    if not isinstance(cantidad, (int, float)):
        cantidad = None

    # Correccion automatica por codigo [agregado 20/8/2026]: para
    # "Desodorante de Ambientes", cualquier producto con menos de
    # 150 ml es casi seguro un frasco de un solo uso (repuesto,
    # difusor, minispray, aromatizante de placard/calzado, etc.) que
    # no se compra "a granel" - extrapolar su precio a 1 litro entero
    # da un numero sin sentido real. En vez de confiar en que Gemini
    # reconozca todas las formas posibles de nombrar esto (regla 1.5
    # del prompt ayuda pero no cubre todos los casos, ej. "Difusor de
    # Aromas 100 Ml" no dice "repuesto" ni "aparato"), se fuerza esta
    # conversion siempre, de forma determinista, sin depender del
    # criterio de Gemini.
    #
    # [Ampliado 20/8/2026] Ademas del umbral de volumen, se suma un
    # chequeo por palabra clave: productos "repuesto" o "automatico"
    # de hasta 300 ml (ej. "Air Wick Freshmatic aparato + repuesto
    # 250 ml") tambien son de un solo uso/recambio, aunque su volumen
    # sea mayor a 150ml - el volumen solo no alcanza para detectarlos
    # sin arriesgar convertir por error un aerosol grande comun.
    #
    # Se quitan los acentos antes de comparar (unicodedata) porque
    # "automatico" sin tilde NO matcheaba contra "automático" con
    # tilde letra por letra - bug real encontrado y corregido en la
    # verificacion de este mismo cambio.
    import unicodedata
    nombre_sin_acentos = unicodedata.normalize("NFKD", nombre_producto.lower())
    nombre_sin_acentos = "".join(c for c in nombre_sin_acentos if not unicodedata.combining(c))
    es_repuesto_o_automatico = "repuesto" in nombre_sin_acentos or "automat" in nombre_sin_acentos

    if categoria == "Desodorante de Ambientes" and unidad == "l" and cantidad is not None:
        if cantidad < 0.15 or (es_repuesto_o_automatico and cantidad < 0.3):
            unidad = "unidad"
            cantidad = 1.0

    # Correccion determinista para "Aceite en Spray" / "Rocio Vegetal"
    # [agregado 20/8/2026]: son aerosoles de cocina en frascos chicos
    # (100-120g), un producto totalmente distinto al aceite liquido
    # comun en botella - no se compra "a granel" ni se compara bien
    # por kilo (mismo patron que los repuestos de aromatizantes).
    if categoria == "Aceites" and unidad in ("kg", "l") and cantidad is not None:
        if "spray" in nombre_sin_acentos or "rocio" in nombre_sin_acentos:
            unidad = "unidad"
            cantidad = 1.0

    # Correccion determinista para "Limpieza del Hogar" [agregado
    # 20/8/2026, ajustado en la misma sesion]: mismo patron que
    # aromatizantes/aceite en spray - productos chicos de un solo uso
    # (discos adhesivos, canastas en gel, pastillas/tabletas,
    # capsulas de lavavajillas, quitamanchas en gel/stick, repelentes
    # en crema, bloques para inodoro, hormiguicidas/insecticidas)
    # normalizados por kg/l daban precios absurdos.
    #
    # OJO: el umbral general se mantiene en 100g/100ml (NO se subio a
    # 250g) porque se encontraron ~30 limpiadores CONCENTRADOS
    # legitimos de 100ml (ej. "Limpiador Concentrado Baño Procenex
    # 100ml, rinde 300ml al diluir") que son productos normales de
    # compra repetida, no de un solo uso - convertirlos a unidad les
    # haria perder el precio por litro del concentrado, que sigue
    # siendo un dato util. Las palabras clave especificas si llegan
    # hasta 400g, porque esos SI son siempre de un solo uso sin
    # importar el peso exacto.
    if categoria == "Limpieza del Hogar" and unidad in ("kg", "l") and cantidad is not None:
        palabras_un_solo_uso = (
            "disco" in nombre_sin_acentos or "pastilla" in nombre_sin_acentos
            or "canasta" in nombre_sin_acentos or "pomada" in nombre_sin_acentos
            or "brillo magico" in nombre_sin_acentos or "capsula" in nombre_sin_acentos
            or "antihumedad" in nombre_sin_acentos
            or "tableta" in nombre_sin_acentos or "bloque" in nombre_sin_acentos
            or "hormiguicida" in nombre_sin_acentos or "repelente" in nombre_sin_acentos
            or "quitamanchas" in nombre_sin_acentos
        )
        if cantidad < 0.1 or (palabras_un_solo_uso and cantidad < 0.4):
            unidad = "unidad"
            cantidad = 1.0

        # Los AEROSOLES se compran "por lata", no a granel - sin
        # importar el tamano (una lata de 500ml sigue siendo UNA
        # lata que se compra entera). Sin limite de cantidad, a
        # diferencia de las palabras clave de arriba.
        if unidad in ("kg", "l") and (
            "aerosol" in nombre_sin_acentos or "insecticida" in nombre_sin_acentos
        ):
            unidad = "unidad"
            cantidad = 1.0

    # Red de seguridad generica [agregado 20/8/2026, ampliada tras
    # el caso del Te Taragui 50 Saquitos]: la Regla 1 del prompt le
    # pide a Gemini que priorice "unidad" cuando el nombre menciona
    # una cantidad de piezas (ej. "x 12 Un."), pero se encontraron 2
    # casos reales donde Gemini no la aplico:
    # - "Jabon En Capsulas... 3 En 1 20 U 400 G" quedo en kg
    # - "Te Sin Filtro Diamantado Taragui 50 Saquitos" quedo en kg
    #   (0.05 kg en vez de 50 unidad) - este bug NO se notaba dentro
    #   de la categoria (el precio/kg no parecia absurdo), recien se
    #   detecto al comparar el mismo EAN entre tiendas: Vea daba
    #   $42.400/"kg" contra $36-41/saquito en las otras 2 tiendas.
    # En vez de confiar solo en que Gemini aplique la regla siempre,
    # se agrega este chequeo determinista con 2 patrones: "numero+U"
    # (20 U, 12 Un.) y "numero+Saquito/s" (50 Saquitos).
    if unidad != "unidad":
        match_unidades = re.search(r"\b(\d+)\s*[Uu]n?\.?\b", nombre_producto)
        match_saquitos = re.search(r"\b(\d+)\s*[Ss]aquitos?\b", nombre_producto)
        match = match_unidades or match_saquitos
        if match:
            cantidad_detectada = float(match.group(1))
            if 1 <= cantidad_detectada <= 1000:
                unidad = "unidad"
                cantidad = cantidad_detectada

    # Filtro de sanidad [agregado 20/8/2026, tras encontrar casos
    # reales rotos]: Gemini a veces devuelve una cantidad absurda
    # (ej. 0.0001 en vez de 200 para "x 200 Un.") - eso dispara el
    # precio_normalizado a millones y arruina las estadisticas de
    # toda la categoria. Ningun producto de supermercado pesa menos
    # de 10 gramos (0.01 kg) ni mas de 50 kg/L, y ningun bulto tiene
    # menos de 1 o mas de 1000 unidades - fuera de esos rangos,
    # descartamos el valor (queda None) en vez de guardar un numero
    # que sabemos que esta mal.
    if cantidad is not None and unidad is not None:
        if unidad in ("kg", "l") and not (0.01 <= cantidad <= 50):
            print(f"    Cantidad normalizada fuera de rango ({cantidad} {unidad}) - se descarta.")
            cantidad = None
            unidad = None
        elif unidad == "100g" and not (0.05 <= cantidad <= 20):
            # Base 100g: un frasco de especias real pesa entre 5 g
            # (0.05 * 100g) y 2 kg (20 * 100g) - fuera de eso, se
            # descarta.
            print(f"    Cantidad normalizada fuera de rango ({cantidad} {unidad}) - se descarta.")
            cantidad = None
            unidad = None
        elif unidad == "unidad" and not (1 <= cantidad <= 1000):
            print(f"    Cantidad normalizada fuera de rango ({cantidad} {unidad}) - se descarta.")
            cantidad = None
            unidad = None

    return {
        "categoria": categoria,
        "cantidad_normalizada": cantidad,
        "unidad_normalizada": unidad,
    }


# --- Orquestacion ---------------------------------------------------------

def correr_tanda(limite: int) -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY no esta configurada en el .env de esta carpeta.")
        return

    cliente = genai.Client(api_key=api_key)

    productos = precios_db.obtener_productos_sin_clasificar(limite=limite)

    if not productos:
        print("No hay productos pendientes de clasificar. Todo al dia.")
        return

    print(f"Tanda de hoy: {len(productos)} productos sin clasificar.\n")

    clasificados = 0
    fallidos = 0

    for indice, producto in enumerate(productos, start=1):
        codigo = producto["codigo_producto"]
        nombre = producto["nombre"]

        print(f"[{indice}/{len(productos)}] {nombre}")

        resultado = clasificar_producto(cliente, nombre)

        if resultado:
            precios_db.guardar_clasificacion_ia(
                codigo_producto=codigo,
                categoria_ia=resultado["categoria"],
                cantidad_normalizada=resultado["cantidad_normalizada"],
                unidad_normalizada=resultado["unidad_normalizada"],
            )
            print(f"    -> {resultado['categoria']} | "
                  f"{resultado['cantidad_normalizada']} {resultado['unidad_normalizada']}")
            clasificados += 1
        else:
            fallidos += 1

        if indice < len(productos):
            time.sleep(SEGUNDOS_ENTRE_PEDIDOS)

    print("\n--- Resumen de la tanda ---")
    print(f"  Clasificados y guardados: {clasificados}")
    print(f"  Fallidos (quedan para la proxima corrida): {fallidos}")


def main():
    parser = argparse.ArgumentParser(
        description="Clasifica productos con Gemini (categoria + normalizacion), de a tandas."
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=LIMITE_POR_DEFECTO,
        help=f"Cantidad maxima de productos a procesar en esta corrida (default: {LIMITE_POR_DEFECTO}).",
    )
    args = parser.parse_args()

    correr_tanda(args.limite)


if __name__ == "__main__":
    main()
