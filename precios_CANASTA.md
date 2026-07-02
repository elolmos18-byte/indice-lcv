# INDICE LCV — CANASTA v2.2

> Definicion de la Canasta Comunidad del Viento (CCV-37): que
> productos se miden cada corrida, con que criterio se elige uno
> entre varios candidatos, y que precio se usa para compararlos.

Este documento es independiente de `precios_MAESTRO.md`. El MAESTRO
define el proyecto Indice LCV en general; este define la metodologia
de seleccion de productos y el criterio de precio. La lista concreta
de rubros (claves de busqueda, exclusiones, categorias permitidas,
tamano de referencia) vive en `precios_canasta_rubros.json` — ver
"Donde esta la definicion real de cada rubro" mas abajo. Este
archivo no duplica esa lista para evitar que las dos queden
desincronizadas.

**El nombre "CCV-37" quedo como nombre del proyecto por motivos
historicos** (asi arranco en Junio 2026), aunque la canasta ya tiene
mas rubros que 37 — el numero no se actualiza cada vez que se suma
un rubro nuevo, ver `precios_canasta_rubros.json` para el conteo
real vigente.

---

## Metodologia de seleccion (v2.0 — reemplaza la v1.0)

### Por que se cambio la v1.0

La version original de este documento (Junio 2026) definia una
canasta de **marca fija**: un solo producto puntual por rubro, que
debia existir en los tres supers, y que se mantenia igual semana a
semana salvo que se discontinuara.

En la practica, ese criterio dejaba la mayoria de los rubros vacios
— muy pocas marcas puntuales estan presentes en los tres catalogos a
la vez (La Anonima, Carrefour y Changomas tienen surtidos distintos,
con sus propias segundas marcas y proveedores locales). El codigo
(`precios_buscar_canasta.py`) paso a implementar otra logica, pero
este documento nunca se actualizo para reflejarlo — quedo
describiendo una metodologia que ya no corria. Esta version corrige
eso.

### Que hace el sistema hoy

**Para cada rubro, en cada super, se busca el producto mas barato
que matchee la definicion del rubro — de forma independiente en
cada uno.** La marca no tiene que coincidir entre supers, y puede
cambiar de una corrida a otra si aparece una opcion mas barata.

Esto significa que el Indice LCV no compara "la misma marca en tres
lugares", sino "cuanto cuesta resolver esta necesidad puntual (1kg
de harina 000, una docena de huevos, etc.) comprando lo mas barato
disponible en cada super". Es una diferencia de fondo con la v1.0, y
es intencional: asi la canasta se puede mantener completa en los
tres supers en vez de ir perdiendo rubros por falta de una marca
compartida.

### Precio de lista, sin descuentos ni promociones

**El precio que se registra es el precio de lista/gondola, nunca un
precio con descuento, promocion, cupon o beneficio de tarjeta.**

El Indice LCV mide la variacion de precios reales de una canasta de
referencia — no las estrategias comerciales puntuales de cada
cadena (dia del descuento, 2x1, reintegro con banco X). Si se
mezclaran precios promocionales, el indice terminaria midiendo que
super tuvo mejor campaña de marketing esa semana, no que super tiene
el precio mas bajo real. El precio con descuento es un beneficio
condicional (dia, medio de pago, tope de reintegro); el precio de
lista es el que cualquier persona paga sin condiciones.

En la practica, esto se resuelve distinto segun el origen del dato:

- **Carrefour y Changomas (VTEX):** la API expone ademas del precio
  mostrado un campo de precio de lista sin promociones
  (`precio_lista` en `catalogo_vtex.csv`). Cuando ese campo esta
  disponible, se usa en vez del precio con descuento.
- **La Anonima:** el listado de categoria del sitio a veces expone
  un precio promocional en vez del precio de lista real. Como
  visitar la pagina individual de cada producto del catalogo entero
  seria muy pesado, el compromiso es visitar solo la pagina del
  producto que ya gano como "mas barato" en su rubro, y confirmar/
  corregir su precio ahi antes de guardar el resultado final (ver
  `corregir_precio_lista_anonima()` en `precios_buscar_canasta.py`).

