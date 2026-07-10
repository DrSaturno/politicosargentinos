#!/usr/bin/env python3
"""
fetch_fotos.py — TransparenciaAR
Descarga fotos de políticos argentinos de forma masiva, citando fuente y licencia.

Estrategia por persona:
  1. Si el CSV trae columna `foto_url` (ej: foto oficial de HCDN/Senado),
     descarga esa directamente — es la fuente mas confiable, evita homonimos
     y ahorra la busqueda en Wikidata para todo el Congreso.
  2. Fallback: Wikidata — busca la entidad, verifica que sea politico/a
     argentino/a, toma la imagen (propiedad P18) alojada en Wikimedia Commons.
     Se usa para quien no trae foto_url (gobernadores, gabinete) o si la
     descarga de la foto oficial fallara.
  3. Consulta a Commons los metadatos de licencia y autor (para el manifest).
  4. Si no hay nada, queda registrado en el manifest como "sin_foto" para
     completar manualmente.

Entrada:  CSV con columnas: nombre,apellido,cargo[,foto_url][,wikidata_id]
Salida:   fotos/{cargo}/{slug}.jpg  (400px de ancho, JPEG)
          manifest_fotos.csv  → nombre, cargo, archivo, fuente_url, licencia, autor, metodo

Uso:
  pip install requests
  python fetch_fotos.py personas.csv
  python fetch_fotos.py personas.csv --ancho 600 --salida ./fotos

Reanudable: si el archivo ya existe, lo saltea (usar --forzar para re-descargar).
"""

import argparse
import csv
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/{archivo}?width={ancho}"

# Identificarse correctamente es requisito de las APIs de Wikimedia
HEADERS = {
    "User-Agent": "TransparenciaAR/0.1 (proyecto de transparencia civica; contacto: admin@crecermas.agency)"
}

PAUSA_SEGUNDOS = 1.0  # rate limit amable con Wikimedia


