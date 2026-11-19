"""Tests for translation coverage of cold-start service-worker messages."""

import unittest

from scripts.audit_service_worker_fallbacks import (
    validate_fallback_messages,
    validate_language_change_sync_guard,
    validate_language_message_queue,
    validate_language_revision_guard,
    validate_offline_language_precedence,
)


class ServiceWorkerFallbackAuditTests(unittest.TestCase):
    def test_active_locale_fallbacks_match_catalog_values(self):
        expected = {"en": "The offline query is not available yet.", "es": "La consulta no está disponible."}
        self.assertEqual(validate_fallback_messages(dict(expected), expected), [])

    def test_missing_locale_or_changed_translation_fails_closed(self):
        expected = {"en": "Offline query unavailable.", "es": "Consulta no disponible."}
        failures = validate_fallback_messages({"en": "Offline"}, expected)
        self.assertEqual(len(failures), 3)
        self.assertTrue(any("distintos" in failure for failure in failures))
        self.assertTrue(any("en:" in failure for failure in failures))
        self.assertTrue(any("es:" in failure for failure in failures))

    def test_offline_device_language_precedes_stale_cookie(self):
        source = "const language = validLanguage(requested) ? requested : saved || cookie || browser;"
        self.assertEqual(validate_offline_language_precedence(source), [])

    def test_stale_cookie_cannot_override_offline_selection(self):
        source = "const language = validLanguage(requested) ? requested : cookie || saved || browser;"
        self.assertTrue(validate_offline_language_precedence(source))

    def test_submitted_locale_cannot_be_overwritten_by_delayed_page_sync(self):
        source = (
            "let languageChangePending = false; "
            "const syncLanguage = () => languageChangePending ? Promise.resolve(false) : postLanguage(document.documentElement.lang); "
            "languageChangePending = true; await postLanguage(selected);"
        )
        self.assertEqual(validate_language_change_sync_guard(source), [])

    def test_missing_pending_locale_guard_is_reported(self):
        self.assertTrue(validate_language_change_sync_guard(
            "const syncLanguage = () => postLanguage(document.documentElement.lang);"
        ))

    def test_worker_serializes_language_cache_writes(self):
        source = (
            "let languageMessageQueue = Promise.resolve(); "
            "const saveLanguage = languageMessageQueue.then(() => caches.open(CACHE).then(async cache => {})); "
            "languageMessageQueue = saveLanguage.catch(() => {}); event.waitUntil(saveLanguage);"
        )
        self.assertEqual(validate_language_message_queue(source), [])

    def test_unqueued_worker_language_write_is_reported(self):
        self.assertTrue(validate_language_message_queue(
            "event.waitUntil(caches.open(CACHE).then(async cache => {}));"
        ))

    def test_worker_rejects_stale_language_revision(self):
        source = (
            "const revision = Number.isSafeInteger(data.revision) && data.revision >= 0 ? data.revision : 0; "
            "if (revision < savedRevision) return; "
            "cache.put(languageRevisionKey(), new Response(String(revision)));"
        )
        self.assertEqual(validate_language_revision_guard(source), [])

    def test_missing_worker_revision_guard_is_reported(self):
        self.assertTrue(validate_language_revision_guard(
            "cache.put(languageKey(), new Response(language));"
        ))


if __name__ == "__main__":
    unittest.main()
