from django.db import models
from django.utils import timezone
from evento.models import Asistente

class Torneo(models.Model):
    MODALIDADES=[("individual","Individual"),("equipo","Equipo")]
    ESTADOS=[(x,x.replace("_"," ").title()) for x in ("inscripcion","sorteado","en_curso","finalizado")]
    nombre=models.CharField(max_length=120); slug=models.SlugField(unique=True); juego=models.CharField(max_length=120)
    modalidad=models.CharField(max_length=10,choices=MODALIDADES); jugadores_por_equipo=models.PositiveSmallIntegerField()
    cupo_equipos=models.PositiveSmallIntegerField(); estado=models.CharField(max_length=15,choices=ESTADOS,default="inscripcion")
    llave_publicada=models.BooleanField(default=False)
    hora_inicio=models.TimeField(); hora_fin=models.TimeField(); reglas=models.TextField(blank=True); cierre_inscripciones=models.DateTimeField()
    @property
    def equipos_confirmados(self): return self.equipos.filter(estado="confirmado").count()
    @property
    def cupos_disponibles(self): return max(0,self.cupo_equipos-self.equipos_confirmados)
    @property
    def inscripciones_abiertas(self): return self.estado=="inscripcion" and timezone.now()<self.cierre_inscripciones
    def __str__(self): return self.nombre
class Equipo(models.Model):
    ESTADOS=[(x,x.title()) for x in ("confirmado","espera","retirado")]
    torneo=models.ForeignKey(Torneo,on_delete=models.CASCADE,related_name="equipos"); nombre=models.CharField(max_length=80)
    capitan=models.ForeignKey(Asistente,on_delete=models.PROTECT,related_name="capitanias"); estado=models.CharField(max_length=12,choices=ESTADOS)
    seed=models.PositiveSmallIntegerField(null=True,blank=True); acreditado=models.BooleanField(default=False)
    acreditado_en=models.DateTimeField(null=True,blank=True); creado_en=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=[("torneo","nombre")]
    def __str__(self): return f"{self.nombre} — {self.torneo}"
class Integrante(models.Model):
    equipo=models.ForeignKey(Equipo,on_delete=models.CASCADE,related_name="integrantes")
    asistente=models.ForeignKey(Asistente,on_delete=models.PROTECT,related_name="participaciones")
    gamertag=models.CharField(max_length=60,blank=True)
    class Meta: unique_together=[("equipo","asistente")]
class PromocionEspera(models.Model):
    torneo=models.ForeignKey(Torneo,on_delete=models.CASCADE,related_name="promociones")
    equipo=models.ForeignKey(Equipo,on_delete=models.PROTECT,related_name="promociones")
    creado_en=models.DateTimeField(auto_now_add=True)
class Partida(models.Model):
    ESTADOS=[(x,x.replace("_"," ").title()) for x in ("pendiente","en_curso","finalizada")]
    SLOTS=[("A","A"),("B","B")]
    torneo=models.ForeignKey(Torneo,on_delete=models.CASCADE,related_name="partidas")
    ronda=models.PositiveSmallIntegerField(); orden=models.PositiveSmallIntegerField()
    equipo_a=models.ForeignKey(Equipo,on_delete=models.SET_NULL,null=True,blank=True,related_name="+")
    equipo_b=models.ForeignKey(Equipo,on_delete=models.SET_NULL,null=True,blank=True,related_name="+")
    score_a=models.PositiveSmallIntegerField(default=0); score_b=models.PositiveSmallIntegerField(default=0)
    ganador=models.ForeignKey(Equipo,on_delete=models.SET_NULL,null=True,blank=True,related_name="victorias")
    por_walkover=models.BooleanField(default=False)
    estado=models.CharField(max_length=12,choices=ESTADOS,default="pendiente")
    siguiente_partida=models.ForeignKey("self",on_delete=models.SET_NULL,null=True,blank=True,related_name="origen")
    slot_siguiente=models.CharField(max_length=1,choices=SLOTS,null=True,blank=True)
    class Meta: unique_together=[("torneo","ronda","orden")]; ordering=["ronda","orden"]