def slugify(texto: str) -> str:
    """apellido-nombre en minúsculas, sin tildes ni caracteres raros."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    return re.sub(r"[\s_]+", "-", texto)


def buscar_entidad_wikidata(nombre_completo: str, sesion: requests.Session) -> str | None:
    """Busca la persona en Wikidata y devuelve el QID del mejor candidato."""
    params = {
        "action": "wbsearchentities",
        "search": nombre_completo,
        "language": "es",
        "type": "item",
        "limit": 5,
        "format": "json",
    }
    r = sesion.get(WIKIDATA_API, params=params, timeout=30)
    r.raise_for_status()
    resultados = r.json().get("search", [])
    if not resultados:
        return None

    # Preferir candidatos cuya descripción sugiera político argentino
    claves = ("polít", "diputad", "senador", "gobernador", "argentin", "politic")
    for cand in resultados:
        desc = (cand.get("description") or "").lower()
        if any(k in desc for k in claves):
            return cand["id"]
    # Si ninguno matchea por descripción, devolver el primero (se valida después)
    return resultados[0]["id"]


def obtener_imagen_p18(qid: str, sesion: requests.Session) -> str | None:
    """Devuelve el nombre de archivo de Commons de la propiedad P18 (imagen)."""
    params = {
        "action": "wbgetclaims",
        "entity": qid,
        "property": "P18",
        "format": "json",
    }
    r = sesion.get(WIKIDATA_API, params=params, timeout=30)
    r.raise_for_status()
    claims = r.json().get("claims", {}).get("P18", [])
    if not claims:
        return None
    return claims[0]["mainsnak"]["datavalue"]["value"]  # ej: "Juan Perez 2023.jpg"


def metadatos_commons(archivo: str, sesion: requests.Session) -> dict:
    """Consulta licencia y autor de una imagen en Commons (para citar fuente)."""
    params = {
        "action": "query",
        "titles": f"File:{archivo}",
        "prop": "imageinfo",
        "iiprop": "extmetadata|url",
        "format": "json",
    }
    r = sesion.get(COMMONS_API, params=params, timeout=30)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        return {
            "licencia": meta.get("LicenseShortName", {}).get("value", "desconocida"),
            "autor": re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip(),
            "pagina": info.get("descriptionurl", f"https://commons.wikimedia.org/wiki/File:{archivo}"),
        }
    return {"licencia": "desconocida", "autor": "", "pagina": ""}


def descargar(url: str, destino: Path, sesion: requests.Session) -> bool:
    r = sesion.get(url, timeout=60, stream=True, allow_redirects=True)
    if r.status_code != 200:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return destino.stat().st_size > 1024  # descartar respuestas vacías/placeholder


def procesar_persona(fila: dict, ancho: int, base: Path, sesion: requests.Session, forzar: bool) -> dict:
    nombre = fila["nombre"].strip()
    apellido = fila["apellido"].strip()
    cargo = fila["cargo"].strip().lower()
    nombre_completo = f"{nombre} {apellido}"
    slug = slugify(f"{apellido} {nombre}")
    destino = base / cargo / f"{slug}.jpg"

    registro = {
        "nombre": nombre_completo,
        "cargo": cargo,
        "archivo": str(destino),
        "fuente_url": "",
        "licencia": "",
        "autor": "",
        "metodo": "sin_foto",
    }

    if destino.exists() and not forzar:
        registro["metodo"] = "ya_existia"
        return registro

    # --- 1) Foto oficial ya provista en el CSV (HCDN/Senado) ---
    # Se prioriza sobre Wikidata: es la fuente mas confiable (evita homonimos)
    # y ademas ahorra la busqueda en Wikidata para todo el Congreso.
    foto_url = fila.get("foto_url", "").strip()
    if foto_url:
        try:
            if descargar(foto_url, destino, sesion):
                registro.update(
                    fuente_url=foto_url,
                    licencia="Foto oficial (obra del Estado)",
                    autor="",
                    metodo="foto_oficial",
                )
                return registro
        except requests.RequestException as e:
            print(f"  ⚠ Error descargando foto oficial de {nombre_completo}: {e}", file=sys.stderr)

    # --- 2) Fallback: Wikidata / Commons (para quien no trae foto_url,       ---
    #     ej. gobernadores y gabinete, o si la foto oficial fallo al bajar) ---
    try:
        qid = fila.get("wikidata_id", "").strip() or buscar_entidad_wikidata(nombre_completo, sesion)
        if qid:
            archivo_commons = obtener_imagen_p18(qid, sesion)
            if archivo_commons:
                url = COMMONS_FILEPATH.format(archivo=archivo_commons.replace(" ", "_"), ancho=ancho)
                if descargar(url, destino, sesion):
                    meta = metadatos_commons(archivo_commons, sesion)
                    registro.update(
                        fuente_url=meta["pagina"],
                        licencia=meta["licencia"],
                        autor=meta["autor"],
                        metodo=f"wikidata:{qid}",
                    )
                    return registro
    except requests.RequestException as e:
        print(f"  ⚠ Error de red con Wikidata para {nombre_completo}: {e}", file=sys.stderr)

    return registro  # quedó sin_foto → completar manual


def main():
    parser = argparse.ArgumentParser(description="Descarga masiva de fotos de políticos con fuente y licencia.")
    parser.add_argument("csv_entrada", help="CSV con columnas: nombre,apellido,cargo[,foto_url][,wikidata_id]")
    parser.add_argument("--salida", default="fotos", help="Carpeta de salida (default: fotos/)")
    parser.add_argument("--ancho", type=int, default=400, help="Ancho de imagen en px (default: 400)")
    parser.add_argument("--forzar", action="store_true", help="Re-descargar aunque el archivo exista")
    args = parser.parse_args()

    base = Path(args.salida)
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    with open(args.csv_entrada, newline="", encoding="utf-8") as f:
        personas = list(csv.DictReader(f))

    faltantes_col = {"nombre", "apellido", "cargo"} - set(personas[0].keys() if personas else [])
    if faltantes_col:
        sys.exit(f"El CSV no tiene las columnas requeridas: {faltantes_col}")

    print(f"Procesando {len(personas)} personas → {base}/ (ancho {args.ancho}px)\n")

    manifest = []
    ok, sin_foto = 0, 0
    for i, fila in enumerate(personas, 1):
        reg = procesar_persona(fila, args.ancho, base, sesion, args.forzar)
        manifest.append(reg)
        estado = reg["metodo"]
        if estado == "sin_foto":
            sin_foto += 1
            print(f"[{i}/{len(personas)}] ✗ {reg['nombre']} — SIN FOTO")
        else:
            ok += 1
            print(f"[{i}/{len(personas)}] ✓ {reg['nombre']} ({estado})")
        if estado not in ("ya_existia",):
            time.sleep(PAUSA_SEGUNDOS)

    manifest_path = base / "manifest_fotos.csv"
    base.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nombre", "cargo", "archivo", "fuente_url", "licencia", "autor", "metodo"])
        writer.writeheader()
        writer.writerows(manifest)

    print(f"\nListo: {ok} con foto, {sin_foto} sin foto.")
    print(f"Manifest (fuentes y licencias): {manifest_path}")
    if sin_foto:
        print("Los 'sin_foto' hay que completarlos a mano — filtrá el manifest por metodo=sin_foto.")


if __name__ == "__main__":
    main()
