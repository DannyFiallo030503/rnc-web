"""Nonclinical locale and absolute-session regressions; isolated Django test DB."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, override_settings, RequestFactory
from django.utils.translation import override
from config.public_context import navigation

@override_settings(ROOT_URLCONF="config.urls_admin", PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", MIDDLEWARE=[*settings.MIDDLEWARE, "public_site.middleware.AccountSecurityMiddleware"])
class AbsoluteSessionTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser("session_check", password="LocalSession-2026!", email="session@example.invalid")

    def test_twelve_hours_start_at_login_and_activity_does_not_extend_them(self):
        response = self.client.post("/acceso/", {"username":"session_check", "password":"LocalSession-2026!"})
        self.assertEqual(response.status_code,302)
        session = self.client.session
        opened = session["rnc_login_started_at"]
        expected = datetime.fromtimestamp(opened, timezone.utc) + timedelta(hours=12)
        self.assertLess(abs((session.get_expiry_date()-expected).total_seconds()),1)
        self.client.get("/administracion/usuarios/")
        self.assertEqual(self.client.session["rnc_login_started_at"], opened)
        self.assertLess(abs((self.client.session.get_expiry_date()-expected).total_seconds()),1)

    def test_expired_login_timestamp_cannot_be_kept_alive_by_a_new_cookie(self):
        self.client.force_login(get_user_model().objects.get(username="session_check"))
        session = self.client.session
        session["rnc_login_started_at"] = (datetime.now(timezone.utc)-timedelta(hours=12,seconds=1)).timestamp()
        session.set_expiry(43200)
        session.save()
        response = self.client.get("/administracion/usuarios/")
        self.assertRedirects(response,"/acceso/",fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_legacy_session_without_login_timestamp_requires_new_login(self):
        self.client.force_login(get_user_model().objects.get(username="session_check"))
        session = self.client.session
        session.pop("rnc_login_started_at", None)
        session.save()
        response = self.client.get("/administracion/usuarios/")
        self.assertRedirects(response,"/acceso/",fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id",self.client.session)

    def test_explicit_javascript_locale_wins_over_cookie(self):
        self.client.cookies["rnc_language"]="es"
        response=self.client.get("/jsi18n/?lang=en")
        self.assertEqual(response["Content-Language"],"en")
        self.assertContains(response,"Study population")
        response=self.client.get("/jsi18n/?lang=es")
        self.assertEqual(response["Content-Language"],"es")

class PublicNavigationLocaleTests(SimpleTestCase):
    def test_about_and_its_anchors_are_present_in_both_languages(self):
        request=RequestFactory().get("/el-rnc/")
        request.resolver_match=SimpleNamespace(url_name="about")
        for language,label in [("es","Acerca de"),("en","About")]:
            with override(language):
                context=navigation(request)
                self.assertEqual(str(next(page["label"] for page in context["page_navigation"] if page["name"]=="about")),label)
                self.assertIn("que-hacemos",[section["anchor"] for section in context["section_navigation"]])
