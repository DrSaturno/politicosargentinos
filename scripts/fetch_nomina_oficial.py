#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_nomina_oficial.py - TransparenciaAR
Nomina de diputados y senadores desde las FUENTES OFICIALES PRIMARIAS
(no Wikipedia, no Wikidata):

  - DIPUTADOS: www.hcdn.gob.ar/diputados/ (tabla HTML oficial en vivo).
    OJO: es un dominio distinto de datos.hcdn.gob.ar (la API que esta caida),
    asi que funciona aunque la API siga sin responder.

  - SENADORES: export JSON de datos abiertos del Senado:
    https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoSenadores/json

Ambas fuentes incluyen la URL de la foto oficial, asi que este script
tambien completa 'foto_url' directamente - no hace falta buscarla despues
en Wikidata para diputados/senadores (fetch_fotos.py solo haria falta para
gobernadores y gabinete, que no tienen una fuente estructurada equivalente).

Uso:
  pip install requests beautifulsoup4 lxml
  python fetch_nomina_oficial.py
  python fetch_nomina_oficial.py --solo diputados
  python fetch_nomina_oficial.py --solo senadores --salida personas_congreso.csv
"""

import argparse
import csv
import json
import re
import time
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TransparenciaAR/0.1 (proyecto de transparencia civica; contacto: admin@crecermas.agency)",
}

HCDN_DIPUTADOS_URL = "https://www.hcdn.gob.ar/diputados/"
SENADO_JSON_URL = "https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoSenadores/json"

ESPERADOS = {"diputado": 257, "senador": 72}


def fecha_ddmmyyyy_a_iso(texto):
    """'10/12/2023' -> '2023-12-10'. Devuelve '' si no matchea el formato."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", texto.strip())
    if not m:
        return ""
    dia, mes, anio = m.groups()
    return f"{anio}-{int(mes):02d}-{int(dia):02d}"


def title_es(texto):
    """Title-case que respeta 'de', 'del', 'la' en apellidos compuestos."""
    minusculas = {"de", "del", "la", "los", "las", "y"}
    palabras = texto.strip().lower().split()
    out = []
    for i, p in enumerate(palabras):
        if i > 0 and p in minusculas:
            out.append(p)
        else:
            out.append(p.capitalize())
    return " ".join(out)


