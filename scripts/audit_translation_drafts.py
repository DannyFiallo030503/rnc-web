"""Audit completeness and isolation of inactive machine-translation drafts."""

from pathlib import Path
import re
import sys

import polib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.languages import ACTIVE_LANGUAGES, PRIORITY_LANGUAGES

LOCALE_ROOT = ROOT / "locale"
ACTIVE = {code for code, _name in ACTIVE_LANGUAGES}
DRAFTS = tuple(code for code, _english, _native, _active in PRIORITY_LANGUAGES if code not in ACTIVE)
DOMAINS = ("django", "djangojs")
PLACEHOLDER = re.compile(r"%\(([^)]+)\)[#0 +\-]?(?:\d+)?(?:\.\d+)?[diouxXeEfFgGcrsa]|%%")
SPANISH_ONLY_COPY = re.compile(
    r"\b(?:poblaci[oó]n|tasas?|falta|edad|ajuste|riñ[oó]n)\b", re.I
)
NON_LATIN_RANGES = {
    "zh-hans": ((0x4E00, 0x9FFF),),
    "hi": ((0x0900, 0x097F),),
    "ar": ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)),
    "bn": ((0x0980, 0x09FF),),
    "ur": ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)),
    "ru": ((0x0400, 0x04FF),),
}
ENGLISH_COPY_EXCEPTIONS = {
    "zh-hans": {"Excel", "rnc-synthetic-query"},
    "ar": {"NCI/SEER · SEER*Explorer"},
    "bn": {"OMS · ICD‑O‑3", "WHO · ICD‑O‑3", "rnc-synthetic-query"},
    "ur": {"OMS · ICD‑O‑3", "WHO · ICD‑O‑3", "NCI/SEER · SEER*Explorer", "rnc-synthetic-query"},
    "ru": {"NCI/SEER · SEER*Explorer"},
}
SEMANTIC_RISKS = {
    "zh-hans": (
        (re.compile(r"barras?", re.I), re.compile(r"酒吧|单杠")),
        (re.compile(r"^circular$", re.I), re.compile(r"馅饼")),
        (re.compile(r"Segi.*Doll", re.I), re.compile(r"娃娃")),
        (re.compile(r"Personas distintas", re.I), re.compile(r"独特的人")),
        (re.compile(r"Grupo de localización", re.I), re.compile(r"站点组")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^甜甜圈$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"勇气")),
        (
            re.compile(r".+"),
            re.compile(
                r"\b(?:Candidate methods|The application does not|codes are not translated)\b",
                re.I,
            ),
        ),
    ),
    "ru": (
        (re.compile(r"barras?", re.I), re.compile(r"бар|батончик|турник", re.I)),
        (re.compile(r"^circular$", re.I), re.compile(r"пирог|торт", re.I)),
        (re.compile(r".+"), re.compile(r"\b(?:and|the)\b", re.I)),
        (
            re.compile(r"tasa|rate", re.I),
            re.compile(r"\b(?:ставк\w*|скорост\w*|цена\w*)\b", re.I),
        ),
        (re.compile(r"Este prototipo solo admite el paquete sintético", re.I), re.compile(r"упаковк\w*", re.I)),
        (re.compile(r"Personas distintas", re.I), re.compile(r"Разные люди")),
        (re.compile(r"^Sexo$", re.I), re.compile(r"^Секс$")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^Пончик$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"доблест")),
    ),
    "fr": (
        (re.compile(r"^circular$", re.I), re.compile(r"\btarte\b", re.I)),
        (re.compile(r"barras? agrupadas", re.I), re.compile(r"\bagrupadas\b", re.I)),
        (re.compile(r"barras porcentuales", re.I), re.compile(r"\bporcentu\w*", re.I)),
        (re.compile(r"El gráfico circular necesita hasta ocho categorías", re.I), re.compile(r"une ou plusieurs catégories|une seule catégorie", re.I)),
        (re.compile(r"Este gráfico necesita al menos dos categorías con datos", re.I), re.compile(r"moins de deux catégories", re.I)),
        (re.compile(r"Enter at least %\(length\)s characters", re.I), re.compile(r"au moins les caractères %\(length\)s", re.I)),
        (re.compile(r"Enter no more than %\(length\)s characters", re.I), re.compile(r"plus de caractères %\(length\)s", re.I)),
        (re.compile(r"Text was not added: enter no more than %\(length\)s characters", re.I), re.compile(r"plus de caractères %\(length\)s", re.I)),
        (re.compile(r"Puedes combinar varios valores", re.I), re.compile(r"une valeur maximale", re.I)),
        (re.compile(r"Este prototipo solo admite el paquete sintético", re.I), re.compile(r"admet seul", re.I)),
        (re.compile(r"composición de personas solo por sexo", re.I), re.compile(r"personnages seuls", re.I)),
        (re.compile(r"Personas distintas", re.I), re.compile(r"Personas distinctes")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^(?:Beignet|Anneau)$", re.I)),
        (re.compile(r"Tasa cruda / específica por 100 000", re.I), re.compile(r"Tasa cruda", re.I)),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"courage", re.I)),
    ),
    "pt-br": (
        (re.compile(r"^circular$", re.I), re.compile(r"^torta$", re.I)),
        (re.compile(r"barras? agrupadas", re.I), re.compile(r"\bbares\b", re.I)),
        (re.compile(r"cada barra", re.I), re.compile(r"\band\b", re.I)),
        (re.compile(r"Enter at least %\(length\)s characters", re.I), re.compile(r"pelo menos caracteres %\(length\)s", re.I)),
        (re.compile(r"Enter no more than %\(length\)s characters", re.I), re.compile(r"no máximo caracteres %\(length\)s", re.I)),
        (re.compile(r"Este prototipo solo admite el paquete sintético", re.I), re.compile(r"\bembalagem\b", re.I)),
        (re.compile(r"Grupo de localización", re.I), re.compile(r"\bsites?\b", re.I)),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^Rosquinha$", re.I)),
    ),
    "hi": (
        (re.compile(r"El corte activo no incluye desglose por municipio", re.I), re.compile(r"नगर पालिका टूटना", re.I)),
        (re.compile(r"El corte agregado no permite deduplicar personas", re.I), re.compile(r"लोगों को डुप्लिकेट नहीं कर सकती", re.I)),
        (re.compile(r"^Sexo$", re.I), re.compile(r"^सेक्स$")),
        (re.compile(r"^Frecuencia absoluta$", re.I), re.compile(r"पूर्ण आवृत्ति")),
        (re.compile(r"^Población denominadora$", re.I), re.compile(r"भाजक जनसंख्या")),
        (re.compile(r"^Grupo de localización$", re.I), re.compile(r"^साइट समूह$")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^डोनट$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"वीरता")),
    ),
    "bn": (
        (re.compile(r"El corte activo no incluye desglose por municipio", re.I), re.compile(r"পৌরসভা ভাঙ্গন", re.I)),
        (re.compile(r"El corte agregado no permite deduplicar personas", re.I), re.compile(r"লোকেদের অনুলিপি করতে পারে না", re.I)),
        (re.compile(r"^Sexo$", re.I), re.compile(r"^সেক্স$")),
        (re.compile(r"^Frecuencia absoluta$", re.I), re.compile(r"পরম ফ্রিকোয়েন্সি")),
        (re.compile(r"^Grupo de localización$", re.I), re.compile(r"^সাইট গ্রুপ$")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^ডোনাট$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"বীরত্ব|এল মিসমো", re.I)),
    ),
    "ur": (
        (re.compile(r"El corte activo no incluye desglose por municipio", re.I), re.compile(r"میونسپلٹی کی کوئی خرابی", re.I)),
        (re.compile(r"El corte agregado no permite deduplicar personas", re.I), re.compile(r"لوگوں کی نقل نہیں کر سکتی", re.I)),
        (re.compile(r"^Sexo$", re.I), re.compile(r"^سیکس$")),
        (re.compile(r"^Grupo de localización$", re.I), re.compile(r"سائٹ گروپ")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^ڈونٹ$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"categoría con el mismo valor", re.I)),
    ),
    "ar": (
        (re.compile(r"Enter at least %\(length\)s characters", re.I), re.compile(r"حرف %\(length\)s على الأقل", re.I)),
        (re.compile(r"^Frecuencia absoluta$", re.I), re.compile(r"التردد المطلق")),
        (re.compile(r"^Personas distintas$", re.I), re.compile(r"أشخاص مميزون")),
        (re.compile(r"^Población denominadora$", re.I), re.compile(r"السكان القاسم")),
        (re.compile(r"^Grupo de localización$", re.I), re.compile(r"مجموعة الموقع")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^دونات$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"شجاعة")),
    ),
    "id": (
        (re.compile(r"^circular$", re.I), re.compile(r"^pai$", re.I)),
        (re.compile(r"barras? agrupadas", re.I), re.compile(r"\b(?:bar dikelompokkan|mengelompokkan bar)\b", re.I)),
        (re.compile(r"tasa|rate", re.I), re.compile(r"\btarif\w*", re.I)),
        (re.compile(r"Segi.*Doll", re.I), re.compile(r"\bboneka\b", re.I)),
        (re.compile(r"cada barra", re.I), re.compile(r"\b100\s*%\s+a\s+dan\b", re.I)),
        (re.compile(r"Personas distintas", re.I), re.compile(r"Orang yang berbeda")),
        (re.compile(r"^Grupo de localización$", re.I), re.compile(r"\bsitus\b", re.I)),
        (re.compile(r"^Sexo$", re.I), re.compile(r"^Seks$")),
        (re.compile(r"^Anillo$", re.I), re.compile(r"^Donat$")),
        (re.compile(r"categoría con el mismo valor", re.I), re.compile(r"keberanian")),
    ),
}


