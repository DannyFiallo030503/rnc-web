"""Create explicitly unapproved gettext drafts for prioritized locales.

This opt-in utility sends interface/catalog text only to Google Translate's
unofficial public endpoint. Generated messages are always marked fuzzy and
must never be activated or published without qualified human review.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.languages import PRIORITY_LANGUAGES

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
CHUNK_SIZE = 20
LOCALE_TARGETS = {
    "zh-hans": ("zh-CN", 1, "nplurals=1; plural=0;"),
    "hi": ("hi", 2, "nplurals=2; plural=(n != 1);"),
    "ar": ("ar", 6, "nplurals=6; plural=(n==0?0:n==1?1:n==2?2:n%100>=3&&n%100<=10?3:n%100>=11&&n%100<=99?4:5);"),
    "fr": ("fr", 2, "nplurals=2; plural=(n > 1);"),
    "bn": ("bn", 2, "nplurals=2; plural=(n != 1);"),
    "pt-br": ("pt", 2, "nplurals=2; plural=(n != 1);"),
    "id": ("id", 1, "nplurals=1; plural=0;"),
    "ur": ("ur", 2, "nplurals=2; plural=(n != 1);"),
    "ru": ("ru", 3, "nplurals=3; plural=(n%10==1&&n%100!=11?0:n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?1:2);"),
}
PROTECTED = re.compile(
    r"%(?:\([^)]+\))?[#0 +\-]?(?:\d+)?(?:\.\d+)?[diouxXeEfFgGcrsa%]"
    r"|https?://[^\s<>\"']+|</?[A-Za-z][^>]*>"
)


def protect(text, prefix):
    tokens = []

    def add_token(value):
        # Google Translate occasionally drops the old numeric-only X...X
        # marker, especially in Russian. Underscore-delimited sentinels survive
        # the provider more consistently and remain easy to recognize.
        token = f"__RNC_PH_{len(tokens)}__"
        tokens.append((token, value))
        return token

    def replace(match):
        return add_token(match.group(0))

    leading = text[:len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    content = text[len(leading):len(text) - len(trailing) if trailing else len(text)]
    protected = PROTECTED.sub(replace, content)
    if leading:
        protected = add_token(leading) + protected
    if trailing:
        protected += add_token(trailing)
    return protected, tokens


def restore(text, tokens, prefix):
    text = text.strip()
    for token, original in tokens:
        if text.count(token) != 1:
            raise ValueError(f"Placeholder perdido o duplicado: {token}")
        text = text.replace(token, original)
    if re.search(r"__RNC_PH_\d+__", text):
        raise ValueError("Marcador temporal de traducción sin restaurar")
    return text


def translate_batch(texts, target, batch_number):
    prefix = f"T{batch_number}X{len(texts)}"
    protected = []
    token_sets = []
    for index, text in enumerate(texts):
        item, tokens = protect(text, f"{prefix}I{index}")
        protected.append(item)
        token_sets.append((tokens, f"{prefix}I{index}"))
    boundary = "ZZZQSEPQQQ"
    payload = f"\n{boundary}\n".join(protected)
    params = urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": target, "dt": "t", "q": payload})
    request = urllib.request.Request(ENDPOINT + "?" + params, headers={"User-Agent": "rnc-web-translation-draft/1.0"})
    error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = "".join(segment[0] for segment in data[0])
            pieces = translated.split(boundary)
            if len(pieces) != len(texts):
                if len(texts) > 1:
                    midpoint = len(texts) // 2
                    left = translate_batch(texts[:midpoint], target, batch_number * 2 + 1)
                    right = translate_batch(texts[midpoint:], target, batch_number * 2 + 2)
                    return left + right
                pieces = [translated]
            try:
                return [restore(piece, tokens, item_prefix) for piece, (tokens, item_prefix) in zip(pieces, token_sets)]
            except ValueError:
                if len(texts) > 1:
                    midpoint = len(texts) // 2
                    left = translate_batch(texts[:midpoint], target, batch_number * 2 + 1)
                    right = translate_batch(texts[midpoint:], target, batch_number * 2 + 2)
                    return left + right
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Falló la traducción al locale {target}: {error}") from error


def translation_units(entry):
    # The English locale carries interface copy in msgstr for both domains;
    # two legacy JS plural entries have Spanish msgids but English msgstr forms.
    singular = entry.msgstr or entry.msgid
    if not entry.msgid_plural:
        return [singular or entry.msgid]
    plural = entry.msgstr_plural.get(1) or entry.msgid_plural
    return [singular or entry.msgid, plural]


def plural_targets(entry, translated, plural_count):
    if not entry.msgid_plural:
        return translated[0], {}
    singular = translated[0]
    plural = translated[1] if len(translated) > 1 else translated[0]
    if plural_count == 1:
        return singular, {0: singular}
    if plural_count == 2:
        return singular, {0: singular, 1: plural}
    # Arabic requires six gettext forms. These machine suggestions use the
    # translated singular for zero/one and plural for dual/few/many/other;
    # human linguistic review is mandatory before activation.
    if plural_count == 6:
        return singular, {0: singular, 1: singular, 2: plural, 3: plural, 4: plural, 5: plural}
    # Russian uses three gettext forms; translate singular for one and plural
    # suggestions for few/other, leaving morphological review to a human.
    return singular, {0: singular, 1: plural, 2: plural}


def source_catalog(domain):
    return polib.pofile(str(ROOT / "locale/en/LC_MESSAGES" / f"{domain}.po"), check_for_duplicates=True)


def generate_locale(locale, only_missing=False, refresh_plurals=False):
    target, plural_count, plural_formula = LOCALE_TARGETS[locale]
    output_dir = ROOT / "locale" / locale / "LC_MESSAGES"
    output_dir.mkdir(parents=True, exist_ok=True)
    totals = {}
    for domain in ("django", "djangojs"):
        catalog = source_catalog(domain)
        existing_path = output_dir / f"{domain}.po"
        existing = polib.pofile(str(existing_path), check_for_duplicates=True) if only_missing and existing_path.exists() else None
        existing_entries = {entry.msgid: entry for entry in existing if entry.msgid} if existing else {}
        entries = [entry for entry in catalog if entry.msgid]
        units = []
        mapping = []
        for entry in entries:
            old = existing_entries.get(entry.msgid)
            if (only_missing and old and old.msgid_plural == entry.msgid_plural
                    and (old.msgstr or old.msgstr_plural)
                    and not (refresh_plurals and entry.msgid_plural)):
                entry.msgstr = old.msgstr
                entry.msgstr_plural = dict(old.msgstr_plural)
                if "fuzzy" not in entry.flags:
                    entry.flags.append("fuzzy")
                continue
            values = translation_units(entry)
            for value in values:
                units.append(value)
            mapping.append((entry, len(values)))
        translated_units = []
        for start in range(0, len(units), CHUNK_SIZE):
            batch_number = start // CHUNK_SIZE
            translated_units.extend(translate_batch(units[start:start + CHUNK_SIZE], target, batch_number))
            print(f"{locale}/{domain}: {min(start + CHUNK_SIZE, len(units))}/{len(units)} textos", flush=True)
            time.sleep(0.12)

        cursor = 0
        for entry, unit_count in mapping:
            values = translated_units[cursor:cursor + unit_count]
            cursor += unit_count
            entry.msgstr, entry.msgstr_plural = plural_targets(entry, values, plural_count)
            entry.msgstr_plural = {index: entry.msgstr_plural.get(index, "") for index in range(plural_count)} if entry.msgid_plural else {}
            if "fuzzy" not in entry.flags:
                entry.flags.append("fuzzy")

        catalog.metadata["Language"] = locale
        catalog.metadata["Plural-Forms"] = plural_formula
        catalog.metadata["Last-Translator"] = "Machine translation draft (unreviewed)"
        catalog.metadata["X-Translation-Status"] = "machine-draft-unreviewed"
        catalog.metadata["X-Content-Review"] = "Human linguistic review required; institutional claims require RNC review"
        catalog.save(str(output_dir / f"{domain}.po"))
        totals[domain] = len(entries)

    locale_display = next((native for code, _english, native, _active in PRIORITY_LANGUAGES if code == locale), locale)
    readme = (
        f"# {locale_display} — borrador automático\n\n"
        "Catálogos generados automáticamente y no revisados. Todas las entradas conservan `fuzzy`; "
        "este locale no se activa ni se compila. Revisar todos los textos, placeholders, plurales, "
        "formatos, términos médicos e institucionales con especialistas. No publicar afirmaciones "
        "institucionales sin validación del RNC. Ver `TRANSLATIONS.md` para la puerta de salida.\n\n"
        f"Entradas preparadas: django {totals['django']}, djangojs {totals['djangojs']}.\n"
    )
    (ROOT / "locale" / locale / "README.md").write_text(readme, encoding="utf-8")
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("locales", nargs="+", choices=tuple(LOCALE_TARGETS))
    parser.add_argument("--only-missing", action="store_true", help="preserve existing drafts and translate only new entries")
    parser.add_argument("--refresh-plurals", action="store_true", help="retranslate plural entries even with --only-missing")
    args = parser.parse_args()
    for locale in args.locales:
        print(json.dumps({locale: generate_locale(locale, only_missing=args.only_missing, refresh_plurals=args.refresh_plurals)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
