"""Private mail outbox worker; configure SMTP for real delivery."""

import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from public_site.models import AccountMail
from public_site.accounts import deliver_invitation


class Command(BaseCommand):
    help = "Procesar invitaciones y recuperación; --watch mantiene el worker activo."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        while True:
            for item in (
                AccountMail.objects.filter(status="pending")
                .select_related("user")
                .order_by("pk")[:50]
            ):
                if not AccountMail.objects.filter(pk=item.pk, status="pending").update(
                    status="processing"
                ):
                    continue
                status = "sent"
                try:
                    if item.user.is_active:
                        deliver_invitation(item.user)
                    else:
                        status = "cancelled"
                except Exception:
                    status = "failed"
                AccountMail.objects.filter(pk=item.pk).update(
                    status=status, processed_at=timezone.now()
                )
                self.stdout.write(f"Correo {item.pk}: {status}")
            if not options["watch"]:
                break
            time.sleep(5)
