#!/usr/bin/env python3
"""
unir_csvs.py - TransparenciaAR
Junta varios CSV parciales en un solo personas_completo.csv.
"""

import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Une varios CSV de personas en uno solo.")
    parser.add_argument("csvs", nargs="+", help="CSV de entrada")
    parser.add_argument("--salida", default="personas_completo.csv", help="CSV combinado de salida")
    args = parser.parse_args()

    todas_filas = []
    todas_columnas = []

    for archivo in args.csvs:
        path = Path(archivo)
        if not path.exists():
            print("No existe: " + archivo + " - se salteo")
            continue
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for col in reader.fieldnames or []:
                if col not in todas_columnas:
                    todas_columnas.append(col)
            filas = list(reader)
            todas_filas.extend(filas)
            print(archivo + ": " + str(len(filas)) + " filas")

    prioridad = ["nombre", "apellido", "cargo", "foto_url", "wikidata_id"]
    columnas_finales = [c for c in prioridad if c in todas_columnas]
    columnas_finales += [c for c in todas_columnas if c not in prioridad]

    salida = Path(args.salida)
    with open(salida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columnas_finales)
        writer.writeheader()
        for fila in todas_filas:
            writer.writerow({col: fila.get(col, "") for col in columnas_finales})

    incompletas = [f for f in todas_filas if not (f.get("nombre") and f.get("apellido") and f.get("cargo"))]

    print("")
    print("Total combinado: " + str(len(todas_filas)) + " personas -> " + str(salida))
    print("Columnas: " + str(columnas_finales))
    if incompletas:
        print(str(len(incompletas)) + " filas con nombre/apellido/cargo incompleto (revisar antes de bajar fotos)")

    pendientes = [f for f in todas_filas if f.get("nombre") == "VERIFICAR"]
    if pendientes:
        print(str(len(pendientes)) + " filas marcadas VERIFICAR - completalas a mano antes de correr fetch_fotos.py")


if __name__ == "__main__":
    main()
