"""Rebuild the public aggregate artifact from the active synthetic delivery."""

from django.core.management.base import BaseCommand, CommandError

from public_site.aggregate_release import publish_release, revoke_public_release
from public_site.services import current_delivery, delivery_records


class Command(BaseCommand):
    help = "Sincronizar el agregado público con el corte sintético activo."

    def handle(self, *args, **options):
        delivery = current_delivery()
        if not delivery:
            revoke_public_release()
            self.stdout.write("No hay corte activo; la publicación pública se vació.")
            return
        if delivery.status != "published":
            raise CommandError("El corte activo no está marcado como publicado.")
        try:
            publish_release(delivery, delivery_records(delivery.storage_key))
        except (OSError, ValueError) as exc:
            raise CommandError(f"No se pudo preparar el agregado público: {exc}") from exc
        self.stdout.write(f"Agregado sintético sincronizado: {delivery.pk}")
