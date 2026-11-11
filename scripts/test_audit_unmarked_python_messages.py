"""Tests for the user-facing Python message audit."""

import tempfile
import unittest
from pathlib import Path

from scripts.audit_unmarked_python_messages import scan_paths


class UnmarkedPythonMessageAuditTests(unittest.TestCase):
    def scan(self, content):
        with tempfile.TemporaryDirectory(prefix="rnc-python-message-audit-") as directory:
            path = Path(directory) / "sample.py"
            path.write_text(content, encoding="utf-8")
            return scan_paths([path])

    def test_unmarked_response_and_form_errors_are_detected(self):
        findings = self.scan(
            'HttpResponse("Try again")\nform.add_error(None, "Invalid value")\n'
        )
        self.assertEqual(len(findings), 2)
        self.assertIn("Try again", findings[0])
        self.assertIn("Invalid value", findings[1])

    def test_translated_messages_and_non_message_fields_are_ignored(self):
        findings = self.scan(
            'HttpResponse(_("Reintente"))\n'
            'form.add_error("field_name", None)\n'
            'messages.error(request, _("Falló"))\n'
        )
        self.assertEqual(findings, [])

    def test_interpolated_raw_exception_is_detected(self):
        findings = self.scan('raise ValueError(f"Row {number}: invalid data")\n')
        self.assertEqual(len(findings), 1)
        self.assertIn("invalid data", findings[0])


if __name__ == "__main__":
    unittest.main()
