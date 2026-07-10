#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_nomina_wikidata.py - TransparenciaAR
Trae nomina de diputados y senadores desde Wikidata SPARQL.
Filtra por mandatos que comenzaron en 2023+ y no tienen fecha de fin = vigentes ahora.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TransparenciaAR/0.1 +https://crecermas.agency)",
    "Accept": "application/sparql-results+json",
}

CARGOS = {
    "diputado": {"qid": "Q18229570", "esperado": 257},
    "senador": {"qid": "Q18711738", "esperado": 72},
}

QUERY_TEMPLATE = """
SELECT DISTINCT ?persona ?personaLabel ?distritoLabel WHERE {
  ?persona p:P39 ?statement.
  ?statement ps:P39 wd:%s.
  ?statement pq:P580 ?inicio.
  FILTER (?inicio >= "2023-01-01"^^xsd:dateTime)
  FILTER NOT EXISTS { ?statement pq:P582 ?fin. }
  OPTIONAL { ?statement pq:P768 ?distrito. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
}
"""

def consultar_sparql(query, reintentos=3, timeout=90):
    ultimo_error = None
    for intento in range(1, reintentos + 1):
        try:
            r = requests.post(
                SPARQL_ENDPOINT,
                data={"query": query, "format": "json"},
                headers=HEADERS,
                timeout=timeout,
            )
            r.raise_for_status()
            return json.loads(r.content.decode("utf-8"))
        except requests.RequestException as e:
            ultimo_error = e
            if intento < reintentos:
                espera = 15 + (intento * 5)
                print("  Intento " + str(intento) + "/" + str(reintentos) + " fallo, reintentando en " + str(espera) + "s...")
                time.sleep(espera)
    raise RuntimeError("SPARQL fallo tras " + str(reintentos) + " intentos: " + str(ultimo_error))

def separar_nombre(nombre_completo):
    partes = nombre_completo.strip().split()
    if len(partes) == 1:
        return partes[0], ""
    return partes[0], " ".join(partes[1:])

def limpiar_distrito(valor):
    if not valor:
        return ""
    v = valor.replace("provincia de ", "").replace(" Province", "").strip()
    return v

def obtener_cargo(cargo):
    info = CARGOS[cargo]
    print("-> Consultando Wikidata SPARQL (" + cargo + "s, posicion " + info["qid"] + ")...")
    data = consultar_sparql(QUERY_TEMPLATE % info["qid"])

    personas = []
    for binding in data.get("results", {}).get("bindings", []):
        uri = binding.get("persona", {}).get("value", "")
        qid = uri.rsplit("/", 1)[-1] if uri else ""
        etiqueta = binding.get("personaLabel", {}).get("value", "").strip()
        distrito = limpiar_distrito(binding.get("distritoLabel", {}).get("value", ""))

        if not etiqueta or etiqueta == qid:
            continue

        nombre, apellido = separar_nombre(etiqueta)
        personas.append({
            "nombre": nombre,
            "apellido": apellido,
            "cargo": cargo,
            "provincia": distrito,
            "bloque": "",
            "mandato": "",
            "foto_url": "",
            "wikidata_id": qid,
            "fuente_url": "https://www.wikidata.org/wiki/" + qid,
            "fuente_nombre": "Wikidata (posicion " + info["qid"] + ", sin fecha de fin)",
        })

    vistos = set()
    unicos = []
    for p in personas:
        if p["wikidata_id"] not in vistos:
            vistos.add(p["wikidata_id"])
            unicos.append(p)

    print("  " + cargo + "s obtenidos: " + str(len(unicos)) + " (esperados ~" + str(info["esperado"]) + ")")
    if len(unicos) < info["esperado"] * 0.8:
        print("  AVISO: conteo bajo - Wikidata puede estar desactualizada.")
    return unicos

def main():
    parser = argparse.ArgumentParser(description="Nomina desde Wikidata SPARQL.")
    parser.add_argument("--solo", choices=["diputados", "senadores"], help="Traer solo un cargo")
    parser.add_argument("--salida", default="personas_congreso_wd.csv", help="CSV de salida")
    args = parser.parse_args()

    todas = []
    errores = []

    objetivos = []
    if args.solo in (None, "diputados"):
        objetivos.append("diputado")
    if args.solo in (None, "senadores"):
        objetivos.append("senador")

    for cargo in objetivos:
        try:
            todas += obtener_cargo(cargo)
        except RuntimeError as e:
            errores.append(str(e))
            print("  ERROR: " + str(e))

    salida = Path(args.salida)
    campos = ["nombre", "apellido", "cargo", "provincia", "bloque", "mandato",
              "foto_url", "wikidata_id", "fuente_url", "fuente_nombre"]
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
        print("Errores guardados en: " + str(errores_path))

if __name__ == "__main__":
    main()
