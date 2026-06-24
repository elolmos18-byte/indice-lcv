# INDICE LCV — MAESTRO v1.0

> Indice de precios local de Puerto Madryn, basado en la metodologia
> de la Canasta Basica Alimentaria del INDEC, aplicada a los tres
> supermercados con catalogo online de la ciudad.

---

## Vision

Pagina publica que muestra una canasta basica de 37 productos
alimenticios comparada entre los tres supermercados con catalogo
online de Puerto Madryn — La Anonima, Carrefour y Changomas —
actualizada semanalmente de forma automatica.

El objetivo es darle a los Guardianes de La Comunidad del Viento un
precio de referencia real para evaluar las ofertas que los comercios
locales publican en LCV. Tambien funciona como indice publico de
precios locales — algo que hoy nadie publica para Madryn.

El proyecto Indice LCV vive aparte de LCV (carpeta propia en el VPS,
base de datos propia), pero comparte el mismo dominio y servidor. Si
en algun momento se decide integrarlo mas a fondo con LCV, esa
migracion es posible — pero arrancar separado deja el proyecto libre
de tocar el codigo de produccion de LCV.

---

## Que hace y que no hace

### Que hace

- Scrapea automaticamente los precios de 37 productos en los tres
  supermercados, una vez por semana.
- Guarda cada "foto semanal" en una base historica.
- Publica una pagina `/precios` con la comparacion mas reciente y
  marca cual super tiene el precio mas bajo de cada producto.
- Calcula el costo total de la canasta en cada super y publica el
  Indice LCV que muestra como evoluciona en el tiempo.
- Detecta ofertas reales (precio actual significativamente por debajo
  del precio de lista o del promedio historico).

### Que NO hace (a proposito, para mantenerlo simple)

- No es un comparador interactivo donde el usuario arma su lista.
- No alerta por Telegram cuando hay ofertas.
- No incluye supermercados chicos locales (Anbar, Tatay, etc.) —
  no tienen catalogo online.
- No incluye productos frescos (carnes, frutas, verduras, pan
  fresco). Esos no tienen marca + tamano estable y necesitarian
  metodologia manual; quedan para una fase posterior.
- No incluye no-alimentos (limpieza, higiene). La CBA del INDEC es
  solo alimentos; si se incluyen mas adelante, seria como Canasta
  Basica Total (CBT), un proyecto separado.
- No vende, no recomienda comercios, no integra con Mercado Pago.

---

## La canasta — CCV-37

CCV = Canasta Comunidad del Viento. 37 productos. Basada en la
Canasta Basica Alimentaria (CBA) del INDEC. Se incluyen solo
productos que cumplen tres requisitos:

1. Estan en los tres supermercados.
2. Tienen marca + tamano fijos (codigo de barras comparable).
3. Son representativos del consumo de un hogar de Madryn.

Las marcas y tamanos exactos se definen en Fase 1 (ver mas abajo),
con criterio de "lo mas vendido o mas estandar disponible en los
tres supers". Esta seccion define solo el armazon de 37 rubros.

| Categoria CBA INDEC | Rubros | Cantidad |
|---|---|---|
| Pan, harinas y derivados | Harina 000, harina leudante, fideos largos, fideos cortos, arroz, polenta, galletitas dulces, galletitas saladas | 8 |
| Azucar y dulces | Azucar, dulce de leche, mermelada | 3 |
| Aceites y grasas | Aceite girasol, aceite mezcla, manteca | 3 |
| Lacteos | Leche entera, leche descremada, yogur firme, yogur bebible, queso untable | 5 |
| Huevos | Huevos x6 | 1 |
| Legumbres y conservas | Arvejas en lata, lentejas, atun en lata, salsa de tomate, pure de tomate | 5 |
| Condimentos y aderezos | Sal fina, sal gruesa, vinagre, mayonesa, ketchup, mostaza | 6 |
| Infusiones | Yerba, cafe, te | 3 |
| Bebidas no alcoholicas | Gaseosa cola, agua mineral, jugo en polvo | 3 |
| **Total** | | **37** |

---

## Arquitectura

```
+--------------------------------------------------+
|                  USUARIO FINAL                   |
|             (visitante de la web)                |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|     Pagina /precios (HTML estatico + JS)         |
|     Tabla comparativa + grafico Indice LCV       |
+-------------------------+------------------------+
                          |
                          | fetch JSON
                          v
+--------------------------------------------------+
|     FastAPI propio  (servicio separado de LCV)   |
|     Endpoint publico GET /precios/canasta        |
+-------------------------+------------------------+
                          |
                          v
+--------------------------------------------------+
|     SQLite local (precios_historico.db)          |
|     Fotos semanales acumuladas                   |
+-------------------------+------------------------+
                          ^
                          | escribe cada lunes 9 AM (cron)
                          |
+--------------------------------------------------+
|     Scrapers Python                              |
|     - precios_buscar_canasta.py (los 3 supers)   |
|     - Lee La Anonima por JSON-LD                 |
|     - Lee Carrefour y Changomas por API VTEX     |
+--------------------------------------------------+
```

**El bot de LCV y el resto del sistema de Comunidad del Viento no
tocan nada de este proyecto.** La unica conexion futura — si se
decide hacerla — seria que el bot de LCV consulte el endpoint
`/precios/canasta` para mostrar precios de referencia al lado de las
ofertas de los comercios locales. Pero eso es opcional, queda para
Fase 6.

---

## Stack tecnologico

