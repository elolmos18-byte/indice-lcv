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
    "Sal y Especias",
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
    "Carbon y Elementos para Fuego",
    "Otros / Sin Categoria",
]

UNIDADES_VALIDAS = ["kg", "l", "unidad"]

PROMPT_TEMPLATE = """Sos un clasificador de productos de supermercado argentino.

Producto: "{nombre_producto}"

Elegi la categoria MAS CERCANA de esta lista (copia el texto EXACTO,
no inventes una nueva):
{lista_categorias}

Ademas, calcula la cantidad normalizada y su unidad, para poder
comparar precio por kg, por litro o por unidad segun corresponda:
- Si el producto se vende por peso (ej. "500 g", "1 Kg", "2,25 Kg"):
  unidad_normalizada = "kg", cantidad_normalizada = la cantidad
  convertida a kilogramos (ej. "500 g" -> 0.5).
- Si se vende por volumen (ej. "900 cc", "1,5 Lt", "2 L"):
  unidad_normalizada = "l", cantidad_normalizada = la cantidad
  convertida a litros (ej. "900 cc" -> 0.9).
- Si se vende por unidad/bulto sin peso ni volumen claro en el
  nombre (ej. "Huevos x 12 un.", "Papel Higienico x 4 rollos"):
  unidad_normalizada = "unidad", cantidad_normalizada = la cantidad
  de unidades/bultos (ej. 12, o 4).
- Si no se puede determinar la cantidad del nombre, cantidad_normalizada = null.

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
