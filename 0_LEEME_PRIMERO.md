# 🗺️ Guía de carpetas - empieza por aquí

> ### 👀 ¿Por qué esta carpeta se ve casi vacía?
>
> Porque se ordenó a propósito (29 de agosto de 2026). Al abrirla ves **dos cosas**:
> **`Abrir Froth`**, que es el clic que arranca el programa, y **`Mis cosas`**, con atajos
> a tus apuntes, datos, resultados y notebooks.
>
> **No se borró ni se movió nada.** Los otros 34 elementos siguen exactamente donde
> estaban: solo están marcados como ocultos, que es una etiqueta de Windows que le dice al
> Explorador que no los dibuje. Para verlos otra vez tienes dos caminos:
>
> - **Rápido y temporal**: en el Explorador, pestaña **Ver → Mostrar → Elementos ocultos**.
> - **Definitivo**: `powershell -ExecutionPolicy Bypass -File packaging	idy_folder.ps1 -Revert`
>
> Y si algún día vuelve a verse desordenada, el mismo script sin `-Revert` la ordena otra
> vez. Pasa cuando git reescribe archivos: al hacerlo les quita la etiqueta de oculto.

¿No sabes en qué carpeta entrar? Esta es la chuleta. Regla simple:

> **Las carpetas con número (1 a 5) son TUYAS: entra tranquilo.**
> **Las carpetas sin número son la maquinaria: NO las toques.**

---

## 📖 TUYAS - entra a leer y mirar

| Carpeta | Qué hay dentro | ¿Qué haces aquí? |
|---------|----------------|------------------|
| **`1_Apuntes`** | Tus PDF de aprendizaje (00, 01, 02...) | **Leer**, en orden. Es tu libro de texto. Empieza por `LEEME.md`. |
| **`2_Datos`** | Los papers descargados (tabla `papers.parquet`) | Mirar, si tienes curiosidad. Se llena solo al correr el pipeline. |
| **`3_Resultados`** | Los mapas y reviews que produce Froth | **Mirar/abrir** tus resultados finales. (Vacío por ahora.) |
| **`4_Notebooks`** | Cuadernos de experimentos (Jupyter) | Aquí trastearás más adelante. (Vacío por ahora.) |
| **`5_Bitacoras`** | Diario de decisiones y de lo que aprendiste | Leer para recordar por qué hicimos algo. |

## ⚙️ MAQUINARIA - no entrar (déjalas trabajar)

| Carpeta | Qué es | Por qué no tocarla |
|---------|--------|--------------------|
| **`froth`** | El **código** del programa (el motor) | Son las "recetas" en Python. Las editarás cuando aprendas a programar, no antes. |
| **`.venv`** | La burbuja con Python y sus librerías | Se rompe si la mueves. Es interna. |
| **`tools`** | El compilador que convierte los apuntes en PDF | Herramienta interna. |
| **`models`** | Tu modelo entrenado (specter-mineral) | Se regenera con `froth.train`. Pesa ~440 MB. |
| **`packaging`** | El constructor del zip portable (entregable B) | Script interno. |
| **`dist`** | El zip portable ya construido | Producto final, no fuente. |
| **`docs`** | Guías públicas (keys, Ollama) + archivo de vistas retiradas | Leer sí; son parte del repo público. |
| **`assets`** | Logo e icono de la marca | Solo imágenes. |

## 📄 Archivos sueltos importantes (en la raíz)

- **`CLAUDE.md`** - la memoria del proyecto (estado, reglas, siguiente paso).
- **`Plan_Proyecto_Froth_ML.md`** - el plan maestro con las fases.
- **`LICENSE`** - licencia MIT (el repo es open source).
- **`Froth App.bat`** - doble clic = la app en su propia ventana (con splash).
- **`Froth.bat`** - doble clic = la app en el navegador.
- **`.openalex_key`** y **`.froth_keys`** - tus claves secretas. Jamás se suben.

---

**En resumen:** si dudas, mira el número. Con número → tuya. Sin número → del programa.
