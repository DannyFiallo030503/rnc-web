"""Read-only numerical checks against the authorized original files.

Prints check outcomes only. No rows, identifiers, case counts or cell values
are written to console or fixtures. Run from the implementation repository.
"""

import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import sys
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_public")
import django
django.setup()
from django.conf import settings
from openpyxl import load_workbook
from public_site.aggregate_release import current_public_release
from public_site.aggregate_statistics import results
from analytics.rnc_classification import classify, catalog, code_set, child_catalog, reference_catalog

checks = 0


def verify(condition, label):
    global checks
    if not condition:
        raise RuntimeError("No coincide la comprobación: " + label)
    checks += 1


def close(actual, expected, label):
    verify(actual is not None and math.isclose(actual, expected, abs_tol=.011), label)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    release = current_public_release()
    verify(release is not None and release["synthetic"] is False and release["schema_version"] == 3, "origen real activo")
    source = ROOT.parent / "Nuevo/BD_2022.csv"
    docx = Path(settings.RNC_DICTIONARY_DOCX)
    population = Path(settings.RNC_POPULATION_XLSX)
    verify(digest(source) == release["provenance"]["original_csv_sha256"], "huella del CSV original")
    verify(digest(docx) == release["provenance"]["dictionary_docx_sha256"], "huella del diccionario")
    verify(digest(population) == release["provenance"]["population_xlsx_sha256"], "huella del denominador")
    reference_root = ROOT.parent / "Nuevo/DICCIONARIO RNC"
    for filename, expected_hash in reference_catalog()["sources"].items():
        verify(digest(reference_root / filename) == expected_hash, "huella de nomenclador suministrado")
        verify(release["provenance"]["reference_dictionary_sha256"][filename] == expected_hash, "procedencia pública del nomenclador")
    child_path = reference_root / child_catalog()["source"]
    verify(digest(child_path) == release["provenance"]["child_classification_xlsx_sha256"], "huella de clasificación infantil")
    roman = ["I","II","III","IV","V","VI","VII","VIII","IX","X","XI","XII"]
    child_book = load_workbook(child_path, read_only=True, data_only=True)
    for record in child_book.active.iter_rows(min_row=2, values_only=True):
        original, label = str(record[2]).strip(), str(record[3]).strip()
        parent = original.rstrip("abcdef")
        suffix = original[len(parent):].upper()
        key = f"{roman.index(parent)+1:02}{suffix}"
        verify(child_catalog()["groups"][key]["label"] == label, "rótulo infantil íntegro del Excel")
        verify(child_catalog()["groups"][key]["group"] == f"{roman.index(parent)+1:02}", "jerarquía infantil del Excel")
    child_book.close()
    verify(all(group["label"] == group["source_label"] for group in catalog()[0]["groups"]), "rótulos del DOCX por aclaración del responsable")
    annuary = next((ROOT.parent / "Nuevo/ANUARIO").glob("*.docx"))
    verify(digest(annuary) == release["provenance"]["annuary_docx_sha256"], "huella de referencia de tasas")
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(docx) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    definitions = []
    for row in document.findall(".//w:tbl", ns)[1].findall("./w:tr", ns):
        cells = [" ".join("".join(n.text or "" for n in paragraph.findall(".//w:t", ns)) for paragraph in cell.findall("./w:p", ns)).strip() for cell in row.findall("./w:tc", ns)]
        definitions.append((cells[1].replace(" ", ""), cells[0].lstrip("-").strip()))
    verify(definitions == [(group["id"], group["source_label"]) for group in catalog()[0]["groups"]], "transcripción íntegra de grupos del DOCX")
    expected_weights = [12000,10000,9000,9000,8000,8000,6000,6000,6000,6000,5000,4000,4000,3000,2000,1000,500,500]
    ages = [f"{age}-{age+4}" for age in range(0,85,5)] + ["85+"]
    weights = dict(zip(ages, expected_weights))
    verify(release["standard_weights"] == weights and sum(weights.values()) == 100000, "pesos estándar")
    reference = []
    with source.open(encoding="utf-8-sig", newline="") as stream:
        for raw in csv.DictReader(stream):
            if not any(value.strip() for value in raw.values() if isinstance(value, str)):
                continue
            row = {key: (value or "").strip() for key, value in raw.items()}
            age = int(row["EDAD"])
            if not ((age >= 20 and row["COMP"] == "3") or (age < 20 and row["COMP"] != "2")):
                continue
            date = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
                try:
                    date = datetime.strptime(row["FECHAD"], fmt)
                    break
                except ValueError:
                    pass
            verify(date is not None and date.year == 2022, "año desde fecha de diagnóstico")
            band = "85+" if age >= 85 else f"{age//5*5}-{age//5*5+4}"
            classification = classify(row)
            if age >= 20:
                category = row["C10"][:3].upper()
                verify(category in code_set(classification["key"][4:]), "pertenencia del código al grupo de publicación")
                verify(category in code_set(classification["group"][4:]), "pertenencia al grupo principal")
            else:
                verify(classification["key"] == "CICN:"+row["CICN"].upper(), "conservación del código infantil")
            category = row["C10"][:3].upper() if age >= 20 else ""
            stage_eligible = age >= 20 and category not in {f"C{n}" for n in list(range(81,87))+list(range(91,97))}
            reference.append({"person_id": row["NOCASO"], "age": age, "age_group": band, "territory": row["PROV"][:2], "municipality": row["PROV"], "sex": {"1":"Hombres","2":"Mujeres"}[row["SEXO"]], "site": classification["key"], "site_group": classification["group"], "morphology": row["MORF"], "stage": row["ETAPA"] or "missing", "stage_eligible": stage_eligible, "vh": row["MORF"] != "8000", "scd": row["UNIDIDAD"] == "0000", "scd_known": bool(row["UNIDIDAD"]), "c10_total": age >= 20 and category.startswith("C") and int(category[1:]) <= 97})
    population_cells = []
    workbook = load_workbook(population, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    for row in sheet.iter_rows(min_row=2, values_only=True):
        province, age, municipality, sex, count = row[2], row[4], row[6], row[7], row[8]
        if any(value is None for value in (province, age, municipality, sex)) or not isinstance(count,(int,float)):
            continue
        age = 85 if str(age).strip().upper() == "85 MAS" else int(age)
        band = "85+" if age >= 85 else f"{age//5*5}-{age//5*5+4}"
        population_cells.append({"territory":str(int(province)),"municipality":str(int(municipality)),"sex":{1:"Hombres",2:"Mujeres"}[int(sex)],"age_group":band,"population":float(count)})
    workbook.close()
    verify(release["options"]["period"] == ["2022"], "único período de la entrega real")
    verify(release["cube"][""][0]["tumors"] == len(reference), "inclusión por edad y comportamiento")
    verify(release["person_identity_verified"] and release["cube"][""][0]["persons"] == len({row["person_id"] for row in reference}), "personas distintas por NOCASO confirmado")
    for cohort in ("all", "adult", "child"):
        scale = 1000000 if cohort == "child" else 100000
        applicable = ages if cohort=="all" else ages[4:] if cohort=="adult" else ages[:4]
        cases = [row for row in reference if row["age_group"] in applicable]
        residents = [row for row in population_cells if row["age_group"] in applicable]
        params = {"cohort":cohort,"dimension":"territory","metric":"count","unit":"tumors"}
        rows,total = results(params,release)
        verify(total["tumors"] == len(cases), "total de la población analizada")
        for row in rows:
            selected = [case for case in cases if case["territory"] == row["label"]]
            denominators = [cell for cell in residents if cell["territory"] == row["label"]]
            population_total = sum(cell["population"] for cell in denominators)
            verify(row["tumors"] == len(selected), "frecuencia territorial")
            verify(row["persons"] == len({case["person_id"] for case in selected}), "personas distintas territoriales")
            close(row["population"],population_total,"población independiente de los casos")
            close(row["relative_frequency"],len(selected)/len(cases)*100,"frecuencia relativa")
            close(row["crude_rate"],len(selected)/population_total*scale,"tasa cruda")
            by_age = Counter(case["age_group"] for case in selected)
            pop_age = defaultdict(float)
            for cell in denominators:pop_age[cell["age_group"]]+=cell["population"]
            if all(pop_age[age] > 0 for age in applicable):
                expected = sum(by_age[age]/pop_age[age]*weights[age] for age in applicable)/sum(weights[age] for age in applicable)*scale
                close(row["adjusted_rate"],expected,"tasa ajustada directa y truncada")
            close(row["vh_percent"],sum(case["vh"] for case in selected)/len(selected)*100,"verificación histológica")
            if all(case["scd_known"] for case in selected):
                close(row["scd_percent"],sum(case["scd"] for case in selected)/len(selected)*100,"solo certificado de defunción")
            else:verify(row["scd_percent"] is None,"SCD incompleto no convertido en cero")
        for dimension in ("site","site_group","morphology"):
            distribution,_ = results({**params,"dimension":dimension},release)
            expected = Counter(case[dimension] for case in cases)
            verify({row["label"]:row["tumors"] for row in distribution} == dict(expected),"distribución sin solapar grupos")
            verify(sum(row["tumors"] for row in distribution) == len(cases),"partición de categorías conserva el numerador")
            pop_age = defaultdict(float)
            for cell in residents:pop_age[cell["age_group"]]+=cell["population"]
            for row in distribution:
                selected=[case for case in cases if case[dimension]==row["label"]]
                close(row["vh_percent"],sum(case["vh"] for case in selected)/len(selected)*100,"VH por categoría")
                if all(case["scd_known"] for case in selected):
                    close(row["scd_percent"],sum(case["scd"] for case in selected)/len(selected)*100,"SCD por categoría")
                else:verify(row["scd_percent"] is None,"SCD por categoría con fuente incompleta")
                if dimension in {"site","site_group"} and cohort=="all":
                    verify(row["crude_rate"] is None and row["adjusted_rate"] is None,"clasificadores por edad sin denominador mezclado")
                    continue
                close(row["population"],sum(cell["population"] for cell in residents),"denominador por categoría independiente del tumor")
                close(row["crude_rate"],len(selected)/sum(cell["population"] for cell in residents)*scale,"tasa cruda por grupo y morfología")
                by_age=Counter(case["age_group"] for case in selected)
                expected_asr=sum(by_age[age]/pop_age[age]*weights[age] for age in applicable)/sum(weights[age] for age in applicable)*scale
                close(row["adjusted_rate"],expected_asr,"ajuste directo por grupo y morfología sin sumar tasas redondeadas")
    stage_rows,_ = results({"cohort":"adult","dimension":"stage","metric":"share","unit":"tumors"},release)
    stage_cases = [case for case in reference if case["stage_eligible"]]
    verify({row["label"]:row["tumors"] for row in stage_rows} == dict(Counter(case["stage"] for case in stage_cases)),"distribución de códigos de etapa con exclusiones documentadas")
    for row in stage_rows:
        close(row["relative_frequency"],row["tumors"]/len(stage_cases)*100,"denominador de la distribución por etapa")
        verify(row["crude_rate"] is None and row["adjusted_rate"] is None,"etapa sin tasa de incidencia ficticia")
    c10_rows,_ = results({"cohort":"adult","dimension":"site_group","site":["DOCX:C00-97"],"metric":"count","unit":"tumors"},release)
    verify(sum(row["tumors"] for row in c10_rows) == sum(case["c10_total"] for case in reference),"total C00-97 separado de códigos D y CICN")
    annuary_rows, _ = results({"cohort":"adult", "dimension":"site_group", "site":["ANUARIO:C00-96"], "metric":"count", "unit":"tumors"}, release)
    verify(sum(row["tumors"] for row in annuary_rows) == sum(case["c10_total"] and case["site"] != "C10:C97" for case in reference), "total C00-96 separado del total del DOCX")
    for cohort in ("all", "adult", "child"):
        selected_cases = [case for case in reference if cohort == "all" or (case["age"] < 20) == (cohort == "child")]
        territories = sorted({case["territory"] for case in selected_cases})[:2]
        selected_cases = [case for case in selected_cases if case["territory"] in territories]
        people_rows, people_total = results({"dimension":"site_group", "cohort":cohort, "territory":territories, "unit":"persons", "metric":"count"}, release)
        verify(people_total["persons"] == len({case["person_id"] for case in selected_cases}), "personas distintas con selección múltiple")
        for row in people_rows:
            verify(row["persons"] == len({case["person_id"] for case in selected_cases if case["site_group"] == row["label"]}), "personas distintas por grupo principal")
    queries = []
    for dimension in ("territory","municipality","sex","age_group","period","site"):
        for metric in ("count","share","rate","asr"):
            if (dimension=="site" and metric in {"rate","asr"}) or (dimension=="age_group" and metric=="asr"):
                continue
            params={"dimension":dimension,"metric":metric,"unit":"tumors","chart":"bar"}
            rows,_=results(params,release)
            if any(row["value"] is None for row in rows):
                continue
            queries.append({"params":params,"rows":[{key:row[key] for key in ("label","tumors","persons","population","relative_frequency","crude_rate","adjusted_rate","value")} for row in rows]})
    for item in list(queries):
        params = {**item["params"], "unit":"persons", "territory":release["options"]["territory"][:2]}
        rows, _ = results(params, release)
        if rows and all(row["value"] is not None for row in rows):
            queries.append({"params":params, "rows":[{key:row[key] for key in ("label","tumors","persons","population","relative_frequency","crude_rate","adjusted_rate","value")} for row in rows]})
    with (Path(settings.PUBLIC_RELEASE_ROOT)/"current.json").open() as stream:
        pointer=json.load(stream)
    artifact=Path(settings.PUBLIC_RELEASE_ROOT)/(pointer["release_id"]+(".json.gz" if pointer.get("encoding")=="gzip" else ".json"))
    worker=subprocess.run(["node","scripts/verify_offline_worker.cjs"],input=json.dumps({"artifact":str(artifact),"queries":queries}),text=True,capture_output=True,cwd=ROOT)
    if worker.returncode:
        raise RuntimeError("No pasó la comparación numérica del worker: "+worker.stderr)
    print(f"Comprobaciones contra los originales aprobadas: {checks}.")
    print(worker.stdout.strip())
    print("No se mostraron registros, identificadores ni valores clínicos.")


if __name__ == "__main__":
    run()
