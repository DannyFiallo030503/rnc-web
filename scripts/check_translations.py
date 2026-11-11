"""Check catalog coverage and interpolation contracts for active languages.

This does not prove that every visible string has been marked or that copy has
passed human review; use audit_unmarked_template_text.py and TRANSLATIONS.md too.
"""

from pathlib import Path
import ast
import re
import sys

import polib


ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ROOT / "locale"
sys.path.insert(0, str(ROOT))
from config.languages import ACTIVE_LANGUAGES, ACTIVE_TRANSLATION_DOMAINS
from analytics.catalogs import SEXES, SITES

TEMPLATE_MARKER = re.compile(r"{%\s*(?:translate|trans)\s+(['\"])(.*?)\1\s*%}", re.S)
TEMPLATE_BLOCKTRANS = re.compile(
    r"{%\s*blocktrans\b[^%]*%}(.*?){%\s*endblocktrans\s*%}", re.S
)
TEMPLATE_PLURAL = re.compile(r"{%\s*plural\s*%}", re.S)
TEMPLATE_VARIABLE = re.compile(r"{{\s*([A-Za-z_]\w*)\s*}}")
JS_SINGLE_MARKER = re.compile(
    r"\b(?:t|fmt|format|gettext)\(\s*(['\"])(.*?)\1", re.S
)
JS_PLURAL_MARKER = re.compile(
    r"\b(?:ngettext|plural)\(\s*(['\"])(.*?)\1\s*,\s*(['\"])(.*?)\3",
    re.S,
)
JS_CONTEXT_MARKER = re.compile(
    r"\bpgettext\(\s*(['\"])(?:.*?)\1\s*,\s*(['\"])(.*?)\2", re.S
)
ACTIVE = {code: ACTIVE_TRANSLATION_DOMAINS.get(code, ()) for code, _name in ACTIVE_LANGUAGES}
SCAN_ROOTS = ("config", "public_site", "analytics", "templates", "static")
PLACEHOLDER = re.compile(r"%\(([^)]+)\)[#0 +\-]?(?:\d+)?(?:\.\d+)?[diouxXeEfFgGcrsa]")
DYNAMIC_CATEGORY_LABELS = {
    item["name"] for item in (*SEXES.values(), *SITES.values())
}


def literals(path):
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        found = {match.group(2) for match in TEMPLATE_MARKER.finditer(content)}
        for match in TEMPLATE_BLOCKTRANS.finditer(content):
            singular = TEMPLATE_PLURAL.split(match.group(1), maxsplit=1)[0]
            message = TEMPLATE_VARIABLE.sub(r"%(\1)s", singular)
            message = re.sub(r"\s+", " ", message).strip()
            if message:
                found.add(message)
        return found
    if path.suffix in {".js", ".mjs"}:
        found = {
            match.group(2)
            for match in JS_SINGLE_MARKER.finditer(content)
        }
        found.update(match.group(3) for match in JS_CONTEXT_MARKER.finditer(content))
        for match in JS_PLURAL_MARKER.finditer(content):
            # Gettext indexes plural entries by the singular msgid; the
            # catalog validates msgid_plural and every translated plural form.
            found.add(match.group(2))
        return found
    tree = ast.parse(content, filename=str(path))
    found = set()
    marker_names = {"_", "gettext", "gettext_lazy", "pgettext", "pgettext_lazy", "ngettext", "ngettext_lazy"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
        )
        if name in marker_names:
            message_arg = 1 if name in {"pgettext", "pgettext_lazy"} else 0
            if len(node.args) <= message_arg:
                continue
            try:
                value = ast.literal_eval(node.args[message_arg])
            except (ValueError, TypeError):
                continue
            if isinstance(value, str):
                found.add(value)
    return found


def plural_literals(path):
    """Return singular/plural source pairs required by gettext call sites."""
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        pairs = set()
        for match in TEMPLATE_BLOCKTRANS.finditer(content):
            parts = TEMPLATE_PLURAL.split(match.group(1), maxsplit=1)
            if len(parts) != 2:
                continue
            singular, plural = (
                re.sub(r"\s+", " ", TEMPLATE_VARIABLE.sub(r"%(\1)s", part)).strip()
                for part in parts
            )
            if singular and plural:
                pairs.add((singular, plural))
        return pairs
    if path.suffix in {".js", ".mjs"}:
        return {
            (match.group(2), match.group(4))
            for match in JS_PLURAL_MARKER.finditer(content)
        }
    tree = ast.parse(content, filename=str(path))
    pairs = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
        )
        if name not in {"ngettext", "ngettext_lazy"}:
            continue
        try:
            singular, plural = (ast.literal_eval(node.args[index]) for index in (0, 1))
        except (ValueError, TypeError):
            continue
        if isinstance(singular, str) and isinstance(plural, str):
            pairs.add((singular, plural))
    return pairs


