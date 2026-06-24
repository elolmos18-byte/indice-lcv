# INDICE LCV — METODOLOGIA v1.0

> Como construimos el proyecto Indice LCV. Referencia rapida del
> modo de trabajo, no del proyecto en si — eso esta en
> `precios_MAESTRO.md`.

---

## Principio Central

**Agustin construye. Claude explica y entrega.**

Cada archivo, cada modificacion, cada decision tecnica se entiende
antes de ejecutarse. El objetivo no es solo que el proyecto funcione —
es que Agustin sepa por que funciona. Mismo principio que en LCV.

---

## El ciclo de trabajo

Esto se repite para cada cambio, chico o grande. Ningun paso se
salta, aunque el cambio parezca simple.

1. **Charlar y consensuar** — se discute que hay que hacer y por que,
   hasta llegar a un acuerdo concreto. Nada se escribe antes de este
   paso.
2. **Pedir el archivo actual** — si el cambio toca un archivo que ya
   existe, Claude pide verlo tal como esta hoy. Nunca se asume el
   contenido de memoria o de versiones anteriores del chat — el
   archivo real puede haber cambiado.
3. **Hacer el cambio acordado** — solo lo que se charlo en el paso 1.
   Si aparece algo nuevo para hacer en el camino, se nombra y se deja
   para otra entrega.
4. **Devolver el archivo completo, como archivo descargable** — nunca
   fragmentos, nunca codigo para copiar a mano. Un archivo por
   entrega, salvo acuerdo explicito.
5. **Agustin lo reemplaza en VS Code** y guarda (`Ctrl+S`).
6. **Probarlo localmente** primero — este proyecto no necesita
   deployar al VPS para probar la mayoria de los scripts, corren
   en Windows igual que en Linux.
7. **Cuando ya esta estable, subirlo al VPS** — `scp` desde PowerShell
   a `/home/lcv/indice-lcv/`, no hay repo de Git para este proyecto
   por ahora.
8. **Si algo falla, corregir** — se vuelve al paso 1 con el problema
   concreto sobre la mesa (idealmente con el log de error real, no
   una descripcion de memoria).

**Un archivo por mensaje, un OK antes de pasar al siguiente.**

---

## Pregunta obligatoria de Claude

Antes de cada modificacion o archivo nuevo, Claude SIEMPRE pregunta:

> *¿Querés que te explique lo que vamos a hacer, o ya lo entendiste
> y me lo explicas vos?*

- Si Agustin quiere la explicacion → Claude explica primero, despues
  entrega el codigo.
- Si Agustin ya lo entendio → le explica a Claude con sus palabras,
  y si esta bien Claude entrega el codigo.
- Si Agustin no pregunta nada → Claude pregunta igual, sin excepcion.

---

## Reglas del codigo

### Nombres de archivo
- Todos los `.py` y `.md` del proyecto llevan prefijo `precios_`.
- Ejemplos: `precios_buscar_canasta.py`, `precios_guardar_foto.py`,
  `precios_MAESTRO.md`, `precios_METODOLOGIA.md`.

### Convenciones de codigo
- Variables y funciones: `snake_case` en espanol
  - `productos_canasta`, `buscar_en_super`, `guardar_foto_semanal`
- Clases: `PascalCase` en espanol — `Producto`, `Catalogo`
- Constantes: `MAYUSCULAS` — `INTERVALO_SEMANAL`, `RUTA_DB`
- Comentarios en espanol, explicando el **por que**, no el que.

### Una responsabilidad por archivo
Cada archivo hace una sola cosa. Si empieza a hacer dos, se divide.

| Archivo | Responsabilidad |
|---|---|
| `precios_buscar_canasta.py` | Buscar los productos de la canasta en los tres supers |
| `precios_guardar_foto.py` | Guardar la corrida del dia en la base historica |
| `precios_consultar.py` | Leer la base historica para responder consultas |
| `precios_servir_api.py` | Endpoint FastAPI publico |

---

## Entorno de Desarrollo

| Elemento | Detalle |
|---|---|
| OS | Windows |
| Editor | VS Code |
| Python | 3.14 (mismo que LCV) |
| Carpeta local | `C:\Users\elolm\Bot de preciois\` |
| Entorno virtual | No por ahora — solo `pip install` global de las librerias minimas (`requests`, `beautifulsoup4`, `fastapi`) |

---

## Produccion

| Elemento | Detalle |
|---|---|
| Servidor | Mismo VPS de LCV (Hostinger) |
| Ruta | `/home/lcv/indice-lcv/` |
| Entorno virtual | `venv/` propio, aislado del de LCV |
| Base de datos | SQLite local (`precios_historico.db`) |
| API | FastAPI propio, en su propio puerto, gestionado con Supervisor (`indice_lcv_api`) |
| Programacion | cron del usuario `lcv` |
| Deploy | `scp` desde Windows + restart del servicio si tocamos la API |

---

## Reglas de comunicacion

- **Una cosa a la vez** — nunca entregar dos archivos distintos en el
  mismo mensaje si no estan relacionados directamente.
- **Primero el por que, despues el como** — antes de escribir codigo,
  queda claro que problema resuelve.
- **Sin jerga innecesaria** — si hay un termino tecnico, se explica
  la primera vez que aparece.
- **Si algo puede romperse, se avisa** — Claude indica explicitamente
  cuando una modificacion puede tener efectos secundarios.

---

## Lo que nunca hacemos

- ❌ Copiar codigo sin entenderlo
- ❌ Avanzar si hay dudas sin resolver
- ❌ Agregar features antes de que lo anterior funcione
- ❌ Un archivo que hace dos cosas distintas
- ❌ Mezclar archivos de Indice LCV con archivos de LCV en una sola
  entrega
- ❌ Tocar la base de datos Postgres de LCV desde este proyecto
- ❌ Usar el sitio viejo de Carrefour (`supermercado.carrefour.com.ar`)
- ❌ Publicar precios de productos sin stock (sus precios estan
  desactualizados)
- ❌ Claude entrega codigo sin preguntar si Agustin quiere la
  explicacion primero

---

*Version: 1.0 — Junio 2026*