def obtener_diputados(sesion, timeout=60, reintentos=3):
    from bs4 import BeautifulSoup

    personas, errores = [], []
    print("-> Consultando www.hcdn.gob.ar/diputados/ (fuente oficial en vivo)...")

    html = None
    for intento in range(1, reintentos + 1):
        try:
            r = sesion.get(HCDN_DIPUTADOS_URL, timeout=timeout)
            r.raise_for_status()
            html = r.content.decode("utf-8", errors="replace")
            break
        except requests.RequestException as e:
            if intento < reintentos:
                print("  Intento " + str(intento) + "/" + str(reintentos) + " fallo, reintentando en 8s...")
                time.sleep(8)
            else:
                errores.append("Error de red consultando " + HCDN_DIPUTADOS_URL + ": " + str(e))

    if html is None:
        return personas, errores

    soup = BeautifulSoup(html, "lxml")

    # Los links a fichas individuales de diputados tienen el patron
    # /diputados/<slug>/ (slug alfanumerico corto, ej. /diputados/haguirre/).
    # Los links de navegacion (nomina-actual, por-bloque, etc.) NO matchean.
    patron_link_persona = re.compile(r"^/diputados/[a-z0-9]+/?$")

    filas_vistas = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # normalizar a path relativo
        path = href.replace("https://www.hcdn.gob.ar", "").replace("http://www.hcdn.gob.ar", "")
        if not patron_link_persona.match(path):
            continue

        texto = a.get_text(separator=" ", strip=True)
        if not texto or "," not in texto:
            continue

        fila = a.find_parent("tr")
        if fila is None or id(fila) in filas_vistas:
            continue
        filas_vistas.add(id(fila))

        celdas = fila.find_all("td")
        celdas_texto = [c.get_text(separator=" ", strip=True) for c in celdas]

        # Foto: primer <img> de la fila (src o data-src)
        foto_url = ""
        img = fila.find("img")
        if img:
            foto_url = img.get("src") or img.get("data-src") or ""
            if foto_url.startswith("/"):
                foto_url = "https://www.hcdn.gob.ar" + foto_url
            if "silueta" in foto_url:  # placeholder generico = sin foto real
                foto_url = ""
            # La tabla de nomina linkea el thumbnail "_small" (60x60px), que
            # queda pixelado al mostrarlo mas grande en la web. Mismo archivo,
            # mismo dominio, pero "_medium" (200x200px) existe y luce bien.
            elif foto_url.endswith("_small.png"):
                foto_url = foto_url[: -len("_small.png")] + "_medium.png"

        apellido, nombre = [p.strip() for p in texto.split(",", 1)]

        # Las celdas de texto suelen venir en orden (segun columnas de la tabla oficial):
        # Distrito | Bloque | Mandato | Inicia mandato | Finaliza mandato | Fecha nacimiento
        resto = [c for c in celdas_texto if c and c != texto]
        distrito = resto[0] if len(resto) > 0 else ""
        bloque = resto[1] if len(resto) > 1 else ""
        mandato = resto[2] if len(resto) > 2 else ""
        inicia = resto[3] if len(resto) > 3 else ""
        finaliza = resto[4] if len(resto) > 4 else ""

        personas.append({
            "nombre": nombre,
            "apellido": apellido,
            "cargo": "diputado",
            "provincia": title_es(distrito) if distrito else "",
            "bloque": bloque,
            "partido": bloque,  # HCDN no distingue partido de bloque para diputados
            "mandato": mandato,
            "mandato_inicio": fecha_ddmmyyyy_a_iso(inicia),
            "mandato_fin": fecha_ddmmyyyy_a_iso(finaliza),
            "foto_url": foto_url,
            "wikidata_id": "",
            "fuente_url": HCDN_DIPUTADOS_URL,
            "fuente_nombre": "H. Camara de Diputados de la Nacion (nomina oficial en vivo)",
        })

    # Dedup por apellido+nombre
    vistos = set()
    unicos = []
    for p in personas:
        clave = (p["nombre"].lower(), p["apellido"].lower())
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(p)
    personas = unicos

    print("  diputados obtenidos: " + str(len(personas)) + " (esperados ~" + str(ESPERADOS["diputado"]) + ")")
    if len(personas) < ESPERADOS["diputado"] * 0.8:
        errores.append("Conteo de diputados bajo (" + str(len(personas)) + "). Revisar estructura de la pagina: " + HCDN_DIPUTADOS_URL)

    return personas, errores