| Capa | Tecnologia | Por que esta eleccion |
|---|---|---|
| Scraping | Python + requests + BeautifulSoup | Suficiente para JSON-LD y APIs publicas. Sin Selenium, no necesitamos JavaScript |
| Base de datos | SQLite (un archivo) | Para 37 productos x 3 supers x 52 semanas/ano = ~5800 filas/ano. SQLite sobra y no necesita servidor |
| Backend | FastAPI | Mismo stack que LCV. Conocido, rapido, simple |
| Frontend | HTML + CSS + JS vanilla | La pagina es una tabla y un grafico. No necesita framework |
| Programacion automatica | cron del VPS | Una corrida por semana, no justifica nada mas complejo |
| Hosting | Mismo VPS de LCV (Hostinger) | Aprovechamos infraestructura existente |

---

## Convencion de nombres de archivo

Todos los archivos del proyecto Indice LCV llevan el prefijo
`precios_` — tanto los `.py` como los `.md`. Esto los distingue
visualmente de los archivos del proyecto LCV cuando ambos comparten
servidor o se versionan en repos separados.

Ejemplos:
- `precios_MAESTRO.md`, `precios_METODOLOGIA.md`
- `precios_buscar_canasta.py`, `precios_guardar_foto.py`,
  `precios_servir_api.py`

---

## Reglas del proyecto

Decisiones tomadas que no se discuten mas, salvo razon de fuerza
mayor. Ponerlas por escrito acumula deuda tecnica menos rapido.

- **Vive en `/home/lcv/indice-lcv/` en el VPS.** Carpeta propia.
- **Base SQLite propia,** no toca Postgres de LCV.
- **Entorno virtual propio** (`venv/`), aislado del de LCV.
- **El endpoint publico es solo lectura.** No hay forma de modificar
  datos via web.
- **La canasta es fija.** Productos solo se agregan o sacan por
  decision consciente y documentada, no automaticamente. Si la
  composicion cambia, se anota en un changelog del proyecto.
- **Si un producto desaparece del catalogo de algun super,** se
  registra como "sin dato" esa semana — no se inventa precio ni se
  toma el de otra semana.
- **El sitio de Carrefour viejo (`supermercado.carrefour.com.ar`)
  no se toca.** Solo el sitio nuevo (`www.carrefour.com.ar`).
- **Productos sin stock se descartan** del relevamiento — sus precios
  pueden estar desactualizados.

---

## Fases de desarrollo

### Fase 1 — Definir la canasta concreta
- Para cada uno de los 37 rubros, identificar marca + tamano que este
  disponible en los tres supers
- Guardarla en un archivo `canasta.json` versionado

### Fase 2 — Scraper de canasta
- Script `precios_buscar_canasta.py` que toma `canasta.json` y para
  cada producto consulta los tres supers, devolviendo precio + URL
  en cada uno
- Maneja productos no encontrados como "sin dato", no como error

### Fase 3 — Histórico semanal
- Base `precios_historico.db` (SQLite) que guarda cada corrida con
  fecha
- Script `precios_guardar_foto.py` que orquesta el proceso completo
- Cron en el VPS los lunes 9:00 AM
- Log de cada corrida en archivo de texto

### Fase 4 — Endpoint publico
- Servicio FastAPI propio (en su carpeta, su venv, su systemd o
  supervisor)
- `GET /precios/canasta` → JSON con la foto mas reciente
- `GET /precios/indice` → JSON con la evolucion del Indice LCV
- Sin auth, solo lectura, con CORS abierto

### Fase 5 — Pagina web
- HTML + CSS + JS vanilla en `/var/www/precios/` (o donde nginx lo
  sirva)
- Tabla comparativa: producto x super, con celda mas barata
  resaltada
- Grafico simple del Indice LCV en el tiempo
- Fecha de la ultima actualizacion bien visible
- Nota legal: "datos publicados por los supermercados, no
  garantizamos exactitud"

### Fase 6 — Integracion suave con LCV (opcional)
- Cuando un Guardian publica una oferta en LCV, el bot consulta
  `/precios/canasta` y muestra precio de referencia si el producto
  esta en la CCV
- Esto es OPCIONAL — el proyecto Indice LCV funciona y tiene sentido
  sin esta integracion

---

## Lo que ya aprendimos (no perder)

Resumen de descubrimientos hechos en la investigacion inicial, para
que dentro de meses no se vuelvan a pisar las mismas piedras:

- **La Anonima publica precios en JSON-LD** dentro del HTML, en las
  paginas de categoria (no en su buscador, que esta roto). Los codigos
  de categoria del sitio nuevo no siempre coinciden con los slugs de
  la URL — algunos numeros apuntan a categorias internamente distintas
  a lo que dice la URL. Conviene confirmarlos navegando el menu real.
- **Carrefour y Changomas usan VTEX** y exponen una API publica de
  catalogo: `/api/catalog_system/pub/products/search/<ruta>`. Devuelve
  JSON con todo incluyendo el "precio de lista" (precio sin
  descuento), util para detectar ofertas reales sin necesidad de
  historial.
- **Productos sin stock** tienen precios viejos pegados que no se
  actualizan. Hay que filtrar por `IsAvailable` y
  `AvailableQuantity`, no solo por precio mayor a cero.
- **Los nombres no coinciden entre supers.** Para matchear el mismo
  producto entre tiendas hay que armar una clave por
  marca + tipo + tamano, no por nombre exacto.
- **Combos y kits con productos de regalo confunden el matching.**
  Hay que excluirlos explicitamente con palabras como "kit",
  "cartuchera", "mochila", "combo escolar".

---

*Version: 1.0 — Junio 2026*
*Puerto Madryn, Patagonia, Argentina*
