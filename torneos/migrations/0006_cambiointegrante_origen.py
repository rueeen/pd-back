from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("torneos", "0005_cambiointegrante")]
    operations = [
        migrations.AddField(
            model_name="cambiointegrante",
            name="origen",
            field=models.CharField(choices=[("admin", "Admin"), ("capitan", "Capitán")], default="admin", max_length=10),
        ),
    ]
