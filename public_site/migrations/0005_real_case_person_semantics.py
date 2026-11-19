from django.db import migrations, models


def clear_unverified_person_counts(apps, schema_editor):
    Delivery = apps.get_model("public_site", "Delivery")
    for delivery in Delivery.objects.all().iterator():
        if delivery.report.get("synthetic") is False and not delivery.report.get("person_identity_verified"):
            Delivery.objects.filter(pk=delivery.pk).update(person_count=None)


def restore_legacy_placeholder(apps, schema_editor):
    apps.get_model("public_site", "Delivery").objects.filter(person_count__isnull=True).update(person_count=0)


class Migration(migrations.Migration):
    dependencies = [("public_site", "0004_account_mail_language")]
    operations = [
        migrations.AlterField(model_name="delivery", name="person_count", field=models.PositiveIntegerField(blank=True, default=None, null=True)),
        migrations.RunPython(clear_unverified_person_counts, restore_legacy_placeholder),
        migrations.AlterModelOptions(name="delivery", options={"ordering":["-created_at"],"permissions":[("operate_deliveries","Gestionar cargas del RNC"),("publish_deliveries","Publicar y revocar cortes")]}),
    ]
