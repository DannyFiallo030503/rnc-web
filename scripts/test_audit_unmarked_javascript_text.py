"""Tests for direct user-visible JavaScript literal detection."""

import unittest

from scripts.audit_unmarked_javascript_text import find_unmarked_user_text


class UnmarkedJavaScriptTextAuditTests(unittest.TestCase):
    def test_visible_dom_and_accessibility_literals_are_detected(self):
        source = '''
node.textContent = "Offline";
button.setAttribute("aria-label", `Open menu`);
input.setCustomValidity('Required');
new Option("Choose one", "");
'''
        findings = find_unmarked_user_text(source)
        self.assertEqual(
            [value for _line, value in findings],
            ["Offline", "Open menu", "Required", "Choose one"],
        )

    def test_gettext_calls_and_empty_dom_resets_are_ignored(self):
        source = '''
node.textContent = t("Offline");
node.textContent = "";
button.setAttribute("aria-label", label);
'''
        self.assertEqual(find_unmarked_user_text(source), [])


if __name__ == "__main__":
    unittest.main()
