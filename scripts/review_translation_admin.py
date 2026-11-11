"""Black-box review of draft locales across public/admin pages and account mail.

Draft PO files remain fuzzy in the repository. This review compiles copies into
a disposable locale root and uses a temporary database plus synthetic users.
"""

import json
import html
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

PORTAL_ROUTE_NAMES = frozenset({
    "home", "about", "login", "logout", "synthetic_explorer",
    "coding_nomenclators", "legacy_explorer", "intake_prototype", "sample",
    "delivery", "delivery_action", "users", "user_create", "user_edit",
    "password_change", "password_change_done", "password_reset",
    "password_reset_done", "password_reset_confirm", "password_reset_complete",
})


def run():
    import django
    from django.conf import settings
    from django.core.management import call_command
    from django.core.cache import cache
    from django.test import Client
    from django.utils import translation
    from django.urls import resolve, reverse
    from django.utils.translation import gettext as _
    from django.utils.translation import trans_real
    from django.core import mail
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    from config.languages import PRIORITY_LANGUAGES
    from scripts.review_pwa import compile_isolated_draft_catalogs

    results = []
    errors = []

    def record(ok, locale, surface, evidence=None):
        item = {"ok": bool(ok), "locale": locale, "surface": surface}
        if evidence is not None:
            item["evidence"] = evidence
        results.append(item)
        if not ok:
            errors.append(item)

    def javascript_has(body, value):
        escaped = "".join(
            character if ord(character) < 128 else f"\\u{ord(character):04x}"
            for character in value
        )
        return value in body or escaped in body

    with tempfile.TemporaryDirectory(prefix="rnc-translation-admin-") as temporary:
        workspace = Path(temporary)
        draft_locale_root = workspace / "draft-locales"
        compiled = compile_isolated_draft_catalogs(draft_locale_root)
        coding_catalog = workspace / "coding-catalog.json"
        coding_catalog.write_text(json.dumps({
            "version": "synthetic-review-v1",
            "source": "https://example.invalid/synthetic-catalog",
            "concepts": [{
                "concept_id": "review:synthetic",
                "name": "Synthetic review concept",
                "description": "Synthetic label used only to check translated UI text.",
                "language": "en",
                "source": "https://example.invalid/synthetic-concept",
                "license": "CC0",
                "publication_status": "authorized",
                "codes": [{
                    "system": "TEST",
                    "edition": "1",
                    "axis": "topography",
                    "code": "T-001",
                    "name": "Synthetic topography code",
                    "description": "Test-only concept code.",
                    "status": "current",
                    "source": "https://example.invalid/synthetic-code",
                    "license": "CC0",
                    "relationship": "primary",
                    "relationship_status": "source-declared",
                }],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        settings.DATABASES = {"default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(workspace / "review.sqlite3"),
        }}
        settings.LOCALE_PATHS = [draft_locale_root, ROOT / "locale"]
        settings.LANGUAGES = tuple(
            (code, native) for code, _english, native, _active in PRIORITY_LANGUAGES
        )
        settings.TRANSLATION_PREVIEW_ENABLED = True
        settings.DRAFT_TRANSLATION_LOCALES = tuple(
            code for code, _english, _native, active in PRIORITY_LANGUAGES if not active
        )
        settings.DEBUG = True
        settings.ALLOWED_HOSTS = ["testserver", "localhost"]
        settings.PRIVATE_STORAGE_ROOT = workspace / "private"
        settings.PUBLIC_RELEASE_ROOT = workspace / "releases"
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.EMAIL_FILE_PATH = None
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
        settings.PUBLIC_ORIGIN = "https://rnc.example.invalid"
        settings.RNC_CODING_CATALOG = str(coding_catalog)
        django.setup()
        trans_real.reset_cache(setting="LANGUAGES")
        call_command("migrate", verbosity=0, interactive=False)

        from django.contrib.auth import get_user_model
        from django.utils.formats import date_format
        from django.utils.timezone import localtime
        from public_site.accounts import invitation
        from public_site.management.commands.deliver_account_mail import Command
        from public_site.models import AccountMail, Delivery
        from public_site.testing import csv_bytes
        from public_site.urls import urlpatterns as portal_urlpatterns

        User = get_user_model()
        root = User.objects.create_superuser(
            "translation_review_admin",
            email="translation-review@example.invalid",
            password="Synthetic-review-2026!",
            first_name="Cuenta",
            last_name="Sintética",
        )
        recipient = User.objects.create_user(
            "translation_mail_user",
            email="translation-mail@example.invalid",
            password="Synthetic-mail-2026!",
        )
        synthetic_delivery = Delivery.objects.create(
            title="Corte sintético de revisión de fechas",
            checksum="a" * 64,
            created_by=root,
            row_count=2,
            person_count=2,
            report={},
        )
        sample_path = settings.PRIVATE_STORAGE_ROOT / "ejemplo_sintetico.csv"
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(csv_bytes())
        declared_portal_routes = frozenset(
            pattern.name for pattern in portal_urlpatterns if pattern.name
        )
        route_probe_paths = {
            "home": reverse("public_site:home"),
            "about": reverse("public_site:about"),
            "login": reverse("public_site:login"),
            "logout": reverse("public_site:logout"),
            "synthetic_explorer": reverse("public_site:synthetic_explorer"),
            "coding_nomenclators": reverse("public_site:coding_nomenclators"),
            "legacy_explorer": reverse("public_site:legacy_explorer"),
            "intake_prototype": reverse("public_site:intake_prototype"),
            "sample": reverse("public_site:sample"),
            "delivery": reverse("public_site:delivery", kwargs={"pk": synthetic_delivery.pk}),
            "delivery_action": reverse("public_site:delivery_action", kwargs={"pk": synthetic_delivery.pk}),
            "users": reverse("public_site:users"),
            "user_create": reverse("public_site:user_create"),
            "user_edit": reverse("public_site:user_edit", kwargs={"pk": recipient.pk}),
            "password_change": reverse("public_site:password_change"),
            "password_change_done": reverse("public_site:password_change_done"),
            "password_reset": reverse("public_site:password_reset"),
            "password_reset_done": reverse("public_site:password_reset_done"),
            "password_reset_confirm": reverse(
                "public_site:password_reset_confirm",
                kwargs={"uidb64": urlsafe_base64_encode(force_bytes(recipient.pk)),
                        "token": "invalid-token"},
            ),
            "password_reset_complete": reverse("public_site:password_reset_complete"),
        }

        pages = (
            ("/", False),
            ("/el-rnc/", False),
            ("/consulta/", False),
            ("/consulta-sintetica/", False),
            ("/nomencladores/", False),
            ("/administracion/cortes/", True),
            (f"/administracion/cortes/{synthetic_delivery.pk}/", True),
            ("/administracion/usuarios/", True),
            ("/administracion/usuarios/nuevo/", True),
            (f"/administracion/usuarios/{recipient.pk}/", True),
            ("/cuenta/contrasena/", True),
            ("/cuenta/contrasena/actualizada/", True),
            ("/cuenta/recuperar/", False),
            ("/cuenta/recuperar/solicitado/", False),
            ("/cuenta/restablecida/", False),
            ("/__translation_review_missing__/", False),
        )
        for locale, _english_name, _native, _active in PRIORITY_LANGUAGES:
            expected_dir = "rtl" if locale in {"ar", "ur"} else "ltr"
            record(
                declared_portal_routes == PORTAL_ROUTE_NAMES,
                locale,
                "inventario de rutas portal sincronizado con escenarios revisados",
                {"declared": sorted(declared_portal_routes),
                 "review_inventory": sorted(PORTAL_ROUTE_NAMES),
                 "missing": sorted(PORTAL_ROUTE_NAMES - declared_portal_routes),
                 "unreviewed": sorted(declared_portal_routes - PORTAL_ROUTE_NAMES)},
            )
            client = Client()
            client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            client.force_login(root)
            probe_names_match = frozenset(route_probe_paths) == declared_portal_routes
            record(
                probe_names_match,
                locale,
                "cada ruta nombrada tiene una sonda HTTP explícita",
                {"declared_without_probe": sorted(declared_portal_routes - route_probe_paths.keys()),
                 "probe_without_route": sorted(route_probe_paths.keys() - declared_portal_routes)},
            )
            for route_name, path in route_probe_paths.items():
                response = client.get(path, follow=False)
                resolved_name = response.resolver_match.url_name if response.resolver_match else None
                record(
                    resolved_name == route_name,
                    locale,
                    f"ruta HTTP {route_name} resuelve a su escenario",
                    {"path": path, "resolved_name": resolved_name,
                     "status": response.status_code},
                )
            with translation.override(locale):
                language_label = str(_("Idioma"))
                admin_label = str(_("Administración"))
                women = str(_("Mujeres"))
                frequency = str(_("Frecuencia absoluta"))
                username_rule_message = str(_(
                    "Use letras de la A a la Z, números, punto, guion o guion bajo."
                ))
                axis_label = str(_("Topografía"))
                relationship_label = str(_("Código del concepto"))
                relationship_status_label = str(_("Declarado por la fuente"))
                csv_structure_error = str(_(
                    "Estructura incompatible. Descargue el CSV sintético de ejemplo."
                ))
                missing_page_heading = str(_("No encontramos esa página"))
                missing_page_intro = str(_(
                    "La dirección no existe o el recurso ya no está disponible. "
                    "Puede continuar desde la navegación del portal."
                ))
                csrf_heading = str(_("No se pudo enviar el formulario"))
                csrf_intro = str(_(
                    "La sesión del formulario ha caducado o no se pudo verificar. "
                    "Vuelva a abrir la página e inténtelo otra vez. No se guardó este envío."
                ))
                sample_filename = str(_("actualizacion_sintetica")) + ".csv"
                min_length_message = str(_(
                    "Use al menos %(limit_value)s caracteres."
                )) % {"limit_value": 10}
                max_length_message = str(_(
                    "Use como máximo %(limit_value)s caracteres."
                )) % {"limit_value": 250}
                invalid_email_message = str(_(
                    "Ingrese un correo electrónico válido."
                ))
                invalid_choice_message = str(_(
                    "Seleccione una opción válida."
                ))
                password_labels = [
                    str(_("Contraseña actual")), str(_("Nueva contraseña")),
                    str(_("Confirmar nueva contraseña")),
                    str(_("Repita la misma contraseña para confirmar.")),
                ]
                password_mismatch = str(_("Las contraseñas nuevas no coinciden."))
                password_common = str(_("Elija una contraseña que no sea de uso común."))
                password_numeric = str(_("La contraseña no puede contener solo números."))
                password_similarity = str(_(
                    "La contraseña no debe parecerse a sus datos personales."
                ))
                password_too_short = str(_(
                    "La contraseña es demasiado corta; debe contener al menos "
                    "%(min_length)s caracteres."
                )) % {"min_length": 8}
                login_copy = [
                    str(_("Iniciar sesión")), str(_("¿Olvidó su contraseña?")),
                    str(_("Las cuentas son creadas por el equipo administrador. No hay registro público.")),
                ]
                reset_password_labels = [
                    str(_("Nueva contraseña")), str(_("Confirmar nueva contraseña")),
                    str(_("Repita la misma contraseña para confirmar.")),
                ]
                reset_invalid_link = str(_(
                    "El enlace no es válido, ya fue utilizado o ha caducado. Solicite uno nuevo."
                ))
                preview_title = str(_("Vista previa de traducción automática"))
                preview_warning = str(_(
                    "Este idioma usa un borrador no revisado ni aprobado. "
                    "No lo use para interpretar estadísticas de cáncer."
                ))
                preview_suffix = str(_("borrador de vista previa"))

            for path, authenticated in pages:
                response = client.get(path)
                body = response.content.decode("utf-8")
                expected_status = 404 if path == "/__translation_review_missing__/" else 200
                page_ok = response.status_code == expected_status
                html_ok = f'<html lang="{locale}" dir="{expected_dir}"' in body
                record(
                    page_ok and html_ok,
                    locale,
                    f"página {path}",
                    {"status": response.status_code, "expected_status": expected_status,
                     "html_locale": html_ok, "authenticated": authenticated},
                )
                if path == "/administracion/cortes/":
                    record(language_label in body and admin_label in body, locale,
                           "etiquetas compartidas de administración",
                           {"language_label_present": language_label in body,
                            "admin_label_present": admin_label in body})
                    with translation.override(locale):
                        expected_date = date_format(
                            localtime(synthetic_delivery.created_at), "SHORT_DATETIME_FORMAT"
                        )
                    record(
                        expected_date in body,
                        locale,
                        "fecha de recepción según formato local",
                        {"expected": expected_date, "present": expected_date in body},
                    )
                if path == "/":
                    if locale in settings.DRAFT_TRANSLATION_LOCALES:
                        decoded_body = html.unescape(body)
                        record(
                            preview_title in decoded_body
                            and preview_warning in decoded_body
                            and preview_suffix in decoded_body,
                            locale,
                            "aviso de traducción preliminar y etiqueta en el selector",
                            {"heading_present": preview_title in decoded_body,
                             "warning_present": preview_warning in decoded_body,
                             "selector_suffix_present": preview_suffix in decoded_body},
                        )
                    else:
                        record(
                            preview_title not in body,
                            locale,
                            "sin aviso de borrador en locale de producción",
                            {"preview_warning_hidden": preview_title not in body},
                        )
                if path == f"/administracion/cortes/{synthetic_delivery.pk}/":
                    with translation.override(locale):
                        expected_date = date_format(
                            localtime(synthetic_delivery.created_at), "SHORT_DATETIME_FORMAT"
                        )
                    record(
                        expected_date in body,
                        locale,
                        "fecha del informe técnico según formato local",
                        {"expected": expected_date, "present": expected_date in body},
                    )
                if path == "/administracion/usuarios/nuevo/":
                    decoded_body = html.unescape(body)
                    record(
                        f'data-rule-message="{username_rule_message}"' in decoded_body,
                        locale,
                        "mensaje de validación del navegador",
                        {"localized_rule_message_present":
                         f'data-rule-message="{username_rule_message}"' in decoded_body},
                    )
                if path == "/__translation_review_missing__/":
                    decoded_body = html.unescape(body)
                    record(
                        response.status_code == 404
                        and missing_page_heading in decoded_body
                        and missing_page_intro in decoded_body,
                        locale,
                        "mensaje localizado de página no encontrada",
                        {"status": response.status_code,
                         "heading_present": missing_page_heading in decoded_body,
                         "intro_present": missing_page_intro in decoded_body,
                         "expected_heading": missing_page_heading,
                         "body_excerpt": decoded_body[decoded_body.find('<main'):decoded_body.find('</main>') + 7]},
                    )
                if path == "/nomencladores/":
                    record(
                        axis_label in body
                        and relationship_label in body
                        and relationship_status_label in body,
                        locale,
                        "etiquetas traducidas del nomenclador sintético",
                        {"axis_present": axis_label in body,
                         "relationship_present": relationship_label in body,
                         "source_status_present": relationship_status_label in body},
                    )
                if path == "/cuenta/contrasena/":
                    decoded_body = html.unescape(body)
                    record(
                        all(label in decoded_body for label in password_labels),
                        locale,
                        "etiquetas y ayuda de cambio de contraseña",
                        {"expected": password_labels,
                         "present": [label in decoded_body for label in password_labels]},
                    )
                    short_response = client.post(path, {
                        "old_password": "Synthetic-review-2026!",
                        "new_password1": "123",
                        "new_password2": "123",
                    })
                    short_body = html.unescape(short_response.content.decode("utf-8"))
                    record(
                        short_response.status_code == 200 and password_too_short in short_body,
                        locale,
                        "error localizado de contraseña demasiado corta",
                        {"status": short_response.status_code,
                         "message_present": password_too_short in short_body},
                    )
                    record(
                        password_common in short_body,
                        locale,
                        "error localizado de contraseña de uso común",
                        {"message_present": password_common in short_body},
                    )
                    record(
                        password_numeric in short_body,
                        locale,
                        "error localizado de contraseña numérica",
                        {"message_present": password_numeric in short_body},
                    )
                    similar_response = client.post(path, {
                        "old_password": "Synthetic-review-2026!",
                        "new_password1": "translation_review_admin",
                        "new_password2": "translation_review_admin",
                    })
                    similar_body = html.unescape(similar_response.content.decode("utf-8"))
                    record(
                        similar_response.status_code == 200
                        and password_similarity in similar_body,
                        locale,
                        "error localizado de similitud con los datos de la cuenta",
                        {"status": similar_response.status_code,
                         "message_present": password_similarity in similar_body},
                    )
                    mismatch_response = client.post(path, {
                        "old_password": "Synthetic-review-2026!",
                        "new_password1": "Review-Unique-Password-2026!",
                        "new_password2": "Different-Password-2026!",
                    })
                    mismatch_body = html.unescape(mismatch_response.content.decode("utf-8"))
                    record(
                        mismatch_response.status_code == 200 and password_mismatch in mismatch_body,
                        locale,
                        "error localizado de confirmación de contraseña",
                        {"status": mismatch_response.status_code,
                         "message_present": password_mismatch in mismatch_body},
                    )
                if path == "/cuenta/recuperar/":
                    recovery_email = str(_("Correo electrónico"))
                    recovery_body = html.unescape(body)
                    record(
                        recovery_email in recovery_body,
                        locale,
                        "etiqueta localizada de correo para recuperación",
                        {"message_present": recovery_email in recovery_body},
                    )

            sample_response = client.get("/administracion/cortes/ejemplo/")
            anonymous_client = Client()
            anonymous_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            with translation.override(locale):
                invalid_login_message = str(_(
                    "El usuario o la contraseña no son válidos."
                ))
            invalid_login_response = anonymous_client.post("/acceso/", {
                "username": "translation_missing_user",
                "password": "Synthetic-invalid-password-2026!",
            })
            invalid_login_body = html.unescape(
                invalid_login_response.content.decode("utf-8")
            )
            record(
                invalid_login_response.status_code == 200
                and invalid_login_message in invalid_login_body,
                locale,
                "error localizado de credenciales no válidas",
                {"status": invalid_login_response.status_code,
                 "message_present": invalid_login_message in invalid_login_body},
            )
            login_body = html.unescape(
                anonymous_client.get("/acceso/").content.decode("utf-8")
            )
            record(
                all(copy in login_body for copy in login_copy),
                locale,
                "texto funcional localizado de acceso y recuperación",
                {"expected": login_copy,
                 "present": [copy in login_body for copy in login_copy]},
            )

            admin_alias = client.get("/admin/")
            record(
                admin_alias.status_code == 302
                and admin_alias.headers.get("Location") == "/administracion/usuarios/",
                locale,
                "alias administrativo redirige a usuarios",
                {"status": admin_alias.status_code,
                 "location": admin_alias.headers.get("Location")},
            )

            logout_client = Client()
            logout_client.force_login(root)
            logout_response = logout_client.post("/salir/")
            record(
                logout_response.status_code == 302
                and logout_response.headers.get("Location") == "/acceso/",
                locale,
                "cierre de sesión redirige al acceso",
                {"status": logout_response.status_code,
                 "location": logout_response.headers.get("Location")},
            )

            uid = urlsafe_base64_encode(force_bytes(recipient.pk))
            bad_token_client = Client()
            bad_token_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            bad_token_path = f"/cuenta/restablecer/{uid}/invalid-token/"
            bad_token_response = bad_token_client.get(bad_token_path, follow=True)
            bad_token_body = html.unescape(
                bad_token_response.content.decode("utf-8")
            )
            record(
                bad_token_response.status_code == 200
                and reset_invalid_link in bad_token_body,
                locale,
                "estado localizado para enlace de restablecimiento inválido",
                {"status": bad_token_response.status_code,
                 "message_present": reset_invalid_link in bad_token_body},
            )

            reset_client = Client()
            reset_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            recipient.refresh_from_db()
            token = default_token_generator.make_token(recipient)
            reset_url = f"/cuenta/restablecer/{uid}/{token}/"
            reset_page = reset_client.get(reset_url, follow=True)
            reset_body = html.unescape(reset_page.content.decode("utf-8"))
            reset_path = reset_page.request["PATH_INFO"]
            record(
                reset_page.status_code == 200
                and all(label in reset_body for label in reset_password_labels),
                locale,
                "formulario válido de restablecimiento y sus rótulos",
                {"status": reset_page.status_code, "path": reset_path,
                 "expected": reset_password_labels,
                 "present": [label in reset_body for label in reset_password_labels]},
            )
            mismatch_reset = reset_client.post(reset_path, {
                "new_password1": "New-Synthetic-Reset-2026!",
                "new_password2": "Different-Synthetic-Reset-2026!",
            }, follow=True)
            mismatch_reset_body = html.unescape(
                mismatch_reset.content.decode("utf-8")
            )
            record(
                mismatch_reset.status_code == 200
                and password_mismatch in mismatch_reset_body,
                locale,
                "error localizado de confirmación en restablecimiento",
                {"status": mismatch_reset.status_code,
                 "message_present": password_mismatch in mismatch_reset_body},
            )
            recovery_submit_client = Client()
            recovery_submit_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            cache.clear()
            recovery_submit = recovery_submit_client.post("/cuenta/recuperar/", {
                "email": recipient.email,
            })
            recovery_queued = AccountMail.objects.filter(
                user=recipient, status="pending"
            ).latest("pk")
            record(
                recovery_submit.status_code == 302
                and recovery_submit.headers.get("Location") == "/cuenta/recuperar/solicitado/"
                and recovery_queued.language == locale,
                locale,
                "solicitud de recuperación guarda locale sin revelar existencia de cuenta",
                {"status": recovery_submit.status_code,
                 "location": recovery_submit.headers.get("Location"),
                 "queued_locale": recovery_queued.language},
            )
            valid_reset = reset_client.post(reset_path, {
                "new_password1": "New-Synthetic-Reset-2026!",
                "new_password2": "New-Synthetic-Reset-2026!",
            }, follow=True)
            valid_reset_body = html.unescape(valid_reset.content.decode("utf-8"))
            with translation.override(locale):
                completed_heading = str(_("Contraseña guardada"))
            record(
                valid_reset.status_code == 200
                and valid_reset.request["PATH_INFO"] == "/cuenta/restablecida/"
                and completed_heading in valid_reset_body,
                locale,
                "cambio de contraseña válido llega al estado final localizado",
                {"status": valid_reset.status_code,
                 "path": valid_reset.request["PATH_INFO"],
                 "heading_present": completed_heading in valid_reset_body},
            )
            from django.utils.http import parse_header_parameters
            from urllib.parse import unquote

            _disposition, disposition_params = parse_header_parameters(
                sample_response.get("Content-Disposition", "")
            )
            sample_download_name = disposition_params.get("filename")
            if sample_download_name is None:
                encoded_name = disposition_params.get("filename*", "")
                sample_download_name = unquote(
                    encoded_name.removeprefix("utf-8''")
                )
            record(
                sample_response.status_code == 200
                and sample_response["Content-Type"].startswith("text/csv")
                and sample_download_name == sample_filename
                and sample_response.content.splitlines()[0] == csv_bytes().splitlines()[0],
                locale,
                "nombre localizado del CSV sintético de administración",
                {"status": sample_response.status_code,
                 "filename": sample_download_name,
                 "expected_filename": sample_filename,
                 "stable_csv_header": sample_response.content.splitlines()[0] == csv_bytes().splitlines()[0]},
            )

            invalid_decision = client.post(
                f"/administracion/cortes/{synthetic_delivery.pk}/estado/",
                {"action": "publish", "reason": "x"},
            )
            invalid_decision_body = html.unescape(
                invalid_decision.content.decode("utf-8")
            )
            record(
                invalid_decision.status_code == 400
                and min_length_message in invalid_decision_body,
                locale,
                "error localizado de longitud mínima en motivo administrativo",
                {"status": invalid_decision.status_code,
                 "expected_message": min_length_message,
                 "message_present": min_length_message in invalid_decision_body},
            )
            oversized_decision = client.post(
                f"/administracion/cortes/{synthetic_delivery.pk}/estado/",
                {"action": "publish", "reason": "x" * 251},
            )
            oversized_body = html.unescape(oversized_decision.content.decode("utf-8"))
            record(
                oversized_decision.status_code == 400
                and max_length_message in oversized_body,
                locale,
                "error localizado de longitud máxima en motivo administrativo",
                {"status": oversized_decision.status_code,
                 "expected_message": max_length_message,
                 "message_present": max_length_message in oversized_body},
            )

            login_client = Client()
            login_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            login_response = login_client.get("/acceso/")
            login_body = login_response.content.decode("utf-8")
            record(
                login_response.status_code == 200
                and f'<html lang="{locale}" dir="{expected_dir}"' in login_body,
                locale,
                "página de acceso sin autenticar",
                {"status": login_response.status_code,
                 "html_locale": f'<html lang="{locale}" dir="{expected_dir}"' in login_body},
            )
            csrf_client = Client(enforce_csrf_checks=True)
            csrf_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            csrf_response = csrf_client.post("/acceso/", {})
            csrf_body = html.unescape(csrf_response.content.decode("utf-8"))
            record(
                csrf_response.status_code == 403
                and csrf_heading in csrf_body
                and csrf_intro in csrf_body,
                locale,
                "mensaje localizado de sesión CSRF caducada",
                {"status": csrf_response.status_code,
                 "heading_present": csrf_heading in csrf_body,
                 "intro_present": csrf_intro in csrf_body,
                 "expected_heading": csrf_heading,
                 "body_excerpt": csrf_body[csrf_body.find('<main'):csrf_body.find('</main>') + 7]},
            )

            invalid_form = client.post(
                "/administracion/usuarios/nuevo/",
                {
                    "username": "invalid<name",
                    "first_name": "Usuario",
                    "last_name": "Prueba",
                    "email": "invalid-name@example.invalid",
                    "role": "reader",
                    "confirm_password": "Synthetic-review-2026!",
                },
            )
            invalid_body = html.unescape(invalid_form.content.decode("utf-8"))
            record(
                invalid_form.status_code == 200
                and username_rule_message in invalid_body,
                locale,
                "mensaje de validación del servidor",
                {"status": invalid_form.status_code,
                 "localized_message_present": username_rule_message in invalid_body},
            )

            invalid_contact_form = client.post(
                "/administracion/usuarios/nuevo/",
                {
                    "username": "valid_user",
                    "first_name": "Usuario",
                    "last_name": "Prueba",
                    "email": "correo-invalido",
                    "role": "unknown-role",
                    "confirm_password": "Synthetic-review-2026!",
                },
            )
            invalid_contact_body = html.unescape(
                invalid_contact_form.content.decode("utf-8")
            )
            record(
                invalid_contact_form.status_code == 200
                and invalid_email_message in invalid_contact_body
                and invalid_choice_message in invalid_contact_body,
                locale,
                "errores localizados de correo y selector inválidos",
                {"status": invalid_contact_form.status_code,
                 "email_present": invalid_email_message in invalid_contact_body,
                 "choice_present": invalid_choice_message in invalid_contact_body},
            )

            invalid_csv_client = Client()
            invalid_csv_client.cookies[settings.LANGUAGE_COOKIE_NAME] = locale
            invalid_csv_client.force_login(root)
            invalid_csv = invalid_csv_client.post(
                "/administracion/cortes/",
                {
                    "title": "Carga sintética inválida",
                    "synthetic": "on",
                    "file": SimpleUploadedFile(
                        "invalid.csv", b"wrong-header\n" + locale.encode("ascii") + b"\n1\n"
                    ),
                },
            )
            invalid_csv_body = html.unescape(invalid_csv.content.decode("utf-8"))
            record(
                invalid_csv.status_code == 200 and csv_structure_error in invalid_csv_body,
                locale,
                "error CSV localizado en administración",
                {"status": invalid_csv.status_code,
                 "translated_error_present": csv_structure_error in invalid_csv_body,
                 "expected_message": csv_structure_error,
                 "body_excerpt": invalid_csv_body[invalid_csv_body.find('<main'):invalid_csv_body.find('</main>') + 7]},
            )

            catalog = client.get("/jsi18n/")
            catalog_body = catalog.content.decode("utf-8")
            women_present = javascript_has(catalog_body, women)
            frequency_present = javascript_has(catalog_body, frequency)
            record(
                catalog.status_code == 200 and women_present and frequency_present,
                locale,
                "catálogo JavaScript y mensajes de gráfico",
                {"status": catalog.status_code,
                 "women_present": women_present,
                 "frequency_present": frequency_present},
            )

            invitation(recipient, language=locale)
            queued = AccountMail.objects.filter(user=recipient, status="pending").latest("pk")
            Command().handle(watch=False)
            queued.refresh_from_db()
            sent = mail.outbox.pop()
            with translation.override(locale):
                expected_subject = str(_("Establecer contraseña · RNC"))
                expected_template = str(_(
                    "Se ha solicitado establecer una contraseña para su cuenta RNC.\n\n"
                    "%(link)s\n\n"
                    "El enlace vence en una hora y solo puede utilizarse una vez. "
                    "Si no reconoce esta solicitud, contacte con soporte."
                ))
            body_prefix, body_suffix = expected_template.split("%(link)s", 1)
            body_matches = body_prefix in sent.body and body_suffix.strip() in sent.body
            record(
                queued.language == locale and queued.status == "sent"
                and sent.subject == expected_subject and body_matches,
                locale,
                "correo de recuperación con locale en cola",
                {"queued_locale": queued.language, "status": queued.status,
                 "subject_matches_catalog": sent.subject == expected_subject,
                 "body_matches_catalog": body_matches},
            )

        report = {
            "success": not errors,
            "profile": "Django Client; temp SQLite, temp .mo copies, synthetic accounts and in-memory email",
            "draft_compiled_catalogs": len(compiled),
            "checks": results,
            "failures": errors,
        }
        output = ROOT / "docs" / "translation-admin-review.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"success": report["success"], "checks": len(results),
                          "failures": len(errors), "output": str(output)}, ensure_ascii=False))
        if errors:
            print(json.dumps({"failed_checks": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(run())