def obtener_senadores(sesion, timeout=60, reintentos=3):
    personas, errores = [], []
    print("-> Consultando JSON de datos abiertos del Senado (fuente oficial)...")

    data = None
    for intento in range(1, reintentos + 1):
        try:
            r = sesion.get(SENADO_JSON_URL, timeout=timeout)
            r.raise_for_status()
            data = json.loads(r.content.decode("utf-8"))
            break
        except requests.RequestException as e:
            if intento < reintentos:
                print("  Intento " + str(intento) + "/" + str(reintentos) + " fallo, reintentando en 8s...")
                time.sleep(8)
            else:
                errores.append("Error de red consultando " + SENADO_JSON_URL + ": " + str(e))
        except (json.JSONDecodeError, KeyError) as e:
            errores.append("No se pudo interpretar el JSON del Senado: " + str(e))
            break

    if data is None:
        return personas, errores

    filas = data.get("table", {}).get("rows", [])
    for fila in filas:
        apellido = str(fila.get("APELLIDO", "")).strip()
        nombre = str(fila.get("NOMBRE", "")).strip()
        provincia = str(fila.get("PROVINCIA", "")).strip()
        bloque = str(fila.get("BLOQUE", "")).strip()
        partido = str(fila.get("PARTIDO O ALIANZA", "")).strip()
        mandato_inicio = str(fila.get("D_LEGAL", "")).strip()
        mandato_fin = str(fila.get("C_LEGAL", "")).strip()
        foto = str(fila.get("FOTO", "")).strip()
        # El JSON linkea la carpeta "fsena" (88x88px, pixelada en la web).
        # "fsenaG" es el mismo archivo en 110x110px y existe para todos los
        # senadores activos (verificado); no hay variante mas grande que esa.
        if "/images/fsena/" in foto:
            foto = foto.replace("/images/fsena/", "/images/fsenaG/")

        if not (apellido and nombre):
            continue

        mandato = ""
        if mandato_inicio and mandato_fin:
            anio_inicio = mandato_inicio.split("-")[0] if "-" in mandato_inicio else ""
            anio_fin = mandato_fin.split("-")[0] if "-" in mandato_fin else ""
            if anio_inicio and anio_fin:
                mandato = anio_inicio + "-" + anio_fin

        personas.append({
            "nombre": title_es(nombre),
            "apellido": title_es(apellido),
            "cargo": "senador",
            "provincia": title_es(provincia) if provincia else "",
            "bloque": bloque,
            "partido": title_es(partido) if partido else "",
            "mandato": mandato,
            "mandato_inicio": mandato_inicio if re.match(r"^\d{4}-\d{2}-\d{2}$", mandato_inicio) else "",
            "mandato_fin": mandato_fin if re.match(r"^\d{4}-\d{2}-\d{2}$", mandato_fin) else "",
            "foto_url": foto,
            "wikidata_id": "",
            "fuente_url": "https://www.senado.gob.ar/senadores/listados/listaSenadoRes",
            "fuente_nombre": "Honorable Senado de la Nacion (datos abiertos oficiales)",
        })

    print("  senadores obtenidos: " + str(len(personas)) + " (esperados ~" + str(ESPERADOS["senador"]) + ")")
    if len(personas) < ESPERADOS["senador"] * 0.8:
        errores.append("Conteo de senadores bajo (" + str(len(personas)) + "). Revisar: " + SENADO_JSON_URL)

    return personas, errores


def main():
    parser = argparse.ArgumentParser(description="Nomina de diputados y senadores desde fuentes oficiales primarias.")
    parser.add_argument("--solo", choices=["diputados", "senadores"], help="Traer solo un cargo")
    parser.add_argument("--salida", default="personas_congreso.csv", help="CSV de salida")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout en segundos por request")
    parser.add_argument("--reintentos", type=int, default=3, help="Reintentos ante error de red")
    args = parser.parse_args()

    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    todas, errores = [], []

    if args.solo in (None, "diputados"):
        p, e = obtener_diputados(sesion, timeout=args.timeout, reintentos=args.reintentos)
        todas += p
        errores += e

    if args.solo in (None, "senadores"):
        p, e = obtener_senadores(sesion, timeout=args.timeout, reintentos=args.reintentos)
        todas += p
        errores += e

    salida = Path(args.salida)
    campos = ["nombre", "apellido", "cargo", "provincia", "bloque", "partido", "mandato",
              "mandato_inicio", "mandato_fin", "foto_url", "wikidata_id", "fuente_url", "fuente_nombre"]
    with open(salida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(todas)

    print("")
    print("CSV generado: " + str(salida) + " (" + str(len(todas)) + " personas)")

    if errores:
        errores_path = salida.with_name(salida.stem + "_errores.txt")
        with open(errores_path, "w", encoding="utf-8") as f:
            f.write("\n".join(errores))
        print("Hubo " + str(len(errores)) + " advertencias - revisar: " + str(errores_path))
        for e in errores[:5]:
            print("  - " + e)


if __name__ == "__main__":
    main()