### El reemplazo del control de calidad: categorias_permitidas

La v1.0 tenia un control de calidad implicito: si una marca no
estaba en los tres supers, ese rubro quedaba "sin canasta" — no se
mostraba un dato dudoso. Al pasar a Camino B (cada super busca su
propio mas barato, sin cruce), ese control desaparecio. Sin el, un
rubro con palabras clave demasiado generales puede matchear un
producto de otra categoria por completo: "picada" matcheando
"Cebolla picada" en vez de carne picada, o "asado" matcheando una
mayonesa con sabor a asado en vez de un corte de carne.

El control de calidad que reemplaza al cruce de marca es el campo
**`categorias_permitidas`** en `precios_canasta_rubros.json`: ademas
de las palabras clave, el producto tiene que pertenecer a una de las
categorias de catalogo permitidas para ese rubro (por ejemplo,
`"carniceria"` para los cortes de carne, o `"verduras"` /
`"frutas"` para la verduleria). Este campo es obligatorio para
cualquier rubro cuyas palabras clave puedan aparecer en productos de
categorias no relacionadas (condimentos con sabor a X, verduras
picadas, etc.) — no es opcional "para prolijidad", es lo que
reemplaza al control que se perdio al abandonar la marca fija.

### Rubros fusionados y variantes de escritura

Algunos cortes de carne no tienen presencia pareja en los tres
catalogos — un super vende "Carnaza" y "Paleta" como productos
separados, y otro solo tiene un unico corte que es a la vez las dos
cosas (ej. "Carnaza de Paleta Fraccionada..."). Exigir que ambos
conceptos existan por separado en los tres supers, como se hacia con
rubros normales, dejaria ese super afuera del rubro para siempre —
no por un error de busqueda, sino porque su catalogo genuinamente no
distingue el corte de esa forma.

Para estos casos existe el **rubro fusionado**: un rubro que se
define con dos (o mas) grupos de palabras clave en vez de uno solo,
y matchea un producto si **cualquiera** de los grupos esta presente
en el nombre — no hace falta que esten todos juntos, a diferencia de
la logica normal de `claves` (donde todas las palabras tienen que
aparecer).

**Un rubro fusionado no promedia ni combina precios de conceptos
distintos.** En cada super se elige el mas barato entre todos los
productos que matchean cualquiera de los grupos — puede ser una
"Carnaza" en un super y una "Paleta" en otro. La ganancia de
transparencia esta en que la pagina publica siempre muestra el
nombre exacto y el link al producto elegido (ver `MAPA.md` — el link
"Ver producto →"): quien mire la tabla ve exactamente que compro
cada super para ese rubro y puede decidir si le sirve como
referencia, en vez de que el indice le oculte la diferencia detras
de un nombre generico.

**El mismo mecanismo (`claves_alternativas`) tambien se usa para
variantes de escritura de un mismo producto**, cuando los tres
catalogos no coinciden en como lo escriben. Caso real: "Fideos
spaguetti" solo tenia como clave la forma "spaguetti" (con gu, la
forma mas comun en los catalogos de Carrefour y Changomas), pero la
mayoria del catalogo de La Anonima escribe "spaghetti" (con gh, a la
italiana) — con una sola clave, La Anonima quedaba con un unico
producto candidato en todo su catalogo, y si ese se daba de baja el
rubro quedaba sin dato pese a tener mas de una decena de spaghettis
distintos en gondola. La solucion es la misma logica O entre grupos:
`[["spaguetti"], ["spaghetti"]]`. La diferencia con el caso de
Carnaza/Paleta es solo el motivo (ortografia en vez de catalogo que
no distingue dos cortes) — el mecanismo y la garantia de
transparencia via el link al producto son los mismos.

Se usa este mecanismo cuando:
- Dos conceptos (cortes, o formas de escribir el mismo producto) son
  razonablemente equivalentes como referencia de gasto o son
  literalmente el mismo producto
