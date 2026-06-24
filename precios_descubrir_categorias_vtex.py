"""
precios_descubrir_categorias_vtex.py

Cuando arrancamos a buscar los 37 productos de la canasta CCV-37 en
Changomas y Carrefour, nos encontramos con que esos sitios tienen
miles de productos repartidos en decenas de categorias - y nadie
quiere copiar a mano 50 URLs.

Lo que hace este script: agarra UNA pagina del sitio (por ejemplo la
de Almacen) y lista TODOS los links de categoria que encuentra
adentro - los del panel lateral, los del menu, todos. Despues vos y
yo (Claude) miramos juntos esa lista y elegimos cuales sirven para
los 37 productos. El resto se descarta.

El script no decide nada por su cuenta. Solo trae la informacion.

Como funciona, paso por paso:
1. Recibe una URL como argumento (por ejemplo, la del Almacen de
   Changomas).
2. Pide esa pagina con requests, usando headers de navegador real.
3. Parsea el HTML con BeautifulSoup y busca todos los <a href="...">.
4. Filtra: solo se queda con los links que:
   - Son del mismo dominio (no nos interesan links a otros sitios).
   - NO terminan en "/p" (esa es la convencion de VTEX para paginas
     de productos individuales, no de categorias).
   - NO son la URL exacta de la pagina que estamos mirando (sino se
     auto-referencia).
5. Le quita duplicados (los menus de los sitios repiten cada link 2
   o 3 veces - version mobile, desktop, breadcrumb).
6. Imprime cada link con su texto del boton/checkbox.
7. Guarda todo en un archivo .txt para revisar despues con calma.

Como correrlo:
    python precios_descubrir_categorias_vtex.py "https://www.masonline.com.ar/3454?map=productClusterIds"

El archivo de salida se llama segun el dominio:
    categorias_encontradas_masonline.txt
    categorias_encontradas_carrefour.txt
"""

import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Headers que imitan un navegador real. Sin esto, los sitios VTEX
# rechazan el pedido como si fuera un bot.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


def descubrir_categorias(url_inicial: str) -> list[tuple[str, str]]:
    """
    Pide la pagina y devuelve una lista de (texto_del_link, url)
    para cada link de categoria que encuentre, sin duplicados.

    "Link de categoria" = cualquier link del mismo dominio que no
    termine en /p (productos individuales).
    """
    respuesta = requests.get(url_inicial, headers=HEADERS, timeout=15)
    respuesta.raise_for_status()

    soup = BeautifulSoup(respuesta.text, "html.parser")
    dominio_origen = urlparse(url_inicial).netloc

    encontrados = {}  # url -> texto, para autodescartar duplicados

    for enlace in soup.find_all("a", href=True):
        href = enlace["href"].strip()
        if not href:
            continue

        # urljoin maneja tanto links relativos ("/aceites") como
        # absolutos ("https://www.masonline.com.ar/aceites").
        url_completa = urljoin(url_inicial, href)

        # Solo nos quedamos con links del mismo dominio.
        if urlparse(url_completa).netloc != dominio_origen:
            continue

        # Las paginas de producto individual de VTEX terminan en /p.
        # No nos interesan - solo queremos categorias.
        if url_completa.rstrip("/").endswith("/p"):
            continue

        # No nos auto-referenciamos a la misma pagina que estamos
        # mirando (ej: el link "Almacen" dentro de la propia pagina
        # de Almacen).
        if url_completa.rstrip("/") == url_inicial.rstrip("/"):
            continue

        # Si ya vimos esta URL en otro lugar de la pagina, no la
        # duplicamos.
        if url_completa in encontrados:
            continue

        texto = enlace.get_text(strip=True) or "(sin texto)"
        encontrados[url_completa] = texto

    # Devolvemos como lista ordenada por texto, mas facil de leer
    # despues.
    return sorted(
        [(texto, url) for url, texto in encontrados.items()],
        key=lambda par: par[0].lower(),
    )


def main():
    if len(sys.argv) < 2:
        print('Uso: python precios_descubrir_categorias_vtex.py "<url>"')
        print("Ejemplo:")
        print('  python precios_descubrir_categorias_vtex.py "https://www.masonline.com.ar/3454?map=productClusterIds"')
        sys.exit(1)

    url = sys.argv[1]
    print(f"Descubriendo categorias en: {url}\n")

    try:
        categorias = descubrir_categorias(url)
    except requests.RequestException as error:
        print(f"No se pudo acceder a la pagina: {error}")
        sys.exit(1)

    if not categorias:
        print("No se encontro ningun link en esta pagina.")
        return

    # El nombre del archivo de salida lo armamos a partir del dominio,
    # para que sea claro de donde vino sin tener que abrir el archivo.
    # masonline.com.ar -> categorias_encontradas_masonline.txt
    dominio = urlparse(url).netloc.replace("www.", "").split(".")[0]
    archivo_salida = f"categorias_encontradas_{dominio}.txt"

    with open(archivo_salida, "w", encoding="utf-8") as f:
        for texto, url_categoria in categorias:
            linea = f"{texto} -> {url_categoria}"
            print(linea)
            f.write(linea + "\n")

    print(f"\n{len(categorias)} links encontrados. Guardados en {archivo_salida}")


if __name__ == "__main__":
    main()
