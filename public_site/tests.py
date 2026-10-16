"""Backend regression: isolated DB/files, fictitious identities and no SMTP."""

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import Delivery, Publication, AuditEvent, AccountPolicy, AccountMail
from .services import ingest, transition, delivery_records
from .testing import uploaded, synthetic_rows, csv_bytes

PASSWORD = "Review-test<> 'Secure-2026!"


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PortalTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rnc-backend-")
        self.addCleanup(self.temporary.cleanup)
        self.override = override_settings(
            PRIVATE_STORAGE_ROOT=Path(self.temporary.name),
            EMAIL_FILE_PATH=Path(self.temporary.name) / "mail",
            PUBLIC_ORIGIN="https://rnc.example.invalid",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()
        delivery_records.cache_clear()
        self.User = get_user_model()
        self.root = self.User.objects.create_superuser(
            "qa_root",
            email="root@example.invalid",
            password=PASSWORD,
            first_name="Elena",
            last_name="García",
        )
        self.reader = self.User.objects.create_user(
            "qa_reader", email="reader@example.invalid", password=PASSWORD
        )
        self.operator = self.User.objects.create_user("qa_operator", password=PASSWORD)
        self.operator.groups.add(Group.objects.get(name="operator"))
        self.publisher = self.User.objects.create_user(
            "qa_publisher", password=PASSWORD
        )
        self.publisher.groups.add(Group.objects.get(name="publisher"))

    def account_data(self, **updates):
        data = {
            "username": "cuenta_nueva",
            "first_name": "María José",
            "last_name": "O’Neill-Pérez",
            "email": "nueva@example.invalid",
            "role": "operator",
            "is_active": "on",
            "initial_password": "",
            "confirm_password": PASSWORD,
        }
        data.update(updates)
        return data

    def delivery(self, extra=1, publish=False):
        d = ingest(uploaded(extra), "Corte sintético 2023–2024", self.root)
        if publish:
            transition(
                d.pk,
                "publish",
                self.root,
                "Publicación sintética autorizada para la prueba.",
            )
        return d

    def post_account(self, **updates):
        self.client.force_login(self.root)
        return self.client.post(
            "/administracion/usuarios/nuevo/", self.account_data(**updates)
        )

    def test_public_pages_and_no_redundant_home_button(self):
        for path in ["/", "/consulta/", "/acceso/", "/cuenta/recuperar/"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "sidebar-home")
                self.assertNotContains(r, 'href="/administracion/cortes/"')

    def test_anonymous_requires_login_on_every_private_route(self):
        for path in [
            "/administracion/cortes/",
            "/administracion/cortes/ejemplo/",
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
        self.assertRedirects(c.post("/salir/", {"csrfmiddlewaretoken": token}), "/")

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
        self.post_account()
        u = self.User.objects.get(username="cuenta_nueva")
        call_command("deliver_account_mail", stdout=io.StringIO())
        self.assertEqual(AccountMail.objects.get(user=u).status, "sent")
        self.assertEqual(len(mail.outbox), 1)
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

    def test_upload_stores_private_original_json_and_metadata(self):
        d = self.delivery()
        self.assertEqual(d.row_count, 73)
        self.assertEqual(d.person_count, 36)
        self.assertEqual(d.report["accepted_rows"], 73)
        path = Path(self.temporary.name) / d.storage_key
        self.assertTrue(path.exists())
        self.assertTrue(path.with_suffix(".csv").exists())
        self.assertEqual(len(json.loads(path.read_text())), 73)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            d.checksum, __import__("hashlib").sha256(csv_bytes()).hexdigest()
        )

    def test_upload_duplicate_is_not_another_delivery(self):
        self.delivery()
        with self.assertRaisesMessage(ValueError, "ya está registrada"):
            self.delivery()
        self.assertEqual(Delivery.objects.count(), 1)

    def test_upload_empty_missing_file_or_confirmation_is_field_specific(self):
        self.client.force_login(self.root)
        r = self.client.post("/administracion/cortes/", {})
        for field in ["title", "file", "synthetic"]:
            self.assertIn(field, r.context["form"].errors)
        self.assertFalse(Delivery.objects.exists())

    def test_upload_wrong_extension_and_title_rejected_before_storage(self):
        self.client.force_login(self.root)
        for title, name, field in [
            ("Corte válido", "sintetico.exe", "file"),
            ("<script>alert(1)</script>", "sintetico.csv", "title"),
        ]:
            r = self.client.post(
                "/administracion/cortes/",
                {"title": title, "file": uploaded(name=name), "synthetic": "on"},
            )
            self.assertIn(field, r.context["form"].errors)
        self.assertFalse(Delivery.objects.exists())

    def test_uploaded_oversize_file_rejected(self):
        from .forms import UploadForm

        file = uploaded()
        file.size = 12 * 1024 * 1024 + 1
        f = UploadForm({"title": "Corte válido", "synthetic": "on"}, {"file": file})
        self.assertFalse(f.is_valid())
        self.assertIn("file", f.errors)

    def test_bad_csv_variants_are_rejected_atomically_and_audited(self):
        variants = []
        variants.append(b"header,no-compatible\n1,2\n")
        variants.append(b"\xff\xfeinvalid")
        for field, value in [
            ("synthetic", "FALSE"),
            ("person_id", "real-id"),
            ("tumor_id", "real-tumor"),
            ("period", "2024<script>"),
            ("population", "0"),
            ("standard_weight", "99"),
            ("sex", "otro"),
            ("site", "desconocida"),
            ("name", "Ana\x00"),
        ]:
            rows = synthetic_rows()
            rows[0][field] = value
            variants.append(csv_bytes(rows))
        rows = synthetic_rows()
        rows[1]["tumor_id"] = rows[0]["tumor_id"]
        variants.append(csv_bytes(rows))
        rows = synthetic_rows()
        rows.pop(0)
        variants.append(csv_bytes(rows))
        for index, raw in enumerate(variants):
            with self.subTest(variant=index):
                with self.assertRaises(ValueError):
                    ingest(
                        SimpleUploadedFile("invalid.csv", raw),
                        "Carga inválida",
                        self.root,
                    )
                self.assertFalse(Delivery.objects.filter(status="validated").exists())
        self.assertEqual(
            Delivery.objects.filter(status="rejected").count(), len(variants)
        )
        self.assertEqual(
            AuditEvent.objects.filter(action="Carga rechazada técnicamente").count(),
            len(variants),
        )

    def test_bad_upload_renders_file_error_and_preserves_title(self):
        self.client.force_login(self.root)
        r = self.client.post(
            "/administracion/cortes/",
            {
                "title": "Mi corte",
                "synthetic": "on",
                "file": SimpleUploadedFile("invalid.csv", b"wrong\n"),
            },
        )
        self.assertIn("file", r.context["form"].errors)
        self.assertContains(r, 'value="Mi corte"')

    def test_publish_replace_revoke_and_audit_are_persistent(self):
        first = self.delivery(publish=True)
        second = self.delivery(extra=2)
        transition(
            second.pk, "publish", self.publisher, "Nueva versión sintética revisada."
        )
        first.refresh_from_db()
        self.assertEqual(first.status, "revoked")
        self.assertEqual(Publication.objects.get(pk=1).delivery_id, second.pk)
        self.assertEqual(self.client.get("/").context["summary"]["tumors"], 38)
        transition(
            second.pk, "revoke", self.publisher, "Revocación sintética para revisión."
        )
        self.assertIsNone(Publication.objects.get(pk=1).delivery_id)
        self.assertFalse(self.client.get("/consulta/").context["table"])
        self.assertTrue(
            AuditEvent.objects.filter(
                action="Revocación", actor=self.publisher, target=str(second.pk)
            ).exists()
        )

    def test_operator_cannot_publish_even_with_forged_post(self):
        d = self.delivery()
        self.client.force_login(self.operator)
        self.assertEqual(
            self.client.post(
                f"/administracion/cortes/{d.pk}/estado/",
                {"action": "publish", "reason": "Intento sin autorización."},
            ).status_code,
            403,
        )
        d.refresh_from_db()
        self.assertEqual(d.status, "validated")

    def test_decision_invalid_reason_action_and_stale_state_not_saved(self):
        d = self.delivery()
        self.client.force_login(self.root)
        path = f"/administracion/cortes/{d.pk}/estado/"
        for data in [
            {"action": "publish", "reason": "corto"},
            {"action": "publish", "reason": "<script>alert(1)</script>"},
            {"action": "drop_database", "reason": "Una razón de longitud suficiente."},
        ]:
            r = self.client.post(path, data)
            self.assertEqual(r.status_code, 400)
            self.assertTrue(r.context["decision_form"].errors)
            d.refresh_from_db()
            self.assertEqual(d.status, "validated")
        transition(d.pk, "publish", self.root, "Publicación inicial de prueba.")
        r = self.client.post(
            path, {"action": "publish", "reason": "Acción antigua repetida."}
        )
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.context["decision_form"].non_field_errors())

    def test_home_query_and_exports_never_include_private_people(self):
        self.delivery(publish=True)
        for path in ["/", "/consulta/", "/consulta/?format=csv"]:
            r = self.client.get(path)
            self.assertNotContains(r, "Ana O’Neill")
            self.assertNotContains(r, "SYN-P-")
            self.assertNotContains(r, "SYN-T-")
        self.assertEqual(
            self.client.get("/private/ejemplo_sintetico.csv").status_code, 404
        )

    def test_people_unique_across_tumors_years_and_denominators_deduplicated(self):
        self.delivery(publish=True)
        r = self.client.get("/consulta/", {"unit": "persons"})
        self.assertEqual(r.context["summary"]["persons"], 36)
        self.assertEqual(r.context["summary"]["tumors"], 73)
        r = self.client.get("/consulta/", {"metric": "rate", "dimension": "sex"})
        self.assertEqual(sum(row["population"] for row in r.context["table"]), 720000)
        r = self.client.get(
            "/consulta/",
            {
                "year": "2024",
                "site": "Colon y recto",
                "dimension": "sex",
                "metric": "rate",
            },
        )
        self.assertEqual(sum(row["population"] for row in r.context["table"]), 360000)

    def test_unknown_filter_and_incompatible_graphs_have_field_errors(self):
        self.delivery(publish=True)
        for data, field in [
            ({"year": "bad"}, "year"),
            ({"chart": "line"}, "chart"),
            ({"metric": "asr", "age": "0-4"}, "metric"),
            ({"chart": "stacked", "metric": "rate"}, "chart"),
            ({"chart": "pie", "unit": "persons"}, "chart"),
            ({"chart": "grouped", "sex": "Mujeres"}, "chart"),
        ]:
            r = self.client.get("/consulta/", data)
            self.assertIn(field, r.context["form"].errors)
            self.assertFalse(r.context["table"])

    def test_all_eight_graph_types_render_compatible_data(self):
        self.delivery(publish=True)
        for kind in [
            "bar",
            "column",
            "line",
            "grouped",
            "stacked",
            "percent",
            "pie",
            "doughnut",
        ]:
            data = {
                "chart": kind,
                "dimension": (
                    "period"
                    if kind == "line"
                    else "sex" if kind in {"pie", "doughnut"} else "site"
                ),
            }
            r = self.client.get("/consulta/", data)
            with self.subTest(kind=kind):
                self.assertFalse(r.context["form"].errors)
                self.assertTrue(r.context["table"])
                self.assertEqual(r.context["chart_payload"]["type"], kind)

    def test_all_export_formats_signatures_metadata_and_no_private_values(self):
        self.delivery(publish=True)
        for fmt, signature in [
            ("csv", b"\xef\xbb\xbf"),
            ("xlsx", b"PK"),
            ("png", b"\x89PNG"),
            ("svg", b"<?xml"),
            ("pdf", b"%PDF"),
        ]:
            with self.subTest(fmt=fmt):
                r = self.client.get("/consulta/", {"year": "2024", "format": fmt})
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.content.startswith(signature))
                self.assertIn(fmt, r["Content-Disposition"])
                self.assertEqual(r["Cache-Control"], "no-store")
        r = self.client.get("/consulta/", {"year": "2024", "format": "csv"})
        self.assertIn("2024", r.content.decode("utf-8-sig"))
        self.assertIn("Datos sintéticos", r.content.decode("utf-8-sig"))

    def test_revocation_does_not_serve_cached_export(self):
        d = self.delivery(publish=True)
        self.assertEqual(
            self.client.get("/consulta/?format=csv")["Content-Type"],
            "text/csv; charset=utf-8",
        )
        transition(d.pk, "revoke", self.root, "Retirar corte sintético de prueba.")
        r = self.client.get("/consulta/?format=csv")
        self.assertNotIn("attachment", r.get("Content-Disposition", ""))

    def test_downloaded_update_is_valid_and_adds_one_tumor(self):
        d = self.delivery(publish=True)
        self.client.force_login(self.root)
        r = self.client.get("/administracion/cortes/ejemplo/")
        updated = ingest(
            SimpleUploadedFile("update.csv", r.content),
            "Actualización sintética",
            self.root,
        )
        self.assertEqual(updated.row_count, d.row_count + 1)
        self.assertEqual(updated.person_count, d.person_count)

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

    def test_control_characters_and_injected_identifiers_are_not_stored_as_valid_records(
        self,
    ):
        for field, value in [
            ("person_id", "SYN-P-<script>"),
            ("tumor_id", "SYN-T-../evil"),
            ("name", "=HYPERLINK(1)"),
        ]:
            rows = synthetic_rows()
            rows[0][field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ingest(uploaded(rows=rows), "Revisión sintética", self.root)
                self.assertFalse(Delivery.objects.filter(status="validated").exists())

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

    def test_privileged_actions_get_do_not_mutate(self):
        d = self.delivery()
        self.client.force_login(self.root)
        self.assertEqual(
            self.client.get(f"/administracion/cortes/{d.pk}/estado/").status_code, 405
        )
        d.refresh_from_db()
        self.assertEqual(d.status, "validated")
        self.assertFalse(Publication.objects.exists())

    def test_revoked_cut_with_saved_filters_shows_empty_state_not_field_errors(self):
        d = self.delivery(publish=True)
        self.client.get(
            "/consulta/?year=2024&dimension=age_group&metric=rate&format=csv"
        )
        transition(d.pk, "revoke", self.root, "Retiro de revisión sintética.")
        r = self.client.get(
            "/consulta/?year=2024&dimension=age_group&metric=rate&format=csv"
        )
        self.assertContains(r, "No hay resultados")
        self.assertFalse(r.context["form"].errors)
        self.assertNotIn("attachment", r.get("Content-Disposition", ""))
