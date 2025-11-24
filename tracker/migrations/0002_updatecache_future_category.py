from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="updatecache",
            name="category",
            field=models.CharField(
                choices=[("major", "major"), ("minor", "minor"), ("future", "future")],
                max_length=10,
            ),
        ),
    ]

