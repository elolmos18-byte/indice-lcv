"""
precios_descubrir_arbol_vtex.py

Descubre TODAS las categorias relevantes de un super VTEX (Changomas
o Carrefour) usando la API publica que devuelve el arbol completo.

Por que este script y no el anterior (precios_descubrir_categorias_vtex.py):
- El anterior leia el HTML de una pagina puntual. Pero las paginas
  hub de VTEX renderizan el panel lateral con JavaScript, asi que
  desde HTML plano solo se ven los menus principales (8 links, no
  las 50+ subcategorias).
- Este nuevo le pega directo a la API publica de catalogo de VTEX:
  /api/catalog_system/pub/category/tree/3
  Esa API devuelve el arbol completo, con URLs legibles, sin
  necesidad de JavaScript ni de scrapear nada.

Como funciona, paso por paso:
1. Recibe el dominio del super como argumento (changomas o carrefour).
2. Llama a la API de arbol de categorias VTEX.
3. Filtra el arbol con tres criterios:
   a) Solo departamentos relevantes para la canasta CCV-37
      (almacen, lacteos, bebidas).
   b) Descarta categorias "Old" o de uso interno.
   c) Solo se queda con categorias "hoja" (nivel 2 y 3, donde hay
      productos) - descarta los departamentos puros (nivel 1, que
      solo agrupan).
4. Imprime la lista y la guarda en un archivo .txt listo para usar
   como insumo en el proximo paso.

Como correrlo:
    python precios_descubrir_arbol_vtex.py changomas
    python precios_descubrir_arbol_vtex.py carrefour
"""

import sys

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}

# Mapeo super -> dominio. Si en el futuro sumamos otro super VTEX,
# alcanza con agregarlo aca.
DOMINIOS = {
    "changomas": "www.masonline.com.ar",
    "carrefour": "www.carrefour.com.ar",
}

# Nombres de departamentos (nivel 1) que SI nos interesan. Es una
# lista blanca - cualquier departamento que no este aca, se descarta.
#
# Los nombres son los que usan Changomas y Carrefour en su arbol
# VTEX, agrupados aca por intencion (Almacen / Lacteos y Frescos /
# Bebidas) aunque cada super los llame distinto.
#
# La comparacion se hace en minusculas y sin acentos, asi que se
# pueden poner como esten - solo importa el texto, no la capitalizacion.
DEPARTAMENTOS_RELEVANTES = [
    # --- ALMACEN ---
    # Carrefour agrupa todo bajo "Almacen"
    "almacen",
    "alimentos",
    # Carrefour separa el "Desayuno y merienda" como departamento aparte,
    # ahi viven galletitas, yerba, cafe, te, mermelada, azucar, dulce de leche
    "desayuno y merienda",
    # Changomas pone cada rubro como departamento de nivel 1
    "aceites, vinagres y aderezos",
    "arroz, legumbres y pastas",
    "caldos, sopas y pure",
    "condimentos y especias",
    "conservas y enlatados",
    "desayunos y meriendas",
    "harinas",
    "reposteria",

    # --- LACTEOS Y FRESCOS ---
    "lacteos y productos frescos",   # Carrefour
    "frescos y congelados",
    "lacteos",                       # Changomas
    "quesos",
    "huevos",                        # Changomas pone huevos como departamento de nivel 1
    "fiambres y embutidos",

    # --- BEBIDAS ---
    "bebidas",                       # Carrefour agrupa todo bajo "Bebidas"
    "gaseosas",                      # Changomas las separa
    "aguas",
    "jugos",
]

# Palabras que, si aparecen en el nombre de la categoria, hacen que
# la descartemos. Son restos del sistema viejo o categorias internas.
PALABRAS_DESCARTE = ["old", "mercadolibre", "categoria mercadolibre"]


def normalizar(texto: str) -> str:
    """
    Para comparar nombres de categoria sin que importen mayusculas,
    acentos o espacios extra.
    """
    import unicodedata
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return sin_acentos.lower().strip()


def es_departamento_relevante(nombre: str) -> bool:
    nombre_norm = normalizar(nombre)
    return nombre_norm in DEPARTAMENTOS_RELEVANTES


def hay_que_descartar(nombre: str) -> bool:
    nombre_norm = normalizar(nombre)
    return any(palabra in nombre_norm for palabra in PALABRAS_DESCARTE)


