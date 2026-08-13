# Guía: usar Claude Code con Froth (para principiantes)

> Objetivo: pasar de "todo por Cowork" a manejar el proyecto tú mismo desde la terminal con
> Claude Code, aprendiendo en el camino. Pasos concretos, sin dar nada por sabido.

---

## 1. ¿Qué es Claude Code y en qué se diferencia de Cowork?

Los dos son **el mismo Claude (yo)**, pero con distinta "carrocería":

- **Cowork** (donde estás ahora): ventana de chat amigable, pensada para tareas de archivos y
  automatización. Cómoda, pero tú no ves "la maquinaria".
- **Claude Code**: yo viviendo **dentro de tu terminal**, en la carpeta de tu proyecto. Veo tus
  archivos, ejecuto comandos, escribo y corro código contigo, y tú apruebas cada paso. Es la
  herramienta correcta para un proyecto de programación como Froth.

Lo bonito: **tu proyecto ya está listo para Claude Code**. El archivo `CLAUDE.md` que creamos es
justo el archivo de memoria que Claude Code lee **automáticamente** al abrir la carpeta. Toda la
columna vertebral, el topic y las decisiones ya están ahí.

---

## 2. Qué necesitas antes de instalar

1. **Cuenta de pago de Claude** (Pro, Max, Team o Enterprise). La gratuita NO da acceso a Claude
   Code. *(Si ya usas Cowork en la app de escritorio, probablemente ya tienes plan de pago.)*
2. **Git para Windows** (recomendado): https://git-scm.com/downloads/win
   Sirve para que Claude Code ejecute comandos con Git Bash y para versionar tu proyecto.
3. **Python** ya instalado (lo usaremos para correr Froth).

---

## 3. Instalar Claude Code en Windows (paso a paso)

1. Abre **PowerShell** (no CMD, no Git Bash). Truco: el prompt de PowerShell empieza con `PS C:\`.
   - Menú inicio → escribe "PowerShell" → Enter.
2. Pega este comando y Enter:
   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```
3. **Cierra esa ventana de PowerShell y abre una NUEVA.** (El instalador cambia el PATH y eso solo
   aplica a terminales nuevas - si no, el comando `claude` "no se encuentra".)
4. Comprueba que quedó bien:
   ```powershell
   claude --version
   claude doctor
   ```
   `claude doctor` es un chequeo de salud: te dice si algo falta.

> ¿Prefieres algo más visual? Existe la **extensión de Claude Code para VS Code** y la app de
> escritorio. Para aprender de verdad, recomiendo la terminal primero - pero VS Code es una
> alternativa cómoda cuando ya le tomes confianza.

---

## 4. Tu primera sesión de Claude Code con Froth

1. Abre PowerShell y **entra a la carpeta del proyecto** (la que contiene `app.py`):
   ```powershell
   cd "<la carpeta donde tienes Froth>"
   ```
   (`cd` = "change directory", cambiar de carpeta.) Truco: en el Explorador, botón derecho
   sobre la carpeta → "Copiar como ruta de acceso", y la pegas entre las comillas.
2. Arranca Claude Code:
   ```powershell
   claude
   ```
   La primera vez te pedirá iniciar sesión: se abre el navegador, apruebas, y listo.
3. Verás un prompt donde le escribes en lenguaje natural. Lo primero, para que "lea" el proyecto:
   > Lee CLAUDE.md y dime en qué fase estamos y cuál es el siguiente paso.

   Como `CLAUDE.md` se carga solo, ya sabrá del topic, las fases y las decisiones.

---

## 5. Cómo se trabaja (el ciclo básico)

Claude Code funciona pidiéndote **permiso antes de actuar**. El ciclo es:

1. Tú describes lo que quieres en español.
2. Yo propongo (ver un archivo, correr un comando, editar código).
3. **Tú apruebas o rechazas.** Nada se ejecuta sin tu OK.

Cosas útiles que puedes escribir o teclear:
- **Plan mode**: pídeme "hazme un plan antes de tocar nada" para que primero razone y tú apruebes.
- `/clear` - limpia la conversación cuando cambies de tema (mantiene el contexto liviano).
- `/init` - regenera/mejora el CLAUDE.md (ya lo tenemos, no hace falta ahora).
- Escribir `claude` y luego tu petición; para salir, `Ctrl + C` dos veces o escribe `/exit`.

---

## 6. Primer objetivo real (Fase 1): bajar papers desde TU máquina

En Cowork no pude bajar papers (mi entorno tiene la red bloqueada). En tu máquina sí se puede.
En tu primera sesión de Claude Code, pídeme literalmente esto, paso por paso:

1. > Crea un entorno virtual de Python en esta carpeta y instala lo de requirements.txt, explicándome cada comando.
2. > Ahora corre `python -m froth.pull` y muéstrame los primeros papers que bajó.
3. > Abre data/processed/papers.parquet y enséñame la tabla (título, año, citas, abstract).

Si algo falla (típico en la primera vez: falta una librería, o el nombre de un término), me lo
pegas y lo arreglamos juntos. Ese "arreglar juntos" es donde más se aprende.

---

## 7. Reglas para que no te pierdas

- **Una cosa a la vez.** No me pidas "hazlo todo"; vamos fase por fase, aprobando cada paso.
- **Pregunta "¿por qué?".** Si no entiendes un comando, pídeme que lo explique antes de aprobar.
- **La memoria es sagrada.** Cuando decidamos algo, pídeme que lo anote en `memory/decisions_log.md`
  y lo que aprendiste en `memory/learning_log.md`. Así la próxima sesión arranca sabiendo todo.
- **Cowork y Claude Code comparten la misma carpeta.** Puedes seguir usando Cowork para cosas
  visuales y Claude Code para programar; ven los mismos archivos.

---

### Fuentes (instalación, verificadas hoy)
- [Claude Code - Advanced setup (docs oficiales)](https://code.claude.com/docs/en/setup)
- [Claude Code - Quickstart](https://code.claude.com/docs/en/quickstart)
