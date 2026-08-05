# 📚 Apuntes Froth — tu libro de texto (léelos en orden)

Cada apunte nace de algo que apareció de verdad en el proyecto — no es teoría suelta.

## Dos formas de leerlo

- **El libro completo** (recomendado): `Froth_Apuntes_completos_ES.pdf` — los 46 apuntes en
  un solo PDF de 93 páginas, con índice y **marcadores** (abre el panel de marcadores de tu
  lector: se despliega apunte por apunte y por dentro de cada uno).
  En inglés: `Froth_Study_Notes_EN.pdf` (94 págs).
- **Sueltos**: carpeta `1. Apuntes acumulados/`, un PDF por apunte, numerados.

| # | Apunte | Fase | De qué trata |
|---|--------|------|--------------|
| 00 | El mapa del proyecto | — | Qué es Froth, las carpetas y las 7 fases. **Empieza aquí.** |
| 01 | Python y el entorno virtual | 0 | Qué es Python, el `.venv`, las librerías, `requirements.txt` |
| 02 | APIs y JSON | 1 | Cómo se piden datos a un servidor (OpenAlex) |
| 03 | Internet, SSL y API keys | 1 | El error de certificados, los códigos 4xx/5xx, la clave secreta |
| 04 | Tablas: pandas y parquet | 1 | El DataFrame de 126 papers y por qué se guarda en parquet |
| 05 | Qué es un embedding | 2 | El "mapa del significado": texto → vector; qué es SPECTER |
| 06 | Cargar SPECTER y tu primer vector | 2 | Usar (no construir) un modelo; el primer abstract vuelto números |
| 07 | La matriz de vectores | 2 | Vectorizar los 126 de golpe (batch) y guardarlos en `.npy` |
| 08 | Similitud coseno | 2 | Medir parecido por el ángulo entre vectores (0 a 1) |
| 09 | El buscador semántico | 2 | Frase → papers parecidos por significado. El "wow". |
| 10 | Cuadernos Jupyter | 2 | Qué es un notebook y tu buscador interactivo para validar |
| 11 | Tu primera web app (Streamlit) | 2 | La página web en tu PC: buscador en el navegador |
| 12 | Reducción de dimensiones | 3 | PCA (sombras) vs UMAP (vecindarios); en qué mienten los mapas 2D |
| 13 | UMAP en acción | 3 | El primer mapa real: coseno, semilla fija y cómo leer las nubes |
| 14 | Clustering: HDBSCAN | 3 | Grupos por densidad, ruido, y el cluster "cuarentena" |
| 15 | Etiquetas: c-TF-IDF | 3 | Nombrar burbujas con palabras características; tus 3 subtemas |
| 16 | El bubble map interactivo | 3 | Plotly, una figura dos caras, y el truco del slider en vivo |
| 17 | El filtro de relevancia | 3 | El sistema se limpia solo: coseno vs TOPIC, umbral por datos |
| 18 | Git y GitHub | 0 | Puntos de guardado, .gitignore, push y tu repo en la nube |
| 19 | Grafos: hubs y puentes | 4 | Nodos/aristas; hubs fundamentan, puentes aportan — tu tesis es un puente |
| 20 | La red de similitud | 4 | kNN + umbral (perillas probadas); Beauvoir resultó ser puente |
| 21 | El mapa mental de temas | 4 | Agregación a nivel tema; similitud vs citas — los silos (tu gap) |
| 22 | Vistas de red y packing | 4 | Red con física (resortes) y circle packing; qué significa la posición |
| 23 | DOI y open access | 4 | Enlaces a la lectura (DOI + PDF gratis); enlazar sí, descargar en masa no |
| 24 | Qué es un gap | 5 | Los 4 tipos medibles (silos, zonas ralas, puentes escasos, dormidos); mina vs desierto |
| 25 | Gaps y review draft | 5 | find_gaps() con tus resultados + el andamio con citas trazables (sin LLM) |
| 26 | Mean pooling (modo Tarea) | 5 | Los modelos truncan a 512 tokens; trocear y promediar lo esquiva |
| 27 | Granularidad con DBCV | 5 | El botón "recomendado" con estadística real, recalculado por corpus |
| 28 | Conectores multi-fuente | 5 | Crossref/S2/Scopus + dedup por DOI; keys tuyas y locales |
| 29 | Motor multi-topic | 6 | Generalizar ≠ entrenar; set_topic + términos derivados; hito 1→2 |
| 30 | El nacimiento de specter-mineral | 6 | Fine-tuning, MNRL sin etiquetas, loss/épocas — 83s en tu GPU |
| 31 | El veredicto del fine-tuning | 6 | 14/22, especialización núcleo/periferia y tu test doble ciego |
| 32 | h-index por cluster | 6 | Must-reads sin números mágicos; fallback head/tail breaks |
| 33 | Resortes calibrados y papers frontera | 6 | length=f(similitud); por qué había "amarillos junto al hub azul" |
| 34 | Resumen extractivo vs abstractivo | 7 | Seleccionar frases reales vs generar texto; por qué no puede alucinar |
| 35 | La frase centroide | 7 | El filtro de relevancia al revés; definiciones de libro a 0.94 |
| 36 | TextRank | 7 | PageRank sobre frases; típico (centroide) vs respaldado (consenso) |
| 37 | MMR | 7 | Anti-redundancia con λ elegido por tus datos (y un objetivo degenerado) |
| 38 | Borda y el draft v2 | 7 | Mezclar jueces por ranking; citas [n] + BibTeX por construcción |
| 39 | El LLM pulidor verificado | 7 | Ollama local pule, una puerta de citas decide; pulir ≠ generar |
| 40 | Títulos de cluster con KeyBERT | 7 | Keyphrases cortas con sentido; score contrastivo cluster−global |
| 41 | El veredicto del re-fine-tune | 6 | 3× datos NO mejoró; curación del corpus > cantidad |
| 42 | Cuelgue vs crash: watchdogs | 7 | Cuando no se cae sino se congela; subprocesos y vigilantes |
| 43 | La puerta de relevancia | 1 | Separar grano de paja en 190.000 papers; umbral en el hueco real |
| 44 | Tripletes de citación | 6 | Entrenar como SPECTER; hard negatives y el veredicto invertido |
| 45 | Zoom semántico y WebGL | 7 | 10.921 papers fluyen y 1.772 no; cortes por percentil de tu corpus |
| 46 | Arranque perezoso y caché | 7 | De 3,5 min a 30 s: importar tarde, y guardar en disco con la clave correcta |

## Cómo está organizado

- **`*.pdf`** (aquí) → lo que lees. Numerados = orden de lectura.
- **`src/`** → el código fuente LaTeX (`.tex`) de cada apunte. No necesitas tocarlo.
- **`src/preamble.tex`** → el estilo común (colores, cajas). Se comparte entre todos.

## Recompilar los PDF (si se edita un `.tex`)

Los apuntes sueltos:

```powershell
.venv\Scripts\python.exe 1_Apuntes\build.py
```

El libro completo, español y luego inglés:

```powershell
.venv\Scripts\python.exe 1_Apuntes\build_book.py
```

```powershell
.venv\Scripts\python.exe 1_Apuntes\build_book.py en
```

> Regla del proyecto: cada vez que aprendes un concepto o habilidad nueva, se crea un
> apunte nuevo con el siguiente número y se recompila. Así este libro crece contigo.
> Si añades un apunte, recuerda su gemelo en `src_en/` (mismo número, nombre en inglés):
> `build_book.py en` te avisa del porcentaje traducido si te falta alguno.
