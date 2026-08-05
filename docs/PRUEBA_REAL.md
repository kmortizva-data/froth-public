# La prueba real: de un título a preguntas que valen la pena

> **Qué es esto.** El recorrido completo de Froth sobre un corpus real, con los números que
> salieron de verdad el 2026-08-03. Ningún número aquí está supuesto: si dice 5.752 papers,
> es porque se contaron.
>
> **Corpus usado**: la tesis de máster que dio origen al proyecto, sobre flotación de micas
> de litio y recuperación de subproductos (Ta, Nb, Be) en el granito de Beauvoir, Francia.

---

## Paso 1 · Cosechar

En la pantalla de inicio, pega el título de tu tema en **"...or map a NEW topic"** y pulsa
**Harvest & map it**.

**Lo que salió:**

| | |
|---|---|
| Papers cosechados | **8.026** |
| Se quedaron en el mapa | **5.752** |
| Subtemas | **135** |
| Papers sueltos (sin subtema) | 1.740 |

Tarda unos 7 minutos, casi todo bajando papers de las cuatro fuentes. El mapa en sí es
cosa de un minuto.

### ¿Se quedó con lo que importa?

Esta es la pregunta que decide si el resto sirve, y se responde mirando las palabras del
propio título:

| Palabra | Cosechados | Conservados |
|---|---|---|
| lepidolite | 202 | **96%** |
| collector | 913 | **88%** |
| beryllium | 103 | 84% |
| flotation | 2.752 | 78% |
| froth | 947 | 77% |
| mica | 3.025 | 77% |
| particle size | 731 | 76% |
| tantalum | 478 | 73% |

Se queda con el mineral **y** con el método. Que las dos mitades del título sobrevivan es
justo lo que costó conseguir: una versión anterior del filtro conservaba el 96% de la
lepidolita y solo el **6%** de la flotación.

---

## Paso 2 · Los mandos del panel izquierdo

Solo hay cuatro que toques, y uno que **no**.

**El deslizador de detalle** decide cuántos subtemas ves. Debajo tiene un botón
**"Use recommended (N)"**, y ese número no es un valor por defecto: se calcula midiendo cuál
agrupa mejor **este** corpus concreto. **Empieza siempre ahí.**

**Year range** recorta por años. Útil para preguntarte "¿qué ha cambiado desde 2020?".

**Hide noise** esconde los papers sueltos, los que no encajaron en ningún subtema. Déjalo
apagado al principio: ahí viven los papers puente, que suelen ser los interesantes.

**Size = citations** hace los puntos más grandes cuanto más citados. Déjalo encendido.

**El que NO debes tocar:** *Refresh app (clear cache)*. Solo sirve si cambió el código.

---

## Paso 3 · Qué subtemas marcar juntos

De 135 subtemas nunca vas a marcar más de tres o cuatro a la vez. **La regla: marca el
subtema de tu pregunta, más sus vecinos.** Y los vecinos no los eliges a ojo: cada nota de
subtema trae una sección **"Borders on"** con los tres más parecidos y su nota de parecido.

Tres combinaciones reales de este mapa:

### A · "¿Cómo separo lepidolita de la ganga?"

| Marca esto | Papers |
|---|---|
| **Flotation separation lepidolite** | 36 |
| Flotation separation bastnaesite (vecino, 0,65) | 21 |
| Clay particles (vecino, 0,64) | 22 |

**Por qué juntos:** la bastnaesita es un carbonato de tierras raras, y su problema de
flotación es el mismo que el tuyo: separar de una ganga con química de superficie parecida.
Las arcillas son el otro enemigo clásico. El mapa los puso al lado sin saber mineralogía.

### B · "¿Y el efecto del tamaño de partícula?"

Tu título dice *differently sized*, así que esta es media tesis.

| Marca esto | Papers |
|---|---|
| **Fine particle flotation** | 60 |
| Fine particle flotation (el otro, vecino 0,95) | 27 |
| Separation behavior particle (vecino, 0,91) | 13 |

Dos subtemas casi idénticos con parecido 0,95: el mapa está diciendo que esa literatura se
partió en dos por el algoritmo, no por el contenido. Marca los dos.

### C · "¿Qué se sabe de mi yacimiento?"

| Marca esto | Papers |
|---|---|
| **Beauvoir rare-metal granite** | 340 |
| Magmatic hydrothermal (vecino, 0,94) | 14 |
| Granites pegmatites (vecino, 0,92) | 9 |

