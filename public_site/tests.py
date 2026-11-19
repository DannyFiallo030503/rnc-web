"""Account, access and catalog regressions, independent of clinical fixtures.

Real numerical validation is in scripts/verify_real_data.py; real source flow
checks are in test_real_data.py. The former synthetic positive-flow scenarios
are replaced by those checks rather than accepted by the real importer.
"""

import io

import json

import re

import shutil

import subprocess

import tempfile

from datetime import timedelta

from pathlib import Path

from types import SimpleNamespace

from unittest.mock import patch

from django.contrib.auth import get_user_model

from django.contrib.auth.models import Group, Permission

from django.contrib.auth.tokens import default_token_generator

from django.core import mail

from django.core.cache import cache

from django.core.management import call_command

from django.test import Client, TestCase, SimpleTestCase, override_settings

from django.utils.encoding import force_bytes

from django.utils.http import urlsafe_base64_encode

from .models import AccountMail, AccountPolicy, AuditEvent, Delivery, Publication

from analytics.rnc_aggregation import build_real_aggregate

from analytics.standard import AGE_STANDARD_WEIGHTS

from public_site.aggregate_statistics import DIMENSIONS, results

from public_site import public_portal

from config.settings_public import TEMPLATES as PUBLIC_TEMPLATES

from django.contrib import admin
from django.utils.translation import override as override_language

PASSWORD = "Review-test<> 'Secure-2026!"

