"""Find literal user-facing Python messages that bypass gettext markers.

The audit is deliberately limited to known response/form/message/error sinks.
It complements (and does not replace) template, JavaScript, and browser audits.
"""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("config", "public_site", "analytics")
TRANSLATION_CALLS = {"_", "gettext", "gettext_lazy", "ngettext", "pgettext"}
MESSAGE_SINK_ARGUMENTS = {
    "HttpResponse": 0,
    "HttpResponseBadRequest": 0,
    "HttpResponseForbidden": 0,
    "HttpResponseNotAllowed": 0,
    "HttpResponseNotFound": 0,
    "HttpResponseServerError": 0,
    "ValueError": 0,
    "ValidationError": 0,
    "PermissionDenied": 0,
    "CatalogError": 0,
}


def _callee_name(function):
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        base = _callee_name(function.value)
        return f"{base}.{function.attr}" if base else function.attr
    return ""


def _sink_argument(name):
    if name in MESSAGE_SINK_ARGUMENTS:
        return MESSAGE_SINK_ARGUMENTS[name]
    if name in {"messages.success", "messages.error", "messages.warning", "messages.info"}:
        return 1
    if name == "messages.add_message":
        return 2
    if name.endswith(".add_error"):
        return 1
    return None


def _is_localized(expression):
    return any(
        isinstance(node, ast.Call)
        and _callee_name(node.func).split(".")[-1] in TRANSLATION_CALLS
        for node in ast.walk(expression)
    )


def _contains_user_text(expression):
    if isinstance(expression, ast.Constant):
        return isinstance(expression.value, str) and bool(expression.value.strip())
    if isinstance(expression, ast.JoinedStr):
        return any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and bool(value.value.strip())
            for value in expression.values
        )
    return False


def scan_paths(paths):
    findings = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            findings.append(f"{path}: no se pudo auditar Python: {error}")
            continue
        raised_calls = {
            id(node.exc)
            for node in ast.walk(tree)
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        }
        for node in ast.walk(tree):
            expression = None
            if isinstance(node, ast.Call):
                if id(node) in raised_calls:
                    continue
                index = _sink_argument(_callee_name(node.func))
                if index is not None and len(node.args) > index:
                    expression = node.args[index]
            elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                if _callee_name(node.exc.func).split(".")[-1] in MESSAGE_SINK_ARGUMENTS:
                    if node.exc.args:
                        expression = node.exc.args[0]
            if expression is None or _is_localized(expression) or not _contains_user_text(expression):
                continue
            snippet = ast.get_source_segment(source, expression) or ""
            try:
                display_path = path.relative_to(ROOT)
            except ValueError:
                display_path = path
            findings.append(
                f"{display_path}:{node.lineno}: mensaje visible sin gettext: {snippet}"
            )
    return findings


def main():
    paths = [
        path
        for relative in SCAN_ROOTS
        for path in (ROOT / relative).rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    findings = scan_paths(paths)
    if findings:
        print("\n".join(findings))
        return 1
    print(f"OK: {len(paths)} archivos Python revisados en destinos de mensajes visibles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