---

## Paso 4 · Qué leer

Pestaña **Export** → botón **Build the vault**. Te genera **1.305 archivos de texto**: uno
por subtema, uno por cada paper que merece lectura, más un índice. Empieza por `_index.md`.

**No son 5.752 papers para leer.** De cada subtema se eligen los imprescindibles mirando la
distribución de citas **de ese subtema**, no un top-10 inventado:

| Subtema | Papers | Para leer |
|---|---|---|
| Flotation separation lepidolite | 36 | **11** |
| Fine particle flotation | 60 | **15** |
| Magmatic hydrothermal | 14 | **5** |

Los primeros de cada lista, para que veas que no es relleno:

- *Electrostatically Controlled Enrichment of Lepidolite via Flotation* — 62 citas
- *Recycling Lepidolite from Tantalum-Niobium Mine Tailings* — 52 citas
- *Role of Bubble Size in Flotation of Coarse and Fine Particles* — 332 citas
- *Flotation of Fine Particles: A Review* — 244 citas
- *The Beauvoir topaz-lepidolite albite granite (Massif Central)* — 268 citas

---

## Paso 5 · Subirlo a NotebookLM

Misma pestaña → botón **Build the pack**. Te da cuatro archivos:

| Archivo | Qué es |
|---|---|
| `sources.md` | Los papers curados con su resumen y su DOI |
| `open_access_links.txt` | Enlaces a los PDF gratuitos |
| `prompts.md` | Las preguntas ya escritas |
| `READ_ME_FIRST.md` | Los tres pasos |

**Los tres pasos:** abre notebooklm.google.com → nuevo cuaderno → arrastra `sources.md`.
Cuenta como **una sola fuente**, así que deja sitio para lo que quieras añadir.

**Qué esperar con los enlaces.** Muchos son de MDPI y, si los abre un programa, dan error
403. **No están rotos**: es protección anti-robots. En un navegador normal abren el PDF sin
problema.

**Por qué lo subes tú y no lo hace el programa:** Google prohíbe entrar a NotebookLM de
forma automática. El que se arriesga a que le cierren la cuenta eres tú, y son dos clics.

---

## Paso 6 · Qué preguntar, y con qué cargado

Aquí está lo que hace que esto valga más que subir 50 PDF sueltos. `prompts.md` trae nueve
preguntas construidas **con números que el mapa midió**. Las tres buenas:

> **Similitud 0,69 pero cero citas cruzadas entre "Pegmatites chinese" y "Pegmatite bodies".
> Esa similitud es más alta que el 100% de los pares de subtemas de este corpus. Dos
> literaturas que estudian casi lo mismo y no se citan ni una vez. ¿Qué explicaría ese
> silencio, y qué tendría que demostrar un paper que las uniera?**

Dos comunidades trabajando sobre pegmatitas sin leerse. Eso es un hueco citable.

> **"Granites pegmatites" ↔ "Pegmatite bodies": cero papers puente pese a una similitud de
> 0,58. ¿Cuáles de las fuentes están en esa frontera, y qué impide que haya más?**

> **1.233 de 5.752 papers son de 2024 o posterior. Compara lo que asume el trabajo reciente
> con lo que asumía el antiguo. ¿Qué cambió, y qué se quedó igual en silencio?**

La diferencia con preguntar "resúmeme esto" es que estas respuestas **se pueden comprobar
contra el corpus**, porque las preguntas ya traen los números.

---

## Lo que la herramienta hace mal, dicho claro

**Hay un subtema basura en el mapa.** Se llama *"Lived experiences"* y tiene 116 papers de
estudios de género. Entra porque el filtro usa los elementos del título (Ta, Nb, **Be**) como
pista, y "Be" también es una palabra corriente en inglés. Se aceptó a cambio de recuperar la
literatura de tantalio y niobio, que sin esa pista se perdía. Es un intercambio consciente,
no un descuido: **ignóralo y sigue**.

**El subtema más grande es de carbón**, 409 papers. No es un error: la flotación de carbón
es la literatura más rica que existe sobre partículas finas, y el propio mapa la pone al lado
de tus subtemas de finos. Es método prestado de otro campo, que es donde suelen estar los
huecos.

**Trabaja con resúmenes, no con el texto completo** de los papers. Lo que te da es un mapa y
una lista de lectura, no un sustituto de leer.