def placeholders(text):
    return sorted(PLACEHOLDER.findall(text))


def looks_like_untranslated_spanish(source, target):
    """Catch exact Spanish leftovers while allowing shared technical names/cognates."""
    return bool(source and source == target and SPANISH_ONLY_COPY.search(source))


def looks_like_untranslated_english(locale, source, target):
    """Catch exact English fallback copy in non-Latin draft locales."""
    ranges = NON_LATIN_RANGES.get(locale)
    if not ranges or not source or target != source:
        return False
    if source in ENGLISH_COPY_EXCEPTIONS.get(locale, set()):
        return False
    return bool(
        any(character.isalpha() for character in source)
        and not any(start <= ord(character) <= end for start, end in ranges for character in target)
    )


def semantic_translation_issues(locale, source, target):
    """Catch selected high-risk chart/stat false friends and untranslated fragments."""
    issues = []
    if re.search(r"\bRNC\b", source or "") and re.search(
        r"\b(?:NCR|RCN)\b|СРН|РНК", target or "", re.I
    ):
        issues.append("sigla institucional RNC alterada")
    for source_pattern, target_pattern in SEMANTIC_RISKS.get(locale, ()):
        if source_pattern.search(source or "") and target_pattern.search(target or ""):
            issues.append("posible falso amigo o fragmento inglés sin traducir")
    return issues


