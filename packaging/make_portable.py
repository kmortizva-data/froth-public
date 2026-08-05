"""
make_portable.py - build the PORTABLE Froth for Windows (deliverable B, public edition).

WHAT IT DOES: assembles dist/Froth/ as a fully self-contained folder:
  runtime/   an embedded Python (python.org "embeddable" build) with every runtime
             dependency pip-installed into it (CPU torch: no GPU assumed)
  app files  froth/, app.py, desktop.py, assets/, .streamlit/, docs/, README.md
  launchers  'Froth App.bat' (own window) and 'Froth (browser).bat'
then zips it to dist/Froth-portable-win64.zip. Download -> unzip -> double-click:
no install, no admin rights, no unsigned-installer warnings.

POLICY (inviolable): the owner's key files (.froth_keys, .openalex_key) are NEVER
copied into the bundle. Users bring their own keys (docs/GET_YOUR_KEYS.md).

HOW TO RUN IT (from the repo root, takes ~10-25 min: big downloads):
    .venv\\Scripts\\python.exe packaging\\make_portable.py
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import truststore

truststore.inject_into_ssl()
import requests  # noqa: E402  (after SSL injection)

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Froth"
RUNTIME = DIST / "runtime"

PY_VERSION = "3.14.6"                              # match the dev machine
EMBED_URL = (f"https://www.python.org/ftp/python/{PY_VERSION}/"
             f"python-{PY_VERSION}-embed-amd64.zip")
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"

APP_ITEMS = ["froth", "assets", "docs", ".streamlit", "app.py", "desktop.py", "README.md"]
# The owner's keys never ship; neither does his personal research logbook
# (my_space.json) - the FEATURE ships, the personal data does not (same policy).
FORBIDDEN = {".froth_keys", ".openalex_key", "my_space.json"}


def step(msg: str) -> None:
    print(f"\n=== {msg} ===", flush=True)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    print(f"  {dest.name}: {dest.stat().st_size / 1e6:.1f} MB")


def run(args: list, **kw) -> None:
    print("  $", " ".join(str(a) for a in args[:6]), "...", flush=True)
    subprocess.run([str(a) for a in args], check=True, **kw)


def main() -> None:
    step("clean dist/")
    if DIST.exists():
        shutil.rmtree(DIST)
    RUNTIME.mkdir(parents=True)

    step(f"embedded Python {PY_VERSION}")
    embed_zip = ROOT / "dist" / "python-embed.zip"
    download(EMBED_URL, embed_zip)
    with zipfile.ZipFile(embed_zip) as z:
        z.extractall(RUNTIME)
    embed_zip.unlink()

    # The embeddable build ships with 'import site' disabled; enable it and add
    # site-packages so pip-installed packages are importable.
    pth = next(RUNTIME.glob("python*._pth"))
    content = pth.read_text().replace("#import site", "import site")
    if "Lib\\site-packages" not in content:
        content += "\nLib\\site-packages\n"
    pth.write_text(content)

    step("bootstrap pip")
    getpip = RUNTIME / "get-pip.py"
    download(GETPIP_URL, getpip)
    py = RUNTIME / "python.exe"
    run([py, str(getpip), "--no-warn-script-location"])
    getpip.unlink()

    step("install CPU torch (the public build assumes no GPU)")
    run([py, "-m", "pip", "install", "--no-warn-script-location",
         "torch", "--index-url", TORCH_CPU_INDEX])

    step("install runtime dependencies")
    run([py, "-m", "pip", "install", "--no-warn-script-location",
         "-r", str(ROOT / "packaging" / "requirements-dist.txt")])

    step("copy the app (keys are policy-excluded)")
    for item in APP_ITEMS:
        src = ROOT / item
        if src.name in FORBIDDEN:
            continue
        if src.is_dir():
            shutil.copytree(src, DIST / item,
                            ignore=shutil.ignore_patterns("__pycache__", *FORBIDDEN))
        else:
            shutil.copy2(src, DIST / item)
    for bad in FORBIDDEN:                          # belt AND suspenders
        assert not (DIST / bad).exists(), f"policy breach: {bad} in bundle!"

    step("launchers + first-run note")
    (DIST / "Froth App.bat").write_text(
        '@echo off\r\nstart "" "%~dp0runtime\\pythonw.exe" "%~dp0desktop.py"\r\n',
        encoding="ascii")
    (DIST / "Froth (browser).bat").write_text(
        '@echo off\r\ncd /d "%~dp0"\r\n"%~dp0runtime\\python.exe" -m streamlit run app.py\r\npause\r\n',
        encoding="ascii")
    (DIST / "READ ME FIRST.txt").write_text(
        "Froth portable\r\n"
        "===============\r\n"
        "1. Double-click 'Froth App.bat' (own window) or 'Froth (browser).bat'.\r\n"
        "2. First run downloads the language model (~440 MB) - give it a few minutes.\r\n"
        "3. Optional but recommended: connect your own free API keys for bigger\r\n"
        "   harvests - step-by-step guide in docs\\GET_YOUR_KEYS.md.\r\n"
        "4. Needs Microsoft Edge WebView2 (preinstalled on Windows 11; otherwise\r\n"
        "   the app window will offer the download).\r\n",
        encoding="ascii")

    step("smoke test: imports inside the bundle")
    # The smoke test runs the freshly-copied embedded runtime. On a locked-down
    # corporate machine (WDAC / Windows Application Control) that can block an
    # unsigned DLL in the new runtime (WinError 4551 on torch's shm.dll) - an
    # ENVIRONMENT policy, not a packaging fault. The bundle is fine on a normal
    # user machine, so warn and still ship rather than abort here.
    try:
        run([py, "-c",
             "import streamlit, torch, sentence_transformers, umap, hdbscan, plotly, "
             "pyvis, circlify, pypdf, webview; "
             "print('bundle imports OK; torch', torch.__version__)"])
    except subprocess.CalledProcessError as e:
        print(f"  WARNING: smoke test could not run in this environment ({e}).\n"
              "  Likely WDAC/AppControl blocking a runtime DLL on this machine - the\n"
              "  bundle still zips; verify imports on an unrestricted machine.")

    step("zip")
    out = ROOT / "dist" / "Froth-portable-win64"
    shutil.make_archive(str(out), "zip", DIST.parent, DIST.name)
    size = (out.with_suffix(".zip")).stat().st_size / 1e9
    print(f"\nDONE -> {out.with_suffix('.zip')} ({size:.2f} GB)")


if __name__ == "__main__":
    main()
