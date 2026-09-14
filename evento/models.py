import secrets
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models
from .validators import normalizar_rut, validar_rut

class Asistente(models.Model):
    TIPOS = [(x,x.title()) for x in ("estudiante","docente","funcionario","externo")]
    AREAS = [(x,x.title()) for x in ("informatica","diseno","automatizacion","otra")]
    APORTES = [(x,x.title()) for x in ("bebida","snack","galletas","desechables","ninguno")]
    nombre=models.CharField(max_length=60); apellido=models.CharField(max_length=60)
    rut=models.CharField(max_length=12,unique=True,validators=[validar_rut])
    email=models.EmailField(); telefono=models.CharField(max_length=20,blank=True)
    tipo=models.CharField(max_length=15,choices=TIPOS); area=models.CharField(max_length=20,choices=AREAS)
    carrera=models.CharField(max_length=120,blank=True); aporte=models.CharField(max_length=15,choices=APORTES,default="ninguno")
    codigo=models.CharField(max_length=12,unique=True,db_index=True,blank=True)
    completos_asignados=models.PositiveSmallIntegerField(default=2)
    completos_retirados=models.PositiveSmallIntegerField(default=0)
    creado_en=models.DateTimeField(auto_now_add=True)
    @property
    def completos_disponibles(self): return self.completos_asignados-self.completos_retirados
    def save(self,*args,**kwargs):
        self.rut=validar_rut(self.rut)
        if self.codigo: return super().save(*args,**kwargs)
        for _ in range(20):
            self.codigo="".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(10))
            try: return super().save(*args,**kwargs)
            except IntegrityError:
                self.codigo=""
        raise RuntimeError("No se pudo generar un código único.")
    def __str__(self): return f"{self.nombre} {self.apellido} ({self.rut})"

class RetiroCompleto(models.Model):
    asistente=models.ForeignKey(Asistente,on_delete=models.PROTECT,related_name="retiros")
    cantidad=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(2)])
    validado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    creado_en=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-creado_en"]
