"""Find direct user-visible JavaScript literals that bypass gettext.

This intentionally narrow source audit checks common DOM, accessibility,
browser-validation, dialog, and option sinks. It complements the marked-message
catalog checker and cannot infer strings passed through arbitrary variables.
"""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
JS_ROOT = ROOT / "static" / "js"
DIRECT_SINKS = (
    re.compile(
        r"\.(?:textContent|innerText|innerHTML|title|placeholder)\s*=\s*"
        r"(?P<quote>['\"`])(?P<text>.*?)(?P=quote)", re.S
    ),
    re.compile(
        r"\.setAttribute\(\s*['\"](?:aria-label|aria-description|title|placeholder)"
        r"['\"]\s*,\s*(?P<quote>['\"`])(?P<text>.*?)(?P=quote)", re.S
    ),
    re.compile(
        r"new\s+Option\(\s*(?P<quote>['\"])(?P<text>.*?)(?P=quote)", re.S
    ),
    re.compile(
        r"\.(?:setCustomValidity)\(\s*(?P<quote>['\"`])(?P<text>.*?)(?P=quote)", re.S
    ),
    re.compile(
        r"\b(?:alert|confirm|prompt)\(\s*(?P<quote>['\"`])(?P<text>.*?)(?P=quote)", re.S
    ),
)


def find_unmarked_user_text(source):
    findings = set()
    for pattern in DIRECT_SINKS:
        for match in pattern.finditer(source):
            value = match.group("text")
            if not value.strip():
                continue
            line = source.count("\n", 0, match.start()) + 1
            findings.add((line, value))
    return sorted(findings)


def scan(root=JS_ROOT):
    findings = []
    for path in sorted(Path(root).rglob("*.js")):
        if "vendor" in path.parts or path.name.endswith(".min.js"):
            continue
        source = path.read_text(encoding="utf-8")
        for line, value in find_unmarked_user_text(source):
            findings.append((path, line, value))
    return findings


def main():
    findings = scan()
    if findings:
        for path, line, value in findings:
            print(f"{path.relative_to(ROOT)}:{line}: texto literal en destino visible: {value!r}")
        print(f"Total: {len(findings)} posibles textos sin marcar", file=sys.stderr)
        return 1
    files = sum(
        1 for path in JS_ROOT.rglob("*.js")
        if "vendor" not in path.parts and not path.name.endswith(".min.js")
    )
    print(
        f"OK: {files} archivos JavaScript revisados; "
        "sin literales directos en destinos visibles inspeccionados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
