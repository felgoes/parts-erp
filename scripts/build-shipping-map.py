#!/usr/bin/env python3
"""Build the offline map from IBGE's Localidades 2022 GPKG ZIP and UF GeoJSON.

Localidades: https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/localidades/Localidades_do_Brasil/2022/
UF: https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson&qualidade=minima&intrarregiao=UF

Usage: python3 scripts/build-shipping-map.py localidades.zip limites.json
"""
import argparse
import json
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("localidades", type=Path)
    parser.add_argument("limites", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp, ZipFile(args.localidades) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".gpkg"))
        gpkg = Path(tmp) / "localidades.gpkg"
        gpkg.write_bytes(archive.read(member))
        with sqlite3.connect(gpkg) as db:
            rows = db.execute("""
                SELECT NM_LOCALIDADE, SIGLA_UF, LONG_LOCALIDADE, LAT_LOCALIDADE
                FROM BR_localidades_2022
                WHERE CT_LOCALIDADE IN ('Cidade', 'Distrito Estadual de Fernando de Noronha')
                ORDER BY CD_LOCALIDADE
            """).fetchall()

    cities = {}
    for city, state, lon, lat in rows:
        name = unicodedata.normalize("NFD", city).encode("ascii", "ignore").decode().lower()
        key = re.sub(r"[^a-z0-9]", "", name) + "," + state
        point = [round(lon, 3), round(-lat, 3)]
        if key in cities and cities[key] != point:
            raise ValueError(f"Municípios ambíguos: {key}")
        cities[key] = point

    states = []
    for feature in json.loads(args.limites.read_text())["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"]
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        elif geometry["type"] != "MultiPolygon":
            raise ValueError(geometry["type"])
        paths = []
        for polygon in polygons:
            for ring in polygon:
                points = " ".join(f"{x:.3f},{-y:.3f}" for x, y in ring[:-1])
                paths.append(f"M{points}Z")
        states.append("".join(paths))

    if len(states) != 27 or len(cities) < 5500:
        raise ValueError("Dados incompletos")
    output = Path(__file__).resolve().parents[1] / "frontend/public/geo/shipping-brazil-v1.json"
    output.write_text(json.dumps({"cities": cities, "states": states}, separators=(",", ":"), sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
