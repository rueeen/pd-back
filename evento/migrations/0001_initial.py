import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import evento.validators
class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
      migrations.CreateModel(name="Asistente",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("nombre",models.CharField(max_length=60)),("apellido",models.CharField(max_length=60)),("rut",models.CharField(max_length=12,unique=True,validators=[evento.validators.validar_rut])),("email",models.EmailField(max_length=254)),("telefono",models.CharField(blank=True,max_length=20)),("tipo",models.CharField(choices=[("estudiante","Estudiante"),("docente","Docente"),("funcionario","Funcionario"),("externo","Externo")],max_length=15)),("area",models.CharField(choices=[("informatica","Informatica"),("diseno","Diseno"),("automatizacion","Automatizacion"),("otra","Otra")],max_length=20)),("carrera",models.CharField(blank=True,max_length=120)),("aporte",models.CharField(choices=[("bebida","Bebida"),("snack","Snack"),("galletas","Galletas"),("desechables","Desechables"),("ninguno","Ninguno")],default="ninguno",max_length=15)),("codigo",models.CharField(blank=True,db_index=True,max_length=12,unique=True)),("completos_asignados",models.PositiveSmallIntegerField(default=2)),("completos_retirados",models.PositiveSmallIntegerField(default=0)),("creado_en",models.DateTimeField(auto_now_add=True))]),
      migrations.CreateModel(name="RetiroCompleto",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("cantidad",models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1),django.core.validators.MaxValueValidator(2)])),("creado_en",models.DateTimeField(auto_now_add=True)),("asistente",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="retiros",to="evento.asistente")),("validado_por",models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL))],options={"ordering":["-creado_en"]})]