def pedir_arbol(dominio: str) -> list:
    """
    Pide a la API publica de VTEX el arbol completo de categorias,
    hasta 3 niveles de profundidad.
    """
    url = f"https://{dominio}/api/catalog_system/pub/category/tree/3"
    respuesta = requests.get(url, headers=HEADERS, timeout=15)
    respuesta.raise_for_status()
    return respuesta.json()


def recorrer_arbol(arbol: list) -> list[dict]:
    """
    Devuelve una lista plana de categorias hoja, cada una con su
    departamento padre, su nombre y su URL. Solo incluye categorias
    de departamentos relevantes para la canasta CCV-37, y descarta
    las "Old".
    """
    resultados = []

    for departamento in arbol:
        nombre_depto = departamento.get("name", "")

        if not es_departamento_relevante(nombre_depto):
            continue
        if hay_que_descartar(nombre_depto):
            continue

        sub_departamentos = departamento.get("children", [])

        # Caso especial: si el departamento esta en la lista blanca pero
        # NO tiene subcategorias (ej: "Huevos" en Changomas), los productos
        # viven directamente en el departamento - lo incluimos tal cual.
        if not sub_departamentos:
            url = departamento.get("url")
            if url:
                resultados.append({
                    "departamento": nombre_depto,
                    "nombre": nombre_depto,
                    "url": url,
                })
            continue

        # Bajamos al nivel 2 (categoria) y nivel 3 (subcategoria),
        # quedandonos con todo lo que tenga URL.
        for categoria in sub_departamentos:
            if hay_que_descartar(categoria.get("name", "")):
                continue

            sub_hijos = categoria.get("children", [])

            if not sub_hijos:
                # Si no tiene subcategorias, la propia categoria es hoja.
                resultados.append({
                    "departamento": nombre_depto,
                    "nombre": categoria.get("name"),
                    "url": categoria.get("url"),
                })
            else:
                # Si tiene subcategorias, esas son las hojas con productos.
                for subcategoria in sub_hijos:
                    if hay_que_descartar(subcategoria.get("name", "")):
                        continue
                    resultados.append({
                        "departamento": nombre_depto,
                        "nombre": f"{categoria.get('name')} > {subcategoria.get('name')}",
                        "url": subcategoria.get("url"),
                    })

    return resultados


def guardar_archivo(categorias: list[dict], nombre_archivo: str):
    """
    Escribe las URLs agrupadas por departamento, con comentarios para
    que sea facil de leer y revisar.
    """
    # Agrupamos por departamento, manteniendo el orden en que aparecieron.
    grupos = {}
    for cat in categorias:
        grupos.setdefault(cat["departamento"], []).append(cat)

    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write(f"# Categorias descubiertas automaticamente\n")
        f.write(f"# Total: {len(categorias)} categorias\n")
        f.write(f"# Revisar y filtrar segun los 37 productos de la CCV-37.\n\n")

        for depto, cats in grupos.items():
            f.write(f"\n# === {depto.upper()} ({len(cats)}) ===\n")
            for cat in cats:
                f.write(f"# {cat['nombre']}\n")
                f.write(f"{cat['url']}\n")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in DOMINIOS:
        print("Uso: python precios_descubrir_arbol_vtex.py <super>")
        print(f"Donde <super> es uno de: {', '.join(DOMINIOS.keys())}")
        sys.exit(1)

    super_elegido = sys.argv[1]
    dominio = DOMINIOS[super_elegido]
    archivo_salida = f"precios_categorias_{super_elegido}.txt"

    print(f"Pidiendo arbol de categorias a {dominio}...")
    try:
        arbol = pedir_arbol(dominio)
    except requests.RequestException as error:
        print(f"No se pudo acceder a la API: {error}")
        sys.exit(1)

    print(f"Arbol recibido, recorriendo y filtrando...")
    categorias = recorrer_arbol(arbol)

    if not categorias:
        print("No se encontro ninguna categoria relevante.")
        print("Puede que los nombres de departamento de este super no esten")
        print("en la lista DEPARTAMENTOS_RELEVANTES - revisar el codigo.")
        return

    guardar_archivo(categorias, archivo_salida)

    print(f"\n{len(categorias)} categorias guardadas en {archivo_salida}")
    print("Revisalas y descarta las que no sirvan para la canasta CCV-37.")


if __name__ == "__main__":
    main()
