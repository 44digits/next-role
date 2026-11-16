from django.db import migrations
from django.db.models import Max


def backfill_last_contacted_at(apps, schema_editor):
    Contact = apps.get_model("tracker", "Contact")
    Interaction = apps.get_model("tracker", "Interaction")
    database = schema_editor.connection.alias

    latest_interactions = (
        Interaction.objects.using(database)
        .values("contact_id")
        .annotate(latest=Max("occurred_at"))
        .iterator()
    )
    for row in latest_interactions:
        Contact.objects.using(database).filter(pk=row["contact_id"]).update(
            last_contacted_at=row["latest"]
        )


class Migration(migrations.Migration):
    dependencies = [("tracker", "0002_rename_salary_job_salary_range_and_more")]

    operations = [
        migrations.RunPython(
            backfill_last_contacted_at,
            migrations.RunPython.noop,
        )
    ]
