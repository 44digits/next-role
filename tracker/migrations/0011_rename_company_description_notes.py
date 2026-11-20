from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0010_deletedjobposting"),
    ]

    operations = [
        migrations.RenameField(
            model_name="company",
            old_name="description",
            new_name="notes",
        ),
    ]