class DjangoAdminTranslationTests(SimpleTestCase):
    def test_admin_site_labels_follow_the_active_language(self):
        with override_language("en"):
            self.assertEqual(str(admin.site.site_header), "RNC Cuba · Administration")
            self.assertEqual(str(admin.site.site_title), "RNC administration")
            self.assertEqual(str(admin.site.index_title), "Users and permissions")
        with override_language("es"):
            self.assertEqual(str(admin.site.site_header), "RNC Cuba · Administración")
            self.assertEqual(str(admin.site.site_title), "Administración RNC")
            self.assertEqual(str(admin.site.index_title), "Usuarios y permisos")

    def test_admin_role_labels_translate_known_role_codes(self):
        from .admin import SupportUserAdmin

        account = SimpleNamespace(
            is_superuser=False,
            groups=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(name="operator"),
                    SimpleNamespace(name="publisher"),
                ]
            ),
        )
        with override_language("en"):
            self.assertEqual(
                SupportUserAdmin.account_roles(None, account),
                "Data intake operator, Publication manager",
            )
            account.is_superuser = True
            self.assertEqual(
                SupportUserAdmin.account_roles(None, account), "Support administrator"
            )
        with override_language("es"):
            self.assertEqual(SupportUserAdmin.account_roles(None, account), "Administrador de soporte")


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PortalTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rnc-web-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.override = override_settings(
        PRIVATE_STORAGE_ROOT=Path(self.temporary.name),
        EMAIL_FILE_PATH=Path(self.temporary.name) / "mail",
        PUBLIC_ORIGIN="https://rnc.example.invalid",
        PUBLIC_RELEASE_ROOT=Path(self.temporary.name) / "public-releases",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()
        self.User = get_user_model()
        self.root = self.User.objects.create_superuser(
        "qa_root", email="root@example.invalid", password=PASSWORD,
        first_name="Elena", last_name="García",
        )
        self.reader = self.User.objects.create_user(
        "qa_reader", email="reader@example.invalid", password=PASSWORD
        )
        self.operator = self.User.objects.create_user("qa_operator", password=PASSWORD)
        self.operator.groups.add(Group.objects.get(name="operator"))
        self.publisher = self.User.objects.create_user("qa_publisher", password=PASSWORD)
        self.publisher.groups.add(Group.objects.get(name="publisher"))

    def account_data(self, **updates):
        data = {
        "username": "cuenta_nueva", "first_name": "María José",
        "last_name": "O’Neill-Pérez", "email": "nueva@example.invalid",
        "role": "operator", "is_active": "on", "initial_password": "",
        "confirm_password": PASSWORD,
        }
        data.update(updates)
        return data

    def post_account(self, **updates):
        self.client.force_login(self.root)
        return self.client.post(
        "/administracion/usuarios/nuevo/", self.account_data(**updates)
        )

    def test_public_pages_and_no_redundant_home_button(self):
        for path in ["/", "/el-rnc/", "/consulta/", "/acceso/", "/cuenta/recuperar/"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "sidebar-home")
                self.assertNotContains(r, 'href="/administracion/cortes/"')
                if path in {"/", "/el-rnc/", "/consulta/"}:
                    self.assertContains(r, 'aria-label="Páginas"')

    def test_javascript_translation_catalog_follows_selected_language(self):
        spanish = self.client.get("/jsi18n/")
        self.assertEqual(spanish.status_code, 200)
        self.assertContains(spanish, "Complete este campo.")

        self.client.cookies["rnc_language"] = "en"
        english = self.client.get("/jsi18n/")
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, "Check this box to continue.")
        self.assertContains(english, "The local calculation encountered an error.")
        self.assertContains(english, "categories with the same values")
        self.assertContains(english, "Age-adjusted rate per 100,000")

    @override_settings(ROOT_URLCONF="config.urls_public", DEPLOYMENT_ROLE="public")
    def test_public_worker_uses_public_origin_scope_and_excludes_private_routes(self):
        response = self.client.get("/service-worker.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-store")
        source = response.content.decode()
        for private_prefix in ('"/admin/"', '"/acceso/"', '"/administracion/"', '"/cuenta/"'):
            self.assertIn(private_prefix, source)
        self.assertIn("/paquete-offline.json", source)
        self.assertIn('"/consulta/"', source)
        from django.urls import resolve
        from .public_portal import not_found

        self.assertIs(resolve("/admin/", urlconf="config.urls_public").func, not_found)

    @override_settings(ROOT_URLCONF="config.urls_public", DEPLOYMENT_ROLE="public", TEMPLATES=PUBLIC_TEMPLATES)
    def test_public_admin_entry_is_hidden_until_server_connectivity_is_confirmed(self):
        from html.parser import HTMLParser

        class AdminLinks(HTMLParser):
            links = None

            def __init__(self):
                super().__init__()
                self.links = []

            def handle_starttag(self, tag, attributes):
                attrs = dict(attributes)
                if tag == "a" and "data-admin-web-link" in attrs:
                    self.links.append(attrs)

        for path in ("/", "/el-rnc/", "/consulta/", "/nomencladores/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                parser = AdminLinks()
                parser.feed(response.content.decode())
                self.assertEqual(len(parser.links), 2)
                self.assertTrue(all("hidden" in link for link in parser.links))
                self.assertContains(response, 'data-server-connection="checking"')

        for path in ("/", "/el-rnc/", "/nomencladores/"):
            with self.subTest(path=path, language="en"):
                response = self.client.get(path, {"__rnc_locale": "en"})
                self.assertContains(response, '<html lang="en"')

    def test_install_manifest_starts_at_explorer_and_combined_site_does_not_register_worker(self):
        from django.conf import settings

        manifest = json.loads((Path(settings.BASE_DIR) / "static/pwa/manifest.webmanifest").read_text())
        self.assertEqual(manifest["start_url"], "/consulta/")
        self.assertEqual(manifest["scope"], "/")
        response = self.client.get("/")
        self.assertNotContains(response, "register-service-worker.js")

    def test_coding_nomenclators_explains_missing_authorized_catalog(self):
        response = self.client.get("/nomencladores/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Catálogo oficial aún no disponible")
        self.assertContains(response, "OMS · ICD‑O‑3")
        self.assertContains(response, "IARC · ICCC‑3")
        self.assertContains(response, "ICD‑O‑4")

        self.client.cookies["rnc_language"] = "en"
        english = self.client.get("/nomencladores/")
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, "Cancer code catalogues")
        self.assertContains(english, "No authorized catalogue is available yet")
        self.assertContains(english, "WHO · ICD‑O‑3")

    def test_coding_nomenclators_fails_closed_on_invalid_file(self):
        path = Path(self.temporary.name) / "invalid-catalog.json"
        path.write_text("{not-json", encoding="utf-8")
        with override_settings(RNC_CODING_CATALOG=path):
            response = self.client.get("/nomencladores/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se pudo cargar el catálogo")
        self.assertContains(response, 'role="alert"')

    def test_coding_nomenclators_searches_versioned_file_and_shows_provenance(self):
        path = Path(self.temporary.name) / "catalog.json"
        path.write_text(json.dumps({
            "version": "test-catalog-v1",
            "source": "https://example.invalid/catalog",
            "concepts": [{
                "concept_id": "concept-alpha", "name": "Example concept",
                "description": "Structural test concept description", "language": "es",
                "source": "https://example.invalid/catalog", "license": "Test-only",
                "publication_status": "authorized", "codes": [{
                    "system": "TEST", "edition": "test-edition", "axis": "other",
                    "code": "alpha", "name": "Example entry", "description": "Structural test description",
                    "status": "current", "source": "https://example.invalid/catalog",
                    "license": "Test-only", "relationship": "primary",
                    "relationship_status": "source-declared",
                }, {
                    "system": "TEST", "edition": "test-edition", "axis": "other",
                    "code": "gamma", "name": "Pending relation", "description": "Relation awaiting validation",
                    "status": "current", "source": "https://example.invalid/catalog",
                    "license": "Test-only", "relationship": "exact",
                    "relationship_status": "pending",
                }],
            }, {
                "concept_id": "concept-beta", "name": "Draft concept",
                "description": "Unapproved test concept", "language": "es",
                "source": "https://example.invalid/catalog", "license": "Test-only",
                "publication_status": "draft", "codes": [{
                    "system": "TEST", "edition": "test-edition", "axis": "other",
                    "code": "beta", "name": "Draft entry", "description": "Unapproved test term",
                    "status": "current", "source": "https://example.invalid/catalog",
                    "license": "Test-only", "relationship": "primary",
                    "relationship_status": "source-declared",
                }],
            }],
        }), encoding="utf-8")
        with override_settings(RNC_CODING_CATALOG=path):
            response = self.client.get("/nomencladores/?q=structural")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alpha")
        self.assertContains(response, "Structural test description")
        self.assertContains(response, "Test-only")
        self.assertNotContains(response, "beta")
        self.assertNotContains(response, "gamma")
        validation_output = io.StringIO()
        call_command("validate_coding_catalog", str(path), stdout=validation_output)
        self.assertIn("Catálogo válido", validation_output.getvalue())
        self.assertIn("códigos: 3", validation_output.getvalue())
        self.assertNotIn("alpha", validation_output.getvalue())

    def test_normalized_coding_csv_import_preserves_literal_codes(self):
        from analytics.coding_nomenclators import load_catalog

        csv_path = Path(self.temporary.name) / "normalized.csv"
        output_path = Path(self.temporary.name) / "catalog.json"
        fields = [
            "concept_id", "concept_name", "concept_description", "language",
            "concept_source", "concept_license", "publication_status", "system",
            "edition", "axis", "code", "code_name", "code_description",
            "code_status", "code_source", "code_license", "relationship",
            "relationship_status",
        ]
        base = [
            "example-concept", "Example concept", "Generic test concept", "es",
            "https://example.invalid/test", "Test-only", "draft", "TEST",
            "edition-test", "classification", "0007", "Example code", "Generic test code",
            "current", "https://example.invalid/test", "Test-only", "primary",
            "pending",
        ]
        import csv
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(fields)
            writer.writerow(base)
            writer.writerow([*base[:10], "0010", *base[11:]])

        call_command(
            "import_coding_catalog_csv", str(csv_path), str(output_path),
            catalog_version="test-v1", source="https://example.invalid/catalog",
        )
        catalog = load_catalog(output_path)
        self.assertEqual(catalog["concepts"][0]["codes"][0]["code"], "0007")
        self.assertEqual(catalog["concepts"][0]["codes"][1]["code"], "0010")
        self.assertEqual(len(catalog["concepts"]), 1)

    def test_normalized_coding_csv_import_rejects_inconsistent_concept_metadata(self):
        from django.core.management.base import CommandError
        import csv

        csv_path = Path(self.temporary.name) / "conflicting.csv"
        output_path = Path(self.temporary.name) / "should-not-exist.json"
        fields = [
            "concept_id", "concept_name", "concept_description", "language",
            "concept_source", "concept_license", "publication_status", "system",
            "edition", "axis", "code", "code_name", "code_description",
            "code_status", "code_source", "code_license", "relationship",
            "relationship_status",
        ]
        base = [
            "example-concept", "Example concept", "Generic test concept", "es",
            "https://example.invalid/test", "Test-only", "draft", "TEST",
            "edition-test", "other", "A1", "Example code", "Generic test code",
            "current", "https://example.invalid/test", "Test-only", "primary",
            "pending",
        ]
        conflict = list(base)
        conflict[1] = "Conflicting concept name"
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(fields)
            writer.writerow(base)
            writer.writerow(conflict)

        with self.assertRaisesRegex(CommandError, "metadatos del concepto"):
            call_command(
                "import_coding_catalog_csv", str(csv_path), str(output_path),
                catalog_version="test-v1", source="https://example.invalid/catalog",
            )
        self.assertFalse(output_path.exists())

    def test_anonymous_requires_login_on_every_private_route(self):
        for path in [
            "/administracion/cortes/",
            "/administracion/cortes/00000000-0000-0000-0000-000000000001/",
            "/administracion/usuarios/",
            "/administracion/usuarios/nuevo/",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)

    def test_capability_matrix_enforced_by_backend(self):
        for user, uploads, accounts in [
            (self.reader, 403, 403),
            (self.operator, 200, 403),
            (self.publisher, 200, 403),
            (self.root, 200, 200),
        ]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.client.get("/administracion/cortes/").status_code, uploads
                )
                self.assertEqual(
                    self.client.get("/administracion/usuarios/").status_code, accounts
                )

    def test_old_admin_cannot_bypass_account_policies(self):
        self.assertRedirects(
            self.client.get("/admin/"),
            "/administracion/usuarios/",
            fetch_redirect_response=False,
        )
        self.client.force_login(self.root)
        self.assertEqual(self.client.get("/admin/auth/user/add/").status_code, 404)

    def test_role_revocation_and_deactivation_are_immediate(self):
        self.client.force_login(self.operator)
        self.operator.groups.clear()
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 403)
        self.operator.is_active = False
        self.operator.save()
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 302)

    def test_login_redirects_and_external_next_rejected(self):
        for user, destination in [
            (self.reader, "/"),
            (self.operator, "/administracion/cortes/"),
            (self.root, "/administracion/cortes/"),
        ]:
            self.client.logout()
            r = self.client.post(
                "/acceso/",
                {
                    "username": user.username,
                    "password": PASSWORD,
                    "next": "https://evil.invalid",
                },
            )
            self.assertRedirects(r, destination)

    def test_login_empty_fields_and_generic_invalid_credentials(self):
        r = self.client.post("/acceso/", {})
        self.assertIn("username", r.context["form"].errors)
        self.assertIn("password", r.context["form"].errors)
        r = self.client.post(
            "/acceso/", {"username": self.reader.username, "password": "Incorrecta"}
        )
        self.assertTrue(r.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_and_logout_post(self):
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post("/acceso/", {}).status_code, 403)
        c.force_login(self.root)
        self.assertEqual(c.get("/salir/").status_code, 405)
        self.assertEqual(c.post("/salir/").status_code, 403)
        c.get("/administracion/cortes/")
        token = c.cookies["csrftoken"].value
        self.assertRedirects(
            c.post("/salir/", {"csrfmiddlewaretoken": token}), "/acceso/"
        )

    def test_create_invited_account_persists_role_hash_policy_audit_and_mail(self):
        r = self.post_account()
        self.assertRedirects(r, "/administracion/usuarios/")
        u = self.User.objects.get(username="cuenta_nueva")
        self.assertFalse(u.has_usable_password())
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.groups.filter(name="operator").exists())
        self.assertEqual(u.email, "nueva@example.invalid")
        self.assertTrue(
            AccountPolicy.objects.filter(user=u, must_change_password=False).exists()
        )
        self.assertEqual(AccountMail.objects.get(user=u).status, "pending")
        self.assertTrue(
            AuditEvent.objects.filter(target=str(u.pk), action="Cuenta creada").exists()
        )

    def test_empty_account_has_field_errors_and_no_writes(self):
        self.client.force_login(self.root)
        before = self.User.objects.count()
        r = self.client.post("/administracion/usuarios/nuevo/", {})
        self.assertEqual(self.User.objects.count(), before)
        for name in [
            "username",
            "first_name",
            "last_name",
            "email",
            "confirm_password",
            "role",
        ]:
            self.assertIn(name, r.context["form"].errors)
        self.assertContains(r, 'aria-invalid="true"')
        self.assertContains(r, 'id="id_email_error"')

    def test_account_contract_rejects_invalid_names_usernames_and_email(self):
        for name, value in [
            ("username", "<script>"),
            ("first_name", "Ana123"),
            ("last_name", "Pérez<script>"),
            ("email", "correo@@mal"),
            ("first_name", "Ana\x00"),
            ("username", "a"),
            ("role", "superusuario_inventado"),
        ]:
            with self.subTest(field=name, value=value):
                r = self.post_account(**{name: value})
                self.assertIn(name, r.context["form"].errors)
                self.assertFalse(
                    self.User.objects.filter(username="cuenta_nueva").exists()
                )

    def test_duplicate_username_case_and_email_rejected_on_correct_field(self):
        for field, value in [
            ("username", "QA_ROOT"),
            ("email", "ROOT@EXAMPLE.INVALID"),
        ]:
            with self.subTest(field=field):
                r = self.post_account(**{field: value})
                self.assertIn(field, r.context["form"].errors)

    def test_bad_support_password_does_not_create_account(self):
        r = self.post_account(confirm_password="No-es-correcta")
        self.assertIn("confirm_password", r.context["form"].errors)
        self.assertFalse(self.User.objects.filter(username="cuenta_nueva").exists())

    def test_weak_or_long_temporary_password_rejected(self):
        for secret in ["123", "123456789012", "password", "a" * 129, "cuenta_nueva"]:
            with self.subTest(length=len(secret)):
                r = self.post_account(initial_password=secret)
                self.assertIn("initial_password", r.context["form"].errors)

    def test_password_symbols_and_accented_names_are_legitimate(self):
        self.post_account(initial_password=PASSWORD)
        u = self.User.objects.get(username="cuenta_nueva")
        self.assertNotEqual(u.password, PASSWORD)
        self.assertTrue(u.check_password(PASSWORD))
        self.assertEqual(u.first_name, "María José")
        self.assertTrue(AccountPolicy.objects.get(user=u).must_change_password)

    def test_temporary_password_forces_change_and_hash_stored(self):
        self.post_account(initial_password=PASSWORD)
        u = self.User.objects.get(username="cuenta_nueva")
        c = Client()
        c.login(username=u.username, password=PASSWORD)
        self.assertRedirects(c.get("/"), "/cuenta/contrasena/")
        self.assertEqual(
            c.post(
                "/cuenta/contrasena/",
                {
                    "old_password": "wrong",
                    "new_password1": "Better<> 'Private-2026!",
                    "new_password2": "Better<> 'Private-2026!",
                },
            ).status_code,
            200,
        )
        self.assertTrue(AccountPolicy.objects.get(user=u).must_change_password)
        self.assertRedirects(
            c.post(
                "/cuenta/contrasena/",
                {
                    "old_password": PASSWORD,
                    "new_password1": "Better<> 'Private-2026!",
                    "new_password2": "Better<> 'Private-2026!",
                },
            ),
            "/cuenta/contrasena/actualizada/",
        )
        u.refresh_from_db()
        self.assertTrue(u.check_password("Better<> 'Private-2026!"))
        self.assertFalse(AccountPolicy.objects.get(user=u).must_change_password)
        self.assertEqual(c.get("/administracion/cortes/").status_code, 200)

    def test_mismatched_and_overlong_new_passwords_not_saved(self):
        self.client.force_login(self.reader)
        for p1, p2 in [("A-new-pass-2026!", "Different-pass!"), ("x" * 129, "x" * 129)]:
            with self.subTest(length=len(p1)):
                r = self.client.post(
                    "/cuenta/contrasena/",
                    {
                        "old_password": PASSWORD,
                        "new_password1": p1,
                        "new_password2": p2,
                    },
                )
                self.assertTrue(r.context["form"].errors)
                self.reader.refresh_from_db()
                self.assertTrue(self.reader.check_password(PASSWORD))

    def test_self_deactivation_and_self_demotion_forbidden(self):
        self.client.force_login(self.root)
        for updates in [{"is_active": ""}, {"role": "reader"}]:
            data = (
                self.account_data(
                    username=self.root.username,
                    email=self.root.email,
                    role="superadmin",
                    **updates,
                )
                if "role" not in updates
                else self.account_data(
                    username=self.root.username, email=self.root.email, **updates
                )
            )
            r = self.client.post(f"/administracion/usuarios/{self.root.pk}/", data)
            self.assertTrue(r.context["form"].non_field_errors())
            self.root.refresh_from_db()
            self.assertTrue(self.root.is_active)
            self.assertTrue(self.root.is_superuser)

    def test_edit_deactivate_reactivate_and_reassign_roles(self):
        self.client.force_login(self.root)
        r = self.client.post(
            f"/administracion/usuarios/{self.reader.pk}/",
            self.account_data(
                username=self.reader.username,
                email=self.reader.email,
                role="publisher",
                is_active="",
            ),
        )
        self.assertEqual(r.status_code, 302)
        self.reader.refresh_from_db()
        self.assertFalse(self.reader.is_active)
        self.assertTrue(self.reader.groups.filter(name="publisher").exists())
        self.client.post(
            f"/administracion/usuarios/{self.reader.pk}/",
            self.account_data(
                username=self.reader.username, email=self.reader.email, role="reader"
            ),
        )
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.is_active)
        self.assertFalse(self.reader.groups.exists())

    def test_search_pagination_and_injection_as_data(self):
        self.client.force_login(self.root)
        for n in range(15):
            self.User.objects.create_user(f"pagination_{n}")
        self.assertEqual(
            len(
                self.client.get("/administracion/usuarios/", {"page": 2}).context[
                    "page"
                ]
            ),
            7,
        )
        r = self.client.get("/administracion/usuarios/", {"q": "qa_root"})
        self.assertEqual(r.context["page"].paginator.count, 1)
        r = self.client.get("/administracion/usuarios/", {"q": "' OR '1'='1"})
        self.assertTrue(r.context["search_form"].errors)
        self.assertEqual(r.context["page"].paginator.count, 0)
        self.assertEqual(self.User.objects.count(), 19)

    def test_mail_worker_and_invitation_activation_end_to_end(self):
        self.client.cookies["rnc_language"] = "en"
        self.post_account()
        u = self.User.objects.get(username="cuenta_nueva")
        queued_mail = AccountMail.objects.get(user=u)
        self.assertEqual(queued_mail.language, "en")
        call_command("deliver_account_mail", stdout=io.StringIO())
        queued_mail.refresh_from_db()
        self.assertEqual(queued_mail.status, "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Set password · RNC")
        self.assertIn("A password has been requested for your RNC account.", mail.outbox[0].body)
        link = next(
            line
            for line in mail.outbox[0].body.splitlines()
            if line.startswith("https://")
        )
        self.assertTrue(link.startswith("https://rnc.example.invalid/"))
        path = link.split("example.invalid", 1)[1]
        c = Client()
        r = c.get(path, follow=True)
        self.assertTrue(r.context["validlink"])
        action = r.request["PATH_INFO"]
        new = "Invited<> 'Private-2026!"
        self.assertRedirects(
            c.post(action, {"new_password1": new, "new_password2": new}),
            "/cuenta/restablecida/",
        )
        u.refresh_from_db()
        self.assertTrue(u.check_password(new))
        self.assertFalse(Client().get(path, follow=True).context["validlink"])

    def test_recovery_email_uses_selected_language(self):
        self.client.cookies["rnc_language"] = "en"
        response = self.client.post(
            "/cuenta/recuperar/", {"email": self.reader.email}
        )
        self.assertRedirects(response, "/cuenta/recuperar/solicitado/")
        queued_mail = AccountMail.objects.get(user=self.reader)
        self.assertEqual(queued_mail.language, "en")

        call_command("deliver_account_mail", stdout=io.StringIO())
        queued_mail.refresh_from_db()
        self.assertEqual(queued_mail.status, "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Set password · RNC")
        self.assertIn("A password has been requested for your RNC account.", mail.outbox[0].body)

    def test_recovery_unknown_inactive_and_known_account_have_same_public_result(self):
        for address in ["reader@example.invalid", "missing@example.invalid"]:
            r = self.client.post("/cuenta/recuperar/", {"email": address})
            self.assertRedirects(r, "/cuenta/recuperar/solicitado/")
        self.assertEqual(AccountMail.objects.count(), 1)
        self.reader.is_active = False
        self.reader.save()
        AccountMail.objects.all().delete()
        self.client.post("/cuenta/recuperar/", {"email": self.reader.email})
        self.assertFalse(AccountMail.objects.exists())

    def test_recovery_rate_limit_deduplicates_mail(self):
        for _ in range(8):
            self.assertEqual(
                self.client.post(
                    "/cuenta/recuperar/", {"email": self.reader.email}
                ).status_code,
                302,
            )
        self.assertEqual(AccountMail.objects.count(), 1)

    def test_expired_invalid_tokens_and_deactivated_account(self):
        uid = urlsafe_base64_encode(force_bytes(self.reader.pk))
        token = default_token_generator.make_token(self.reader)
        path = f"/cuenta/restablecer/{uid}/{token}/"
        now = default_token_generator._now()
        with patch.object(
            default_token_generator, "_now", return_value=now + timedelta(hours=2)
        ):
            self.assertFalse(self.client.get(path, follow=True).context["validlink"])
        self.assertFalse(
            self.client.get(
                f"/cuenta/restablecer/{uid}/bad-token/", follow=True
            ).context["validlink"]
        )
        self.reader.is_active = False
        self.reader.save()
        r = self.client.get(path, follow=True)
        if r.context["validlink"]:
            self.client.post(
                r.request["PATH_INFO"],
                {
                    "new_password1": "Changed-safe-2026!",
                    "new_password2": "Changed-safe-2026!",
                },
            )
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password(PASSWORD))

    def test_smtp_failure_recorded_without_exposing_secret(self):
        AccountMail.objects.create(user=self.reader)
        with patch(
            "public_site.accounts.send_mail",
            side_effect=RuntimeError("private-transport-details"),
        ):
            call_command("deliver_account_mail", stdout=io.StringIO())
        self.assertEqual(AccountMail.objects.get().status, "failed")
        self.client.force_login(self.root)
        r = self.client.get("/administracion/usuarios/")
        self.assertContains(r, "Falló el envío")
        self.assertNotContains(r, "private-transport-details")

    def test_html_is_escaped_and_does_not_create_account(self):
        self.client.force_login(self.root)
        payload = "<script>alert('probe')</script>"
        r = self.client.post(
            "/administracion/usuarios/nuevo/", self.account_data(first_name=payload)
        )
        self.assertContains(r, "&lt;script&gt;")
        self.assertNotContains(r, payload)
        self.assertFalse(self.User.objects.filter(username="cuenta_nueva").exists())
        self.assertIn("script-src 'self'", r["Content-Security-Policy"])
        self.assertIn("object-src 'none'", r["Content-Security-Policy"])

    def test_login_throttle_cannot_be_bypassed_with_correct_credentials_after_limit(
        self,
        ):
        for _ in range(11):
            self.client.post(
                "/acceso/", {"username": self.reader.username, "password": "wrong"}
            )
        r = self.client.post(
            "/acceso/", {"username": self.reader.username, "password": PASSWORD}
        )
        self.assertTrue(r.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_error_is_themed_and_does_not_echo_internal_reason(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/administracion/usuarios/nuevo/", {})
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "No se pudo enviar el formulario", status_code=403)
        self.assertNotContains(r, "CSRF cookie not set", status_code=403)

    def test_search_rejects_overlength_and_tags_without_widening_results(self):
        self.client.force_login(self.root)
        for query in ["a" * 101, "<script>alert(1)</script>"]:
            r = self.client.get("/administracion/usuarios/", {"q": query})
            self.assertIn("q", r.context["search_form"].errors)
            self.assertEqual(r.context["page"].paginator.count, 0)

    def test_password_change_invalidates_another_session(self):
        first = Client()
        second = Client()
        first.login(username=self.reader.username, password=PASSWORD)
        second.login(username=self.reader.username, password=PASSWORD)
        first.post(
            "/cuenta/contrasena/",
            {
                "old_password": PASSWORD,
                "new_password1": "Another-private-2026!",
                "new_password2": "Another-private-2026!",
            },
        )
        self.assertNotIn("_auth_user_id", second.get("/").wsgi_request.session)
