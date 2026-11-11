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

    def test_admin_labels_and_static_notice_context_are_detected(self):
        findings = self.scan(
            'from django.contrib import admin\n'
            'from django.contrib.admin import AdminSite\n'
            'class Site(AdminSite):\n'
            ' site_header = "Support administration"\n'
            ' @admin.display(description="Roles")\n'
            ' def role_label(self, obj):\n'
            '  return "Public reader"\n'
            'class Actions:\n'
            ' def get_action_choices(self):\n'
            '  return [(value, label if value else "Choose an action") for value, label in choices]\n'
            'TemplateView.as_view(extra_context={"heading": "Password saved", "intro": "Your password changed."})\n'
        )
        self.assertEqual(len(findings), 6)
        self.assertTrue(any("Support administration" in finding for finding in findings))
        self.assertTrue(any("Roles" in finding for finding in findings))
        self.assertTrue(any("Public reader" in finding for finding in findings))
        self.assertTrue(any("Choose an action" in finding for finding in findings))
        self.assertTrue(any("Password saved" in finding for finding in findings))

    def test_localized_admin_labels_and_notices_are_accepted(self):
        findings = self.scan(
            'from django.utils.translation import gettext_lazy as _\n'
            'from django.contrib.admin import AdminSite\n'
            'class Site(AdminSite):\n'
            ' site_header = _("Support administration")\n'
            'TemplateView.as_view(extra_context={"heading": _("Password saved")})\n'
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
