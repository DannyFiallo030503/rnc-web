"""Build hash-pinned, isolated .mo catalogs for explicitly enabled draft preview."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import sys

import polib

from django.utils.translation.trans_real import to_locale

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PLACEHOLDER = re.compile(r"%\(([^)]+)\)[#0 +\-]?(?:\d+)?(?:\.\d+)?[diouxXeEfFgGcrsa]")


def compile_translation_preview(output_dir):
    from config.languages import PRIORITY_LANGUAGES

    output_dir = Path(output_dir).resolve()
    production_locale_root = (ROOT / "locale").resolve()
    if output_dir == production_locale_root or production_locale_root in output_dir.parents:
        raise ValueError("La vista previa debe compilarse fuera de locale/ de producción.")

    sources = []
    for code, _english, _native, active in PRIORITY_LANGUAGES:
        if active:
            continue
        for domain in ("django", "djangojs"):
            source = ROOT / "locale" / code / "LC_MESSAGES" / f"{domain}.po"
            if not source.is_file():
                raise FileNotFoundError(f"Falta el catálogo de borrador {source.relative_to(ROOT)}")
            catalog = polib.pofile(str(source), check_for_duplicates=True)
            entries = [entry for entry in catalog if entry.msgid and not entry.obsolete]
            plural_match = re.search(
                r"nplurals\s*=\s*(\d+)", catalog.metadata.get("Plural-Forms", "")
            )
            plural_count = int(plural_match.group(1)) if plural_match else 0
            invalid_entry = False
            for entry in entries:
                if entry.msgid_plural:
                    if not plural_count:
                        invalid_entry = True
                        break
                    targets = [
                        entry.msgstr_plural.get(index, "")
                        for index in range(plural_count)
                    ]
                    if any(not target.strip() for target in targets):
                        invalid_entry = True
                        break
                else:
                    targets = [entry.msgstr]
                    if not entry.msgstr.strip():
                        invalid_entry = True
                        break
                expected_placeholders = sorted(PLACEHOLDER.findall(entry.msgid))
                if any(
                    sorted(PLACEHOLDER.findall(target)) != expected_placeholders
                    for target in targets
                ):
                    invalid_entry = True
                    break
            if not entries or invalid_entry:
                raise ValueError(
                    f"El catálogo {source.relative_to(ROOT)} tiene traducciones vacías, "
                    "formas plurales incompletas o placeholders incompatibles."
                )
            sources.append((code, domain, source, catalog))

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    records = {}
    with tempfile.TemporaryDirectory(prefix="rnc-locale-preview-") as temporary:
        stage = Path(temporary)
        for code, domain, source, catalog in sources:
            # Fuzzy entries are included only in this opt-in preview artifact.
            preview = polib.POFile()
            preview.metadata = dict(catalog.metadata)
            preview.metadata_is_fuzzy = catalog.metadata_is_fuzzy
            for entry in catalog:
                if entry.obsolete:
                    continue
                copied = polib.POEntry(
                    msgid=entry.msgid,
                    msgstr=entry.msgstr,
                    msgid_plural=entry.msgid_plural,
                    msgstr_plural=dict(entry.msgstr_plural),
                    msgctxt=entry.msgctxt,
                    flags=[flag for flag in entry.flags if flag != "fuzzy"],
                )
                preview.append(copied)
            relative_mo = Path(to_locale(code)) / "LC_MESSAGES" / f"{domain}.mo"
            staged_mo = stage / relative_mo
            staged_mo.parent.mkdir(parents=True, exist_ok=True)
            preview.save_as_mofile(str(staged_mo))
            mo_bytes = staged_mo.read_bytes()
            records[f"{code}/{domain}"] = {
                "source": source.relative_to(ROOT).as_posix(),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "entries": len([entry for entry in catalog if entry.msgid and not entry.obsolete]),
                "fuzzy_entries_included": sum("fuzzy" in entry.flags for entry in catalog if entry.msgid and not entry.obsolete),
                "mo": relative_mo.as_posix(),
                "mo_sha256": hashlib.sha256(mo_bytes).hexdigest(),
            }

        output_dir.mkdir(parents=True, exist_ok=True)
        for record in records.values():
            staged_mo = stage / record["mo"]
            target = output_dir / record["mo"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(staged_mo.read_bytes())
        manifest = {
            "schema": "rnc-translation-preview-v1",
            "warning": "Machine-generated draft translations; not approved for interpreting statistics.",
            "catalogs": records,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "locale-preview",
        help="destino aislado de los catálogos .mo de borrador (default: locale-preview/)",
    )
    args = parser.parse_args(argv)
    manifest = compile_translation_preview(args.output_dir)
    print(
        f"Vista previa compilada: {len(manifest['catalogs'])} catálogos, "
        f"{sum(item['entries'] for item in manifest['catalogs'].values())} entradas; "
        f"manifiesto {args.output_dir.resolve() / 'manifest.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
