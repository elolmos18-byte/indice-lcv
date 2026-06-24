# INDICE LCV — CANASTA v1.0

> Definicion de la Canasta Comunidad del Viento (CCV-37): que
> productos puntuales se miden cada semana, con que marca y tamano,
> y como se eligieron.

Este documento es independiente de `precios_MAESTRO.md`. El MAESTRO
define el proyecto Indice LCV en general; este define solo los 37
productos concretos que componen la canasta y los criterios usados
para elegirlos. Si la composicion de la canasta cambia (un producto
se discontinua, una marca desaparece de un super), se actualiza
este archivo con su changelog.

---

## Metodologia de seleccion

Para que el Indice LCV sea honesto y comparable entre supers y entre
semanas, todos los productos se eligen siguiendo estos siete
criterios:

### 1. Una marca y un tamano por rubro

Para cada uno de los 37 rubros de la CCV-37 se elige UN producto
especifico (no "leche" en general, sino "Leche entera La Serenisima
sachet 1L"). Ese producto se fija y queda igual semana a semana.
Asi, lo que mide el Indice LCV es la variacion de precios del MISMO
producto en el tiempo, no la variacion del rubro en general.

### 2. La marca debe existir en los tres supers

Si una marca esta presente solo en dos supers, no sirve - no podemos
comparar lo que un super no vende. La eleccion se hace cruzando los
tres catalogos y quedandose solo con marcas presentes en los tres.

### 3. Calidad pareja, no nos importa cual es "la mejor"

El objetivo no es opinar sobre que marca es superior. El objetivo es
comparar el precio del MISMO producto entre tres supers. Si la marca
elegida es de primera linea, ok. Si es segunda marca, tambien ok. Lo
que importa es que sea la misma en los tres.

### 4. Cuando hay varias marcas posibles, preferencia por las mas vendidas o conocidas

Razon practica: si la marca elegida desaparece de un super, queremos
que sea facil reemplazarla por otra equivalente. Las marcas chicas
tienen mas riesgo de discontinuarse de un momento al otro.

### 5. Si para un rubro no hay marca compartida entre los tres, ese rubro queda "sin canasta"

No inventamos comparaciones que no son validas. Si mas adelante
aparece una marca compatible, se suma con changelog. El Indice LCV
prefiere ser incompleto antes que mentiroso.

### 6. Si una marca elegida desaparece de uno de los supers, se reemplaza por la siguiente que tambien este en los tres

Y se anota la fecha del cambio en el changelog al final de este
archivo. No se mezclan precios de productos distintos en la misma
serie historica - eso destrozaria el Indice LCV.

### 7. Cada rubro tiene una unidad de comparacion estandar

Aunque la marca sea la misma, los tamanos no siempre coinciden entre
supers (un super puede tener sachet 1L y otro botella 900cc). Para
que la comparacion sea honesta, cada rubro define una unidad
estandar de comparacion: por kilo, por litro, o por unidad.

- El **precio real** (el de gondola) es el que se muestra en la
  pagina, porque es lo que la persona va a pagar.
- El **precio normalizado** (por kg / L / unidad) es el que se usa
  para decidir cual super es el mas barato del rubro.

Ejemplo: si Carrefour vende Yerba Cruz de Malta 500g a $4500 y
La Anonima vende la misma marca pero en 1kg a $8500, comparar
$4500 contra $8500 directo es enganoso - en realidad el primero
sale $9000/kg y el segundo $8500/kg, asi que La Anonima es 5%
mas barata aunque su precio absoluto sea casi el doble.

---

## Los 37 rubros de la CCV-37

Tabla por completar en Fase 1. Mientras "marca" y "tamano" esten en
blanco, ese rubro todavia no esta operativo. Una vez completos los
37, se genera `canasta.json` y arranca Fase 2.

### Pan, harinas y derivados (8 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 1 | Harina 000 | por kg | | |
| 2 | Harina leudante | por kg | | |
| 3 | Fideos largos (spaguetti) | por kg | | |
| 4 | Fideos cortos (mostachol) | por kg | | |
| 5 | Arroz | por kg | | |
| 6 | Polenta | por kg | | |
| 7 | Galletitas dulces | por kg | | |
| 8 | Galletitas saladas | por kg | | |

### Azucar y dulces (3 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 9 | Azucar | por kg | | |
| 10 | Dulce de leche | por kg | | |
| 11 | Mermelada | por kg | | |

### Aceites y grasas (3 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 12 | Aceite de girasol | por litro | | |
| 13 | Aceite de mezcla | por litro | | |
| 14 | Manteca | por kg | | |

### Lacteos (5 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 15 | Leche entera | por litro | | |
| 16 | Leche descremada | por litro | | |
| 17 | Yogur firme | por litro | | |
| 18 | Yogur bebible | por litro | | |
| 19 | Queso untable | por kg | | |

### Huevos (1 rubro)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 20 | Huevos | por unidad | | |

### Legumbres y conservas (5 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 21 | Arvejas en lata | por kg drenado | | |
| 22 | Lentejas | por kg | | |
| 23 | Atun en lata | por kg drenado | | |
| 24 | Salsa de tomate | por litro | | |
| 25 | Pure de tomate | por litro | | |

### Condimentos y aderezos (6 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 26 | Sal fina | por kg | | |
| 27 | Sal gruesa | por kg | | |
| 28 | Vinagre | por litro | | |
| 29 | Mayonesa | por kg | | |
| 30 | Ketchup | por kg | | |
| 31 | Mostaza | por kg | | |

### Infusiones (3 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 32 | Yerba | por kg | | |
| 33 | Cafe | por kg | | |
| 34 | Te | por unidad (saquito) | | |

### Bebidas no alcoholicas (3 rubros)

| # | Rubro | Unidad de comparacion | Marca | Tamano |
|---|---|---|---|---|
| 35 | Gaseosa cola | por litro | | |
| 36 | Agua mineral sin gas | por litro | | |
| 37 | Jugo en polvo | por unidad (sobre) | | |

---

## Changelog de la canasta

Cada vez que se modifica la composicion de la canasta (se reemplaza
una marca, se discontinua un producto, se ajusta un tamano), se
anota aca con fecha y motivo. Sin excepciones - el changelog es lo
que mantiene la integridad de la serie historica del Indice LCV.

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-06-23 | Creacion de la canasta CCV-37 v1.0 | Definicion inicial del proyecto |

---

*Version: 1.0 — Junio 2026*