def complete_translation(entry):
    """Require all plural forms, and exclude fuzzy suggestions from coverage."""
    if "fuzzy" in entry.flags:
        return False
    if entry.msgid_plural:
        return bool(entry.msgstr_plural) and all(value.strip() for value in entry.msgstr_plural.values())
    return bool(entry.msgstr.strip())


def catalog_inventory_extras(required_messages, catalog):
    """Return active PO msgids that are no longer present in source literals."""
    catalog_messages = {
        entry.msgid
        for entry in catalog
        if entry.msgid and not entry.obsolete
    }
    return sorted(catalog_messages - set(required_messages))


def catalog_plural_mismatches(source_pairs, catalog):
    """Return source plural forms that disagree with their catalog entry."""
    entries = {
        entry.msgid: entry
        for entry in catalog
        if entry.msgid and not entry.obsolete
    }
    return sorted(
        (singular, source_plural, entries[singular].msgid_plural)
        for singular, source_plural in source_pairs
        if singular in entries and entries[singular].msgid_plural != source_plural
    )


def placeholder_names(message):
    return sorted(PLACEHOLDER.findall(message))


def main():
    required = set()
    required_js = set()
    plural_required = {"django": set(), "djangojs": set()}
    for relative in SCAN_ROOTS:
        for path in (ROOT / relative).rglob("*"):
            if path.suffix in {".py", ".html"} and "__pycache__" not in path.parts:
                required.update(literals(path))
                plural_required["django"].update(plural_literals(path))
            elif path.suffix in {".js", ".mjs"} and "vendor" not in path.parts and not path.name.endswith(".min.js"):
                required_js.update(literals(path))
                plural_required["djangojs"].update(plural_literals(path))
    failures = []
    for language, domains in ACTIVE.items():
        for domain in domains:
            path = CATALOGS / language / "LC_MESSAGES" / f"{domain}.po"
            if not path.exists():
                failures.append(f"Falta el catálogo {path.relative_to(ROOT)}")
                continue
            required_domain = (
                required | DYNAMIC_CATEGORY_LABELS
                if domain == "django"
                else required_js | DYNAMIC_CATEGORY_LABELS
            )
            catalog = polib.pofile(str(path))
            entries = {
                entry.msgid: entry
                for entry in catalog
                if entry.msgid and not entry.obsolete
            }
            translated = {
                message for message, entry in entries.items()
                if complete_translation(entry)
            }
            missing = sorted(required_domain - translated)
            if missing:
                failures.append(f"{language}/{domain}: {len(missing)} cadenas marcadas sin traducción")
                failures.extend(f"  - {message}" for message in missing)
            extra = catalog_inventory_extras(required_domain, catalog)
            if extra:
                failures.append(
                    f"{language}/{domain}: {len(extra)} entradas PO sin referencia actual"
                )
                failures.extend(f"  - retirar o volver a marcar: {message}" for message in extra)
            for singular, source_plural, catalog_plural in catalog_plural_mismatches(
                plural_required[domain], catalog
            ):
                failures.append(
                    f"{language}/{domain}: msgid_plural no coincide para "
                    f"{singular!r}: {catalog_plural!r} ≠ {source_plural!r}"
                )
            for message in sorted(required_domain & entries.keys()):
                entry = entries[message]
                source_names = placeholder_names(message)
                targets = entry.msgstr_plural.values() if entry.msgid_plural else (entry.msgstr,)
                for target in targets:
                    if not target.strip() or "fuzzy" in entry.flags:
                        continue
                    target_names = placeholder_names(target)
                    if source_names != target_names:
                        failures.append(
                            f"{language}/{domain}: placeholders distintos para {message!r}: "
                            f"{source_names!r} → {target_names!r}"
                        )

    unsupported_active = sorted(language for language, domains in ACTIVE.items() if not domains)
    if unsupported_active:
        failures.append(
            "Hay idiomas activos sin dominios declarados para la puerta de salida: "
            + ", ".join(unsupported_active)
        )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        f"OK: {len(required)} literales Django y {len(required_js)} literales JS "
        "marcados tienen traducción en los catálogos configurados. "
        "Esto no detecta textos visibles que todavía no estén marcados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
