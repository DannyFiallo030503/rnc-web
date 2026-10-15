"""Regression coverage for the public/admin boundary using synthetic accounts."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(DEBUG=True)
class AccessAndNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "Temporary-test-password-27!"
        users = get_user_model().objects
        cls.reader = users.create_user("test_reader", password=cls.password)
        cls.staff = users.create_user("test_staff", password=cls.password, is_staff=True)
        cls.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="auth"))
        cls.support = users.create_user("test_support", password=cls.password, is_staff=True)
        cls.support.groups.add(Group.objects.get(name="superadmin"))
        cls.root = users.create_superuser("test_root", password=cls.password)

    def test_public_pages_work_without_login(self):
        for url in ("/", "/acceso/", "/consulta-sintetica/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'href="/administracion/cortes/"')
                self.assertNotContains(response, 'href="/admin/"')

    def test_anonymous_admin_access_requires_login(self):
        self.assertRedirects(self.client.get("/administracion/cortes/"),
                             "/acceso/?next=/administracion/cortes/")
        self.assertRedirects(self.client.get("/admin/"), "/admin/login/?next=/admin/")

    def test_reader_and_ordinary_staff_cannot_open_admin(self):
        for user in (self.reader, self.staff):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                blocked = self.client.get("/administracion/cortes/")
                self.assertEqual(blocked.status_code, 403)
                self.assertNotContains(blocked, "Resumen de cortes", status_code=403)
                self.assertEqual(self.client.get("/admin/auth/user/").status_code, 302)
                self.assertNotContains(self.client.get("/"), 'href="/administracion/cortes/"')
                self.assertNotContains(self.client.get("/"), 'href="/admin/"')

    def test_support_and_superuser_can_manage_users(self):
        for user in (self.support, self.root):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get("/administracion/cortes/").status_code, 200)
                self.assertEqual(self.client.get("/admin/auth/user/").status_code, 200)
                self.assertContains(self.client.get("/"), 'href="/administracion/cortes/"')

    def test_support_without_staff_cannot_manage_accounts(self):
        self.support.is_staff = False
        self.support.save(update_fields=["is_staff"])
        self.client.force_login(self.support)
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 200)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 302)
        self.assertNotContains(self.client.get("/"), 'href="/admin/"')

    def test_role_revocation_takes_effect_on_next_request(self):
        self.client.force_login(self.support)
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 200)
        self.support.groups.clear()
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 403)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 302)

    def test_deactivation_ends_access(self):
        self.client.force_login(self.support)
        self.support.is_active = False
        self.support.save(update_fields=["is_active"])
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_login_redirects_match_role(self):
        for user, destination in ((self.reader, "/"), (self.support, "/administracion/cortes/")):
            self.client.logout()
            with self.subTest(user=user.username):
                response = self.client.post(reverse("public_site:login"),
                                            {"username": user.username, "password": self.password})
                self.assertRedirects(response, destination)

    def test_login_rejects_external_redirect(self):
        response = self.client.post("/acceso/", {"username": self.support.username,
                                    "password": self.password, "next": "https://example.invalid/"})
        self.assertRedirects(response, "/administracion/cortes/")

    def test_failed_login_preserves_username_and_generic_error(self):
        response = self.client.post("/acceso/", {"username": "test_reader", "password": "wrong"})
        self.assertContains(response, 'value="test_reader"')
        self.assertContains(response, 'aria-describedby="login-error"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_year_filter_is_not_discarded_as_integer(self):
        from analytics.demo import load_rows
        rows = load_rows()
        year = min(row["period"] for row in rows)
        expected_tumors = sum(row["tumor_count"] for row in rows if row["period"] == year)
        response = self.client.get("/consulta-sintetica/", {"year": str(year), "unit": "persons"})
        self.assertEqual(response.context["filters"]["year"], str(year))
        self.assertEqual(response.context["data"]["summary"]["tumors"], expected_tumors)
        self.assertContains(response, "tasas de personas distintas")

    def test_unknown_filters_are_safely_normalized(self):
        response = self.client.get("/consulta-sintetica/", {
            "year": "unknown", "unit": "unknown", "measure": "unknown", "territory": "unknown",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filters"]["year"], "")
        self.assertEqual(response.context["filters"]["unit"], "tumors")
        self.assertEqual(response.context["filters"]["measure"], "crude")

    def test_login_and_logout_require_csrf_and_logout_is_post(self):
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post("/acceso/", {}).status_code, 403)
        browser.force_login(self.support)
        self.assertEqual(browser.get("/salir/").status_code, 405)
        self.assertEqual(browser.post("/salir/").status_code, 403)
        browser.get("/administracion/cortes/")
        token = browser.cookies["csrftoken"].value
        response = browser.post("/salir/", {"csrfmiddlewaretoken": token})
        self.assertRedirects(response, "/")
        self.assertEqual(browser.get("/administracion/cortes/").status_code, 302)

    @override_settings(DEBUG=False)
    def test_synthetic_data_remains_local(self):
        self.assertEqual(self.client.get("/consulta-sintetica/").status_code, 404)

    def test_backend_management_can_create_synthetic_account(self):
        self.client.force_login(self.support)
        response = self.client.post("/admin/auth/user/add/", {
            "username": "created_by_support", "password1": self.password,
            "password2": self.password, "usable_password": "true", "_save": "Guardar",
        })
        self.assertEqual(response.status_code, 302)
        account = get_user_model().objects.get(username="created_by_support")
        self.assertTrue(account.check_password(self.password))
        self.assertFalse(account.is_superuser)
        self.assertEqual(self.client.get(f"/admin/auth/user/{account.pk}/change/").status_code, 200)
