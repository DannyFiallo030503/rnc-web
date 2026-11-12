"""Validate evidence required before declaring a locale translation complete.

This gate never activates a locale. It checks catalog integrity and the
presence of explicit linguistic, institutional, functional, and release
approvals recorded in locale/reviews/<locale>.json.
"""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys

import polib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.languages import ACTIVE_LANGUAGES, ACTIVE_TRANSLATION_DOMAINS, PRIORITY_LANGUAGES

DOMAINS = ("django", "djangojs")
PLACEHOLDER = re.compile(r"%\(([^)]+)\)[#0 +\-]?(?:\d+)?(?:\.\d+)?[diouxXeEfFgGcrsa]")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{7,64}$")
PRIORITY = tuple(code for code, _english, _native, _active in PRIORITY_LANGUAGES)


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def evidence_file_matches(root, evidence):
    if not isinstance(evidence, dict):
        return False
    relative = evidence.get("path")
    digest = evidence.get("sha256")
    if not nonempty(relative) or not SHA256.fullmatch(str(digest or "")):
        return False
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    root = Path(root).resolve()
    path = (root / candidate).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == digest


def catalog_problems(path):
    """Return structural problems without exposing catalog values in logs."""
    problems = []
    catalog = polib.pofile(str(path), check_for_duplicates=True)
    entries = [entry for entry in catalog if entry.msgid and not entry.obsolete]
    plural_header = catalog.metadata.get("Plural-Forms", "")
    plural_count_match = re.search(r"nplurals\s*=\s*(\d+)", plural_header)
    plural_count = int(plural_count_match.group(1)) if plural_count_match else 0
    for entry in entries:
        if "fuzzy" in entry.flags:
            problems.append("contiene entradas fuzzy")
            break
        if entry.msgid_plural:
            if not plural_count or any(
                not entry.msgstr_plural.get(index, "").strip()
                for index in range(plural_count)
            ):
                problems.append("tiene formas plurales incompletas")
                break
            targets = entry.msgstr_plural.values()
        else:
            if not entry.msgstr.strip():
                problems.append("contiene traducciones vacías")
                break
            targets = (entry.msgstr,)
        expected = sorted(PLACEHOLDER.findall(entry.msgid))
        if any(sorted(PLACEHOLDER.findall(value)) != expected for value in targets):
            problems.append("tiene placeholders incompatibles")
            break
    if not entries:
        problems.append("no contiene mensajes revisables")
    return len(entries), problems


def source_language_inventory(root):
    """Hash the Spanish gettext source strings whose msgids render directly."""
    source_path = Path(root) / "locale/en/LC_MESSAGES/django.po"
    if not source_path.is_file():
        return None, 0
    catalog = polib.pofile(str(source_path), check_for_duplicates=True)
    source_entries = [
        [entry.msgctxt or "", entry.msgid, entry.msgid_plural or ""]
        for entry in catalog if entry.msgid and not entry.obsolete
    ]
    canonical = json.dumps(source_entries, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), len(source_entries)


