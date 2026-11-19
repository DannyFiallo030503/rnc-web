"""Versioned, disjoint publication groups transcribed from the supplied DOCX."""

import json
import os
import re
from functools import lru_cache
from pathlib import Path


def code_set(expression):
    result = set()
    for part in expression.replace(" ", "").split(","):
        match = re.fullmatch(r"([CD])(\d{2})(?:-([CD])?(\d{2}))?", part)
        if not match:
            raise ValueError("Rango del catálogo tumoral no reconocido.")
        letter, start, end_letter, end = match.groups()
        if end_letter and end_letter != letter:
            raise ValueError("El catálogo no admite rangos entre capítulos.")
        result.update(f"{letter}{number:02}" for number in range(int(start), int(end or start) + 1))
    return frozenset(result)


def read_private_catalog(name):
    default_directory = Path(__file__).resolve().parents[1] / "private" / "catalogs"
    directory = Path(os.environ.get("RNC_CLASSIFICATION_CATALOG_DIR") or default_directory)
    return json.loads((directory / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def reference_catalog():
    return read_private_catalog("rnc_reference_terms.json")


@lru_cache(maxsize=1)
def child_catalog():
    return read_private_catalog("rnc_child_groups.json")


@lru_cache(maxsize=1)
def catalog():
    data = read_private_catalog("rnc_site_groups.json")
    return data, [{**group, "members": code_set(group["id"])} for group in data["groups"]]


def classify(row):
    if int(row["EDAD"]) < 20:
        code = row["CICN"].strip().upper()
        if not re.fullmatch(r"\d{1,2}[A-Z]?", code):
            raise ValueError("CICN no tiene un formato reconocido.")
        entry = child_catalog()["groups"].get(code)
        group = entry["group"] if entry else code
        label = entry["label"] if entry else f"CICN {code}"
        parent = child_catalog()["groups"].get(group)
        return {"key": f"CICN:{code}", "label": f"{code} · {label}", "group": f"CICN:{group}", "group_label": parent["label"] if parent else label, "system": "CICN", "category": code}
    code = row["C10"].strip().upper()
    match = re.fullmatch(r"([CD]\d{2})(?:\.?\d)?", code)
    if not match:
        raise ValueError("C10 no tiene un formato reconocido.")
    category = match.group(1)
    _, groups = catalog()
    matches = [group for group in groups if group["level"] != "total" and category in group["members"]]
    parent = next((group for group in matches if group["level"] == "main"), None)
    details = [group for group in matches if group["level"] == "detail"]
    chosen = min(details, key=lambda group: len(group["members"])) if details else parent
    if chosen and chosen["level"] == "main" and any(group["members"] < chosen["members"] for group in groups if group["level"] == "detail"):
        chosen = None
    leaf = chosen["id"] if chosen else category
    label = chosen["label"] if chosen else reference_catalog()["cie10"].get(category, [category])[0]
    main = parent["id"] if parent else category
    main_label = parent["label"] if parent else label
    return {"key": f"C10:{leaf}", "label": f"{leaf} · {label}" if leaf != label else leaf, "group": f"C10:{main}", "group_label": f"{main} · {main_label}" if main != main_label else main, "system": "C10", "category": category}
