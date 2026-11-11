"""List user-facing template text and attributes not marked for translation.

This is an audit aid, not a completeness proof: runtime-generated values and
JavaScript-owned UI must be reviewed separately.
"""

from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
EXCEPTIONS = ROOT / "scripts/translation_audit_exceptions.json"
TAG = re.compile(r"{%.*?%}", re.S)
VARIABLE = re.compile(r"{{.*?}}", re.S)
MARKED_BLOCK = re.compile(
    r"{%\s*(?:blocktrans|blocktranslate)\b.*?{%\s*end(?:blocktrans|blocktranslate)\s*%}",
    re.S,
)
INTERESTING_ATTRIBUTES = {"alt", "aria-label", "placeholder", "title"}


class TextAudit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []

    def handle_data(self, data):
        self.add(data)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in INTERESTING_ATTRIBUTES and value:
                self.add(value, attribute=name)

    def add(self, value, attribute="text"):
        value = re.sub(r"\s+", " ", value).strip()
        if not value or "{{" in value or "{%" in value:
            return
        if sum(char.isalpha() for char in value) < 2:
            return
        if value.startswith(("{%", "{{")):
            return
        self.items.append((attribute, value))


def main():
    with EXCEPTIONS.open(encoding="utf-8") as source:
        exceptions = json.load(source)
    findings = 0
    reviewed = 0
    unreviewed = 0
    seen = set()
    for path in sorted(TEMPLATES.rglob("*.html")):
        source = path.read_text(encoding="utf-8")
        source = MARKED_BLOCK.sub(" ", source)
        source = TAG.sub(" ", source)
        source = VARIABLE.sub(" ", source)
        parser = TextAudit()
        parser.feed(source)
        unique = sorted(set(parser.items))
        if unique:
            relative = str(path.relative_to(ROOT))
            entry = exceptions.get(relative)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            findings += len(unique)
            seen.add(relative)
            if entry and entry.get("sha256") == digest and entry.get("count") == len(unique):
                reviewed += len(unique)
                print(f"CLASIFICADO {relative}: {len(unique)} — {entry['reason']}")
                continue

            unreviewed += len(unique)
            if entry:
                print(f"EXCEPCIÓN CADUCADA {relative}: actualizar revisión y justificación")
            else:
                print(f"SIN CLASIFICAR {relative}: {len(unique)} cadenas visibles")
            for attribute, value in unique:
                print(f"  [{attribute}] {value}")

    stale = sorted(set(exceptions) - seen)
    for relative in stale:
        print(f"EXCEPCIÓN OBSOLETA {relative}: quitar del manifiesto")
        unreviewed += 1
    print(
        f"Total: {findings} candidatas; {reviewed} clasificadas; "
        f"{unreviewed} pendientes de revisión."
    )
    return 1 if unreviewed else 0


if __name__ == "__main__":
    raise SystemExit(main())