def catalog_entries(path):
    catalog = polib.pofile(str(path), check_for_duplicates=True)
    return catalog, {entry.msgid: entry for entry in catalog if entry.msgid}


def audit_drafts():
    errors = []
    source_catalogs = {}
    for domain in DOMAINS:
        source_path = LOCALE_ROOT / "en/LC_MESSAGES" / f"{domain}.po"
        source_catalogs[domain] = catalog_entries(source_path)

    report = []
    for locale in DRAFTS:
        for domain in DOMAINS:
            path = LOCALE_ROOT / locale / "LC_MESSAGES" / f"{domain}.po"
            if not path.is_file():
                errors.append(f"{locale}/{domain}: falta el catálogo")
                continue
            catalog, entries = catalog_entries(path)
            _source, source_entries = source_catalogs[domain]
            if entries.keys() != source_entries.keys():
                missing = source_entries.keys() - entries.keys()
                extra = entries.keys() - source_entries.keys()
                errors.append(f"{locale}/{domain}: inventario distinto (faltan {len(missing)}, sobran {len(extra)})")
            plural_count_match = re.search(r"nplurals\s*=\s*(\d+)", catalog.metadata.get("Plural-Forms", ""))
            plural_count = int(plural_count_match.group(1)) if plural_count_match else 0
            for message, source_entry in source_entries.items():
                entry = entries.get(message)
                if entry is None:
                    continue
                if "fuzzy" not in entry.flags:
                    errors.append(f"{locale}/{domain}: entrada no marcada fuzzy: {message[:90]!r}")
                if entry.msgid_plural:
                    forms = [entry.msgstr_plural.get(index, "") for index in range(plural_count)]
                    if not plural_count or any(not value.strip() for value in forms):
                        errors.append(f"{locale}/{domain}: formas plurales incompletas: {message[:90]!r}")
                    targets = forms
                else:
                    targets = [entry.msgstr]
                if not entry.msgid_plural and not entry.msgstr.strip():
                    errors.append(f"{locale}/{domain}: traducción vacía: {message[:90]!r}")
                for target in targets:
                    if not target.strip():
                        continue
                    if looks_like_untranslated_spanish(message, target):
                        errors.append(
                            f"{locale}/{domain}: posible texto fuente español sin traducir: {message[:90]!r}"
                        )
                    if looks_like_untranslated_english(
                        locale, source_entry.msgstr or source_entry.msgid, target
                    ):
                        errors.append(
                            f"{locale}/{domain}: posible texto inglés de referencia sin traducir: {message[:90]!r}"
                        )
                    for issue in semantic_translation_issues(locale, message, target):
                        errors.append(f"{locale}/{domain}: {issue}: {message[:90]!r}")

                expected = placeholders(source_entry.msgid)
                targets = entry.msgstr_plural.values() if entry.msgid_plural else (entry.msgstr,)
                for target in targets:
                    if placeholders(target) != expected:
                        errors.append(f"{locale}/{domain}: placeholders distintos: {message[:90]!r}")
                        break

            compiled = path.with_suffix(".mo")
            if compiled.exists():
                errors.append(f"{locale}/{domain}: catálogo inactivo compilado ({compiled.relative_to(ROOT)})")
            report.append((locale, domain, len(entries), sum("fuzzy" in entry.flags for entry in entries.values())))

    for locale, domain, count, fuzzy in report:
        print(f"{locale}/{domain}: {count} entradas, {fuzzy} fuzzy, no compilado")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(audit_drafts())