def validate_locale(locale, root=ROOT, manifest_dir=None):
    root = Path(root)
    manifest_dir = Path(manifest_dir) if manifest_dir else root / "locale" / "reviews"
    manifest_path = manifest_dir / f"{locale}.json"
    errors = []
    if locale not in PRIORITY:
        return [f"locale no incluido en la prioridad: {locale}"]
    if not manifest_path.is_file():
        errors.append(f"falta evidencia de revisión: {manifest_path}")
        manifest = {"locale": locale}
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"manifiesto JSON ilegible para {locale}")
            manifest = {"locale": locale}

    if manifest.get("locale") != locale:
        errors.append("el locale declarado no coincide con el archivo")
    domains = ACTIVE_TRANSLATION_DOMAINS.get(locale, DOMAINS)
    catalog_records = manifest.get("catalogs")
    if not isinstance(catalog_records, dict) or set(catalog_records) != set(domains):
        errors.append("la evidencia de catálogos no coincide con los dominios requeridos")
        catalog_records = catalog_records if isinstance(catalog_records, dict) else {}
    for domain in domains:
        catalog_path = root / "locale" / locale / "LC_MESSAGES" / f"{domain}.po"
        record = catalog_records.get(domain)
        if not catalog_path.is_file():
            errors.append(f"falta catálogo {domain}")
            continue
        count, problems = catalog_problems(catalog_path)
        if problems:
            errors.append(f"catálogo {domain}: " + ", ".join(problems))
        if not isinstance(record, dict):
            errors.append(f"falta evidencia del catálogo {domain}")
            continue
        digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        if record.get("sha256") != digest or not SHA256.fullmatch(str(record.get("sha256", ""))):
            errors.append(f"la revisión de {domain} no corresponde al hash actual")
        if record.get("reviewed_entries") != count:
            errors.append(f"el conteo revisado de {domain} no coincide")

    if locale == "es":
        source_record = manifest.get("source_copy_review")
        digest, count = source_language_inventory(root)
        if digest is None:
            errors.append("falta catálogo fuente para verificar la revisión del texto español")
        elif not isinstance(source_record, dict):
            errors.append("falta revisión lingüística del texto fuente español")
        else:
            if source_record.get("sha256") != digest or not SHA256.fullmatch(str(source_record.get("sha256", ""))):
                errors.append("la revisión del texto fuente español no corresponde al inventario actual")
            if source_record.get("reviewed_entries") != count:
                errors.append("el conteo revisado del texto fuente español no coincide")

    linguistic = manifest.get("linguistic_review", {})
    if not isinstance(linguistic, dict) or linguistic.get("status") != "approved":
        errors.append("falta aprobación de revisión lingüística humana")
    else:
        for key in ("reviewer", "qualification"):
            if not nonempty(linguistic.get(key)):
                errors.append(f"revisión lingüística: falta {key}")
        if not evidence_file_matches(root, linguistic.get("report")):
            errors.append("revisión lingüística: falta informe vigente o su hash no coincide")
        if not valid_date(linguistic.get("reviewed_at")):
            errors.append("revisión lingüística: fecha inválida")

    institutional = manifest.get("institutional_review", {})
    if not isinstance(institutional, dict) or institutional.get("status") != "approved":
        errors.append("falta aprobación institucional de afirmaciones RNC")
    else:
        for key in ("authority", "evidence"):
            if not nonempty(institutional.get(key)):
                errors.append(f"revisión institucional: falta {key}")
        if not valid_date(institutional.get("reviewed_at")):
            errors.append("revisión institucional: fecha inválida")

    functional = manifest.get("functional_validation", {})
    if not isinstance(functional, dict) or functional.get("status") != "passed":
        errors.append("faltan pruebas funcionales aprobadas para este locale")
    else:
        if not REVISION.fullmatch(str(functional.get("revision", ""))):
            errors.append("pruebas funcionales: revisión debe ser un SHA de 7–64 caracteres")
        if not evidence_file_matches(root, functional.get("report")):
            errors.append("pruebas funcionales: falta reporte vigente o su hash no coincide")
        if not valid_date(functional.get("validated_at")):
            errors.append("pruebas funcionales: fecha inválida")
        surfaces = functional.get("surfaces")
        required_surfaces = {"public", "admin", "javascript", "exports", "offline", "formats"}
        if not isinstance(surfaces, list) or not required_surfaces.issubset(set(surfaces)):
            errors.append("pruebas funcionales: cobertura incompleta de superficies")

    release = manifest.get("release", {})
    if not isinstance(release, dict) or release.get("status") != "complete":
        errors.append("el estado de salida debe seguir parcial hasta aprobar todos los requisitos")
    else:
        if not nonempty(release.get("approved_by")):
            errors.append("salida: falta responsable de aprobación")
        if not valid_date(release.get("approved_at")):
            errors.append("salida: fecha inválida")
    return errors


def validate_active_locales(active_languages=None, root=ROOT, manifest_dir=None):
    """Require every additional selectable locale to have passed its release gate.

    English and Spanish are mandatory source/product languages and may remain
    explicitly partial. New locales are selectable only after full evidence.
    """
    active_languages = ACTIVE_LANGUAGES if active_languages is None else active_languages
    errors = []
    for locale, _display_name in active_languages:
        if locale in {"en", "es"}:
            continue
        locale_errors = validate_locale(locale, root, manifest_dir)
        if locale_errors:
            errors.append((locale, locale_errors))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", choices=PRIORITY, action="append", help="validar un locale; puede repetirse")
    parser.add_argument("--manifest-dir", type=Path, default=ROOT / "locale" / "reviews")
    parser.add_argument(
        "--check-activation", action="store_true",
        help="fallar si un locale adicional seleccionable no pasó su puerta de salida",
    )
    args = parser.parse_args(argv)
    if args.check_activation:
        activation_errors = validate_active_locales(
            ACTIVE_LANGUAGES, ROOT, args.manifest_dir
        )
        if not activation_errors:
            print("Activación verificada: no hay locales adicionales sin puerta completa.")
            return 0
        for locale, errors in activation_errors:
            print(f"{locale}: activación bloqueada ({len(errors)} requisitos pendientes)")
            for error in errors:
                print(f"  - {error}")
        return 1
    locales = args.locale or list(PRIORITY)
    failures = 0
    for locale in locales:
        errors = validate_locale(locale, ROOT, args.manifest_dir)
        if errors:
            failures += 1
            print(f"{locale}: PARCIAL ({len(errors)} requisitos pendientes)")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{locale}: PUERTA COMPLETA (evidencia documentada)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