- No es posible cubrir los tres supers con una sola lista de
  palabras clave sin dejar sistematicamente afuera a alguno

No es un mecanismo para "rellenar" rubros que simplemente no
encuentran match — para eso existe la regla de rubro incompleto (ver
mas abajo), que es la respuesta correcta cuando un super no vende
algo en absoluto.

### Rubros incompletos

Si un super no tiene ningun producto que matchee un rubro (clave +
exclusiones + categoria permitida), ese rubro queda con el dato de
ese super vacio — no se inventa ni se aproxima. El total de la
canasta de ese super solo suma los rubros donde estan los tres
supers completos, para que la comparacion de totales sea siempre
sobre la misma canasta (ver `_costo_referencia()` y el uso de
`rubro_completo` en `precios_buscar_canasta.py`).

### Unidad de comparacion estandar

Cada rubro define una unidad estandar (`kg`, `L`, `unidad`, `m`,
`panos`) para poder comparar presentaciones de tamano distinto entre
supers de forma honesta. El **precio de gondola** (`precio_envase`)
es el que efectivamente se paga por ese envase puntual; el **precio
normalizado** (`precio_normalizado`) es el que se usa para decidir
cual super es mas barato y para calcular el total de la canasta.

Ejemplo: si un super vende un producto de 500g a $800 y otro vende
el mismo tipo de producto en 1kg a $1200, comparar $800 contra
$1200 directo es enganoso — normalizado es $1600/kg contra
$1200/kg, y el segundo es el mas barato aunque su precio de gondola
sea mayor.

---

## Donde esta la definicion real de cada rubro

La lista completa de rubros — nombre, grupo, palabras clave,
exclusiones, categorias permitidas cuando aplica, tamano de
referencia y unidad — vive en **`precios_canasta_rubros.json`**. Ese
archivo es la unica fuente de verdad operativa; este documento no lo
duplica para que no puedan quedar desincronizados (que es
exactamente lo que le paso a la tabla de la v1.0 de este mismo
archivo).

Cualquier cambio a un rubro (agregar una palabra a `excluir`, sumar
`categorias_permitidas`, agregar un rubro nuevo) se hace directo en
ese `.json`, y se anota en el changelog de mas abajo con fecha y
motivo — igual que antes.

---

## Changelog de la canasta

Cada vez que se modifica la composicion o la logica de la canasta,
se anota aca con fecha y motivo. Sin excepciones — el changelog es
lo que mantiene la integridad de la serie historica del Indice LCV.

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-06-23 | Creacion de la canasta CCV-37 v1.0 | Definicion inicial del proyecto (marca fija, misma marca en los 3 supers) |
| 2026-07-01 | Reescritura v2.0: se documenta Camino B (mas barato por super, sin marca fija) y precio de lista sin descuentos/promociones | La v1.0 describia una metodologia que el codigo ya no implementaba. Se corrige el documento para reflejar el criterio real vigente, y se deja de duplicar la lista de rubros (ahora unica fuente: `precios_canasta_rubros.json`) |
| 2026-07-01 | v2.1: se agrega `categorias_permitidas` a los rubros de Carniceria (Carne picada, Asado, Pollo, Nalga, Carnaza/Paleta) y se documenta el mecanismo de "rubro fusionado" | Se detectaron matches de otra categoria (cebolla picada, mayonesa sabor asado) por falta de restriccion de categoria en Carniceria. Carnaza y Paleta se fusionan en un solo rubro porque La Anonima no distingue esos dos cortes en su catalogo — ver seccion "Rubros fusionados" |
| 2026-07-01 | v2.2: se extiende `claves_alternativas` a "Fideos spaguetti" para cubrir la variante "spaghetti" (con gh) | La Anonima escribe la mayoria de sus fideos largos como "Spaghetti", no "Spaguetti" — con una sola clave, el rubro dependia de un unico producto candidato en su catalogo. De paso se corrigio que Changomas no traia su opcion mas barata por el mismo motivo de ortografia |

---

*Version: 2.2 — Julio 2026*
