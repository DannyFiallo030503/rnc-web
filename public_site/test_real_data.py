"""Real-source intake/publication and administrative capability regressions."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest import SkipTest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from .aggregate_release import current_public_release, _read_artifact
from .models import AuditEvent, Delivery
from .services import ingest, transition


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VisualizationCapabilityTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rnc-capability-")
        self.addCleanup(self.temporary.cleanup)
        self.override = override_settings(PUBLIC_RELEASE_ROOT=Path(self.temporary.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()
        User = get_user_model()
        self.root = User.objects.create_superuser("chart_admin", password="Local-test-2026!", email="admin@example.invalid")
        self.operator = User.objects.create_user("chart_operator", password="Local-test-2026!")
        self.operator.groups.add(Group.objects.get(name="operator"))
        self.publisher = User.objects.create_user("chart_publisher", password="Local-test-2026!")
        self.publisher.groups.add(Group.objects.get(name="publisher"))

    def test_anonymous_cannot_configure_visualizations(self):
        self.assertEqual(self.client.post("/administracion/visualizaciones/", {}).status_code, 302)
        self.assertFalse((Path(self.temporary.name)/"visualizations.json").exists())

    def test_operator_cannot_configure_visualizations(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post("/administracion/visualizaciones/", {"map":"on"}).status_code, 403)
        self.assertFalse((Path(self.temporary.name)/"visualizations.json").exists())

    def test_publisher_can_disable_map_and_save_an_audit_event(self):
        self.client.force_login(self.publisher)
        response = self.client.post("/administracion/visualizaciones/", {"trend":"on"})
        self.assertEqual(response.status_code, 302)
        saved = json.loads((Path(self.temporary.name)/"visualizations.json").read_text())
        self.assertEqual(saved, {"map":False,"trend":True})
        self.assertTrue(AuditEvent.objects.filter(action="configure_visualizations",actor=self.publisher).exists())

    def test_invalid_configuration_is_not_treated_as_enabled(self):
        from .chart_availability import availability
        (Path(self.temporary.name)/"visualizations.json").write_text('{"map":"true","trend":null}')
        self.assertEqual(availability(), {"map":False,"trend":False})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RealSourceFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(settings.BASE_DIR).parent / "Nuevo/BD_2022.csv"
        if not cls.source.is_file() or not Path(settings.RNC_POPULATION_XLSX).is_file():
            raise SkipTest("Faltan los archivos reales; no se sustituyen por casos inventados.")
        super().setUpClass()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rnc-real-flow-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.override = override_settings(PRIVATE_STORAGE_ROOT=root/"private",PUBLIC_RELEASE_ROOT=root/"published",EMAIL_FILE_PATH=root/"mail")
        self.override.enable()
        self.addCleanup(self.override.disable)
        _read_artifact.cache_clear()
        self.addCleanup(_read_artifact.cache_clear)
        self.user = get_user_model().objects.create_superuser("real_flow_admin",password="Local-test-2026!",email="real@example.invalid")
        cache.clear()

    def upload(self):
        return SimpleUploadedFile("BD_2022.csv",self.source.read_bytes(),content_type="text/csv")

    def test_real_intake_preserves_case_semantics_and_private_storage(self):
        delivery = ingest(self.upload(), "Corte real de prueba", self.user)
        self.assertEqual(delivery.status,"validated")
        self.assertGreater(delivery.person_count, 0)
        self.assertTrue(delivery.report["person_identity_verified"])
        path=Path(settings.PRIVATE_STORAGE_ROOT)/delivery.storage_key
        self.assertTrue(path.is_file())
        self.assertTrue(path.stat().st_mode & 0o777 == 0o600)
        self.assertTrue(delivery.checksum == hashlib.sha256(self.source.read_bytes()).hexdigest(), "La huella no corresponde al original.")
        self.assertIsNone(current_public_release())

    def test_duplicate_source_is_not_another_delivery(self):
        ingest(self.upload(),"Corte real de prueba",self.user)
        with self.assertRaises(ValueError):ingest(self.upload(),"Otro título",self.user)
        self.assertEqual(Delivery.objects.count(),1)

    def test_source_header_only_is_rejected_without_partial_storage(self):
        content=b"UNIDIDAD,EDAD,FECHAD,MORF,COMP,ETAPA,C10,CICN,NOCASO,SEXO,PROV\n"
        delivery=ingest(SimpleUploadedFile("cabecera.csv",content),"Entrada sin registros",self.user)
        self.assertEqual(delivery.status,"rejected")
        self.assertFalse(delivery.storage_key)
        self.assertFalse(any(Path(settings.PRIVATE_STORAGE_ROOT).rglob("*.csv")))

    def test_real_publication_is_traced_compressed_and_revocable(self):
        delivery=ingest(self.upload(),"Corte real de prueba",self.user)
        with self.captureOnCommitCallbacks(execute=True):
            transition(delivery.pk,"publish",self.user,"Activación real en recursos temporales de prueba.")
        release=current_public_release()
        self.assertTrue(release is not None)
        self.assertFalse(release["synthetic"])
        self.assertEqual(release["options"]["period"],["2022"])
        self.assertTrue(release["person_identity_verified"])
        self.assertTrue(release["provenance"]["original_csv_sha256"] == hashlib.sha256(self.source.read_bytes()).hexdigest(),"Origen del agregado no coincide.")
        self.assertTrue(all(cell["persons"] > 0 for cell in release["cube"][""]))
        self.assertTrue(all("NOCASO" not in cell and "person_id" not in cell for cell in release["cube"][""]))
        pointer=json.loads((Path(settings.PUBLIC_RELEASE_ROOT)/"current.json").read_text())
        self.assertEqual(pointer["encoding"],"gzip")
        response=self.client.get("/consulta/",{"chart":"table","dimension":"site_group","cohort":"adult"})
        self.assertEqual(response.status_code,200)
        self.assertTrue(b"query-table-view" in response.content)
        with self.captureOnCommitCallbacks(execute=True):
            transition(delivery.pk,"revoke",self.user,"Revocación real en recursos temporales de prueba.")
        self.assertIsNone(current_public_release())

    def test_case_count_does_not_default_to_zero_people(self):
        delivery=Delivery.objects.create(title="Metadatos sin casos",checksum="a"*64,created_by=self.user,report={"synthetic":False})
        self.assertIsNone(delivery.person_count)
