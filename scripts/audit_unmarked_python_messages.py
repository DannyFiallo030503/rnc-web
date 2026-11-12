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
ADMIN_SITE_LABELS = {"site_header", "site_title", "index_title"}
TEMPLATE_CONTEXT_LABELS = {"heading", "intro", "submit_label", "title"}
FIELD_TEXT_KEYWORDS = {
    "label", "help_text", "verbose_name", "verbose_name_plural", "error_messages"
}
WIDGET_TEXT_ATTRIBUTES = {
    "alt", "aria-label", "data-label", "data-rule-message", "placeholder", "title"
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


def _literal_string(expression):
    return isinstance(expression, ast.Constant) and isinstance(expression.value, str)


def _has_admin_display_decorator(node):
    return any(
        isinstance(decorator, ast.Call)
        and _callee_name(decorator.func) == "admin.display"
        for decorator in node.decorator_list
    )


def _admin_translation_findings(tree, source, path):
    """Check Django admin labels and static template contexts, which are UI sinks."""
    findings = []

    def add(node, expression, localized_nodes=()):
        if id(expression) in localized_nodes:
            return
        if _is_localized(expression) or not _literal_string(expression):
            return
        text = expression.value.strip()
        if (
            sum(character.isalpha() for character in text) < 2
            or (text.isidentifier() and text.islower())
        ):
            return
        snippet = ast.get_source_segment(source, expression) or repr(text)
        findings.append(
            f"{path}:{node.lineno}: rótulo admin/contexto visible sin gettext: {snippet}"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            is_admin_site = any(
                _callee_name(base).split(".")[-1] == "AdminSite" for base in node.bases
            )
            if is_admin_site:
                for statement in node.body:
                    if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                        continue
                    targets = (
                        statement.targets
                        if isinstance(statement, ast.Assign)
                        else [statement.target]
                    )
                    value = statement.value
                    if any(
                        isinstance(target, ast.Name) and target.id in ADMIN_SITE_LABELS
                        for target in targets
                    ):
                        add(statement, value)

        if isinstance(node, ast.FunctionDef) and _has_admin_display_decorator(node):
            localized_nodes = {
                id(part)
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and _callee_name(call.func).split(".")[-1] in TRANSLATION_CALLS
                for part in ast.walk(call)
            }
            for statement in node.body:
                for result in ast.walk(statement):
                    if isinstance(result, ast.Constant) and isinstance(result.value, str):
                        add(node, result, localized_nodes)

        if isinstance(node, ast.Call):
            name = _callee_name(node.func)
            if name == "admin.display":
                for keyword in node.keywords:
                    if keyword.arg == "description":
                        add(node, keyword.value)
            if name.endswith(".as_view"):
                for keyword in node.keywords:
                    if keyword.arg != "extra_context" or not isinstance(keyword.value, ast.Dict):
                        continue
                    for key, value in zip(keyword.value.keys, keyword.value.values):
                        if _literal_string(key) and key.value in TEMPLATE_CONTEXT_LABELS:
                            add(node, value)

        if isinstance(node, ast.FunctionDef) and node.name == "get_action_choices":
            for expression in ast.walk(node):
                if isinstance(expression, ast.IfExp):
                    add(expression, expression.body)
                    add(expression, expression.orelse)

    return findings


def _field_translation_findings(tree, source, path):
    """Check labels, help, choices and validation copy attached to Django fields."""
    findings = []
    # Migration files are frozen database-state snapshots, not live UI source.
    if "migrations" in Path(path).parts:
        return findings

    def add(node, expression):
        if _is_localized(expression):
            return
        if _literal_string(expression) and expression.value.strip():
            snippet = ast.get_source_segment(source, expression) or repr(expression.value)
            findings.append(
                f"{path}:{node.lineno}: texto visible de campo sin gettext: {snippet}"
            )

    def dictionary_values(expression):
        if isinstance(expression, ast.Dict):
            return zip(expression.keys, expression.values)
        return ()

    def choice_labels(expression):
        if not isinstance(expression, (ast.List, ast.Tuple)):
            return
        for option in expression.elts:
            if isinstance(option, (ast.List, ast.Tuple)) and len(option.elts) >= 2:
                yield option.elts[1]

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = _callee_name(node.func).split(".")[-1]
            if callee == "update" and node.args and isinstance(node.args[0], ast.Dict):
                receiver = _callee_name(node.func.value).lower()
                for key, value in dictionary_values(node.args[0]):
                    if not _literal_string(key):
                        continue
                    if key.value in WIDGET_TEXT_ATTRIBUTES and "attrs" in receiver:
                        add(node, value)
                    elif key.value in FIELD_TEXT_KEYWORDS and "error_messages" in receiver:
                        add(node, value)
            if not callee.endswith("Field"):
                continue
            for keyword in node.keywords:
                if keyword.arg in FIELD_TEXT_KEYWORDS:
                    values = (
                        [value for _key, value in dictionary_values(keyword.value)]
                        if keyword.arg == "error_messages"
                        else [keyword.value]
                    )
                    for value in values:
                        add(node, value)
                elif keyword.arg == "choices":
                    for value in choice_labels(keyword.value):
                        add(node, value)
                elif keyword.arg == "widget" and isinstance(keyword.value, ast.Call):
                    for widget_keyword in keyword.value.keywords:
                        if widget_keyword.arg != "attrs":
                            continue
                        for key, value in dictionary_values(widget_keyword.value):
                            if _literal_string(key) and key.value in WIDGET_TEXT_ATTRIBUTES:
                                add(node, value)

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in {"label", "help_text"}:
                    add(node, value)
                elif (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "error_messages"
                ):
                    add(node, value)
                elif (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == "attrs"
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value in WIDGET_TEXT_ATTRIBUTES
                ):
                    add(node, value)

    return findings


def scan_paths(paths):
    findings = []
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            findings.append(f"{path}: no se pudo auditar Python: {error}")
            continue
        try:
            display_path = path.relative_to(ROOT)
        except ValueError:
            display_path = path
        findings.extend(_admin_translation_findings(tree, source, display_path))
        findings.extend(_field_translation_findings(tree, source, display_path))
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
