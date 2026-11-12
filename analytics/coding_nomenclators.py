"""Read and search externally supplied, versioned coding nomenclators."""

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext_lazy as _


AXES = {
    "topography", "morphology", "behavior", "grade", "stage", "classification", "other",
}
PUBLIC_STATES = {"authorized", "deprecated"}
CONCEPT_FIELDS = {
    "concept_id", "name", "description", "language", "source", "license",
    "publication_status",
}
CODE_FIELDS = {
    "system", "edition", "axis", "code", "name", "description", "status",
    "source", "license", "relationship", "relationship_status",
}
CODE_STATES = {"current", "deprecated", "optional"}
RELATIONSHIPS = {"primary", "same-concept", "exact", "broader", "narrower", "related"}
RELATIONSHIP_STATES = {"source-declared", "validated-rnc", "pending"}


class CatalogError(ValueError):
    """The configured nomenclator is unreadable or does not meet its contract."""


def _required_strings(item, keys, label):
    if not isinstance(item, dict) or keys - item.keys():
        raise CatalogError(_("%(label)s: faltan campos requeridos.") % {"label": label})
    if any(not isinstance(item[key], str) or not item[key].strip() for key in keys):
        raise CatalogError(
            _("%(label)s: hay campos vacíos o con tipo inválido.") % {"label": label}
        )


def _web_url(value, label):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CatalogError(
            _("%(label)s: la fuente debe ser una URL HTTP o HTTPS.") % {"label": label}
        )


def validate_catalog_payload(payload):
    """Validate and normalize an in-memory catalog using the public contract."""
    if not isinstance(payload, dict) or not isinstance(payload.get("concepts"), list):
        raise CatalogError(_("El archivo debe contener un arreglo 'concepts'."))
    _required_strings(payload, {"version", "source"}, "Catálogo")
    _web_url(payload["source"], "Catálogo")

    concepts, concept_ids, code_ids = [], set(), set()
    for concept_number, concept in enumerate(payload["concepts"], 1):
        label = _("Concepto %(number)s") % {"number": concept_number}
        if not isinstance(concept, dict) or (CONCEPT_FIELDS | {"codes"}) - concept.keys():
            raise CatalogError(
                _("%(label)s: faltan campos requeridos.") % {"label": label}
            )
        _required_strings(concept, CONCEPT_FIELDS, label)
        _web_url(concept["source"], label)
        if concept["publication_status"] not in PUBLIC_STATES | {"draft"}:
            raise CatalogError(
                _("%(label)s: estado de publicación no admitido.") % {"label": label}
            )
        if concept["concept_id"] in concept_ids:
            raise CatalogError(
                _("%(label)s: identificador de concepto duplicado.") % {"label": label}
            )
        concept_ids.add(concept["concept_id"])
        if not isinstance(concept["codes"], list) or not concept["codes"]:
            raise CatalogError(
                _("%(label)s: debe contener uno o más códigos.") % {"label": label}
            )

        codes = []
        for code_number, code in enumerate(concept["codes"], 1):
            code_label = _("%(label)s, código %(number)s") % {
                "label": label,
                "number": code_number,
            }
            _required_strings(code, CODE_FIELDS, code_label)
            if code["axis"] not in AXES:
                raise CatalogError(_("%(label)s: eje no admitido.") % {"label": code_label})
            if code["status"] not in CODE_STATES:
                raise CatalogError(
                    _("%(label)s: estado de código no admitido.") % {"label": code_label}
                )
            if code["relationship"] not in RELATIONSHIPS:
                raise CatalogError(
                    _("%(label)s: relación de concepto no admitida.") % {"label": code_label}
                )
            if code["relationship_status"] not in RELATIONSHIP_STATES:
                raise CatalogError(
                    _("%(label)s: estado de relación no admitido.") % {"label": code_label}
                )
            _web_url(code["source"], code_label)
            identifier = (code["system"], code["edition"], code["axis"], code["code"])
            if identifier in code_ids:
                raise CatalogError(
                    _("%(label)s: código repetido para el mismo sistema y edición.")
                    % {"label": code_label}
                )
            code_ids.add(identifier)
            codes.append(code)
        concepts.append({**concept, "codes": codes})

    return {
        "version": payload["version"],
        "source": payload["source"],
        "concepts": concepts,
        "status": "available" if concepts else "empty",
    }


def load_catalog(path=None):
    """Load the JSON selected by RNC_CODING_CATALOG (or an explicit path)."""
    configured = path or getattr(settings, "RNC_CODING_CATALOG", "")
    if not configured:
        return {"version": "", "source": "", "concepts": [], "status": "unavailable"}
    try:
        payload = json.loads(Path(configured).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CatalogError(_("El catálogo configurado no se puede leer como JSON UTF-8.")) from error
    return validate_catalog_payload(payload)


def catalog_summary(catalog):
    """Return aggregate counts only; never print actual code values."""
    counts = Counter()
    for concept in catalog["concepts"]:
        counts["conceptos"] += 1
        counts[f"publicación:{concept['publication_status']}"] += 1
        for code in concept["codes"]:
            counts["códigos"] += 1
            counts[f"sistema:{code['system']} · {code['edition']} · {code['axis']}"] += 1
    return counts


def search_concepts(catalog, *, query="", system="", edition="", axis=""):
    query = query.casefold().strip()
    matches = []
    for concept in catalog["concepts"]:
        if concept["publication_status"] not in PUBLIC_STATES:
            continue
        codes = [
            code for code in concept["codes"]
            if code["relationship_status"] != "pending"
            and (not system or code["system"] == system)
            and (not edition or code["edition"] == edition)
            and (not axis or code["axis"] == axis)
        ]
        if not codes:
            continue
        if query:
            searchable = " ".join(
                [concept["concept_id"], concept["name"], concept["description"]]
                + [
                    " ".join(code[key] for key in ("code", "name", "description", "system", "edition"))
                    for code in codes
                ]
            ).casefold()
            if query not in searchable:
                continue
        matches.append({**concept, "codes": codes})
    return matches
