import uuid
from django.conf import settings
from django.db import models


class Delivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    checksum = models.CharField(max_length=64, unique=True)
    storage_key = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    row_count = models.PositiveIntegerField(default=0)
    person_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        default="validated",
        choices=[
            ("rejected", "Rechazado"),
            ("validated", "Validado"),
            ("published", "Publicado"),
            ("revoked", "Revocado"),
        ],
    )
    report = models.JSONField(default=dict)
    published_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("operate_deliveries", "Gestionar entregas sintéticas"),
            ("publish_deliveries", "Publicar y revocar cortes sintéticos"),
        ]


class Publication(models.Model):
    # Singleton pointer: a release replaces the complete previous synthetic dataset.
    key = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    delivery = models.ForeignKey(Delivery, null=True, on_delete=models.PROTECT)


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=100)
    reason = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AccountPolicy(models.Model):
    class Meta:
        permissions = [("manage_accounts", "Gestionar cuentas del portal")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    must_change_password = models.BooleanField(default=False)


class AccountMail(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=12, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)
