import csv
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import Throttled
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from .models import Area, Asistente, Carrera, ConfiguracionEvento, RetiroCompleto
from .serializers import AreaCatalogoSerializer, AsistenteSerializer, ConfiguracionEventoSerializer, PaseSerializer, RetiroSerializer
from .services import registrar_retiro
from .validators import normalizar_rut

class ExplainedAnonRateThrottle(AnonRateThrottle):
    message = "Se alcanzó el límite de solicitudes desde esta red. Intenta nuevamente en unos minutos."
    def allow_request(self, request, view):
        if super().allow_request(request, view): return True
        raise Throttled(wait=self.wait(), detail=self.message)
class RegistrationThrottle(ExplainedAnonRateThrottle): scope="registration"
class PassRecoveryThrottle(ExplainedAnonRateThrottle): scope="pass_recovery"
class CatalogoAreasView(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[]
    def get(self,request):
        qs=Area.objects.filter(activa=True).prefetch_related(
            Prefetch("carreras",queryset=Carrera.objects.filter(activa=True),to_attr="carreras_activas")
        )
        return Response(AreaCatalogoSerializer(qs,many=True).data)
class RegistroView(APIView):
    permission_classes=[AllowAny]; throttle_classes=[RegistrationThrottle]
    def post(self,request):
        try: rut=normalizar_rut(request.data.get("rut",""))
        except DjangoValidationError: rut=request.data.get("rut","")
        existing=Asistente.objects.filter(rut=rut).first()
        if existing:
            supplied_email=str(request.data.get("email","")).strip()
            if not supplied_email or supplied_email.casefold() != existing.email.strip().casefold():
                return Response({"detail":"Ese RUT ya está registrado. Si eres tú, ingresa el mismo correo que usaste."},status=status.HTTP_409_CONFLICT)
            return Response(AsistenteSerializer(existing).data|{"recuperado":True})
        s=AsistenteSerializer(data=request.data); s.is_valid(raise_exception=True)
        with transaction.atomic():
            configuracion=ConfiguracionEvento.objects.select_for_update().get_or_create(pk=1)[0]
            if not configuracion.registro_abierto or Asistente.objects.count() >= configuracion.cupo_asistentes:
                detail=configuracion.mensaje_cupos_agotados or "Los cupos para el evento se agotaron."
                return Response({"detail":detail},status=status.HTTP_409_CONFLICT)
            asistente=s.save(completos_asignados=configuracion.completos_por_asistente)
        return Response(AsistenteSerializer(asistente).data,status=status.HTTP_201_CREATED)

def _datos_configuracion(configuracion):
    registrados=Asistente.objects.count()
    return {"registro_abierto":configuracion.registro_abierto,"cupo_asistentes":configuracion.cupo_asistentes,
            "registrados":registrados,"cupos_disponibles":max(0,configuracion.cupo_asistentes-registrados),
            "completos_por_asistente":configuracion.completos_por_asistente,
            "mensaje_cupos_agotados":configuracion.mensaje_cupos_agotados}

class ConfiguracionEventoView(APIView):
    permission_classes=[AllowAny]
    def get(self,request): return Response(_datos_configuracion(ConfiguracionEvento.obtener()))

class AdminConfiguracionEventoView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request): return Response(_datos_configuracion(ConfiguracionEvento.obtener()))
    @transaction.atomic
    def patch(self,request):
        configuracion=ConfiguracionEvento.objects.select_for_update().get_or_create(pk=1)[0]
        serializer=ConfiguracionEventoSerializer(configuracion,data=request.data,partial=True)
        serializer.is_valid(raise_exception=True)
        aplicar=serializer.validated_data.pop("aplicar_a_existentes",False)
        cambia_completos="completos_por_asistente" in serializer.validated_data
        configuracion=serializer.save()
        sin_actualizar=0
        if cambia_completos and aplicar:
            nuevo=configuracion.completos_por_asistente
            sin_actualizar=Asistente.objects.filter(completos_retirados__gt=nuevo).count()
            Asistente.objects.filter(completos_retirados__lte=nuevo).update(completos_asignados=nuevo)
        data=_datos_configuracion(configuracion)
        if cambia_completos and aplicar: data["sin_actualizar"]=sin_actualizar
        return Response(data)
class PaseView(APIView):
    permission_classes=[AllowAny]
    def get(self,request,codigo): return Response(PaseSerializer(get_object_or_404(Asistente,codigo=codigo.upper())).data)
class RecuperarPaseView(APIView):
    permission_classes=[AllowAny]; throttle_classes=[PassRecoveryThrottle]
    def post(self,request):
        detail="No se encontró un registro con esos datos."
        try: rut=normalizar_rut(request.data.get("rut",""))
        except DjangoValidationError: return Response({"detail":detail},status=status.HTTP_404_NOT_FOUND)
        asistente=Asistente.objects.filter(rut=rut).first(); email=str(request.data.get("email","")).strip()
        if not asistente or not email or asistente.email.strip().casefold()!=email.casefold():
            return Response({"detail":detail},status=status.HTTP_404_NOT_FOUND)
        return Response({"codigo":asistente.codigo})
class AdminAsistentesView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        qs=Asistente.objects.all().order_by("-creado_en"); q=request.query_params.get("q")
        if q: qs=qs.filter(Q(nombre__icontains=q)|Q(apellido__icontains=q)|Q(rut__icontains=q)|Q(codigo__icontains=q))
        if request.query_params.get("con_saldo")=="1": qs=qs.filter(completos_retirados__lt=F("completos_asignados"))
        return Response(AsistenteSerializer(qs,many=True).data)
class AdminAsistentesExportView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        response=HttpResponse(content_type="text/csv; charset=utf-8"); response["Content-Disposition"]='attachment; filename="asistentes.csv"'; response.write("\ufeff")
        response.write("# Contiene datos personales. La copia impresa debe destruirse al cierre de la jornada.\r\n")
        writer=csv.writer(response); writer.writerow(["código","nombre","apellido","RUT","tipo","área","carrera","completos asignados","completos retirados"])
        for a in Asistente.objects.select_related("area","carrera").order_by("apellido","nombre"):
            writer.writerow([a.codigo,a.nombre,a.apellido,a.rut,a.tipo,a.area.nombre if a.area else "",a.carrera.nombre if a.carrera else "",a.completos_asignados,a.completos_retirados])
        return response
class AdminAsistenteView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request,codigo): return Response(AsistenteSerializer(get_object_or_404(Asistente,codigo=codigo.upper())).data)
class AdminRetirosView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        qs=RetiroCompleto.objects.select_related("asistente","validado_por").all()[:200]
        return Response(RetiroSerializer(qs,many=True).data)
    def post(self,request):
        attendee=get_object_or_404(Asistente,codigo=str(request.data.get("codigo","")).upper())
        try: cantidad=int(request.data.get("cantidad"))
        except (TypeError,ValueError):
            return Response({"detail":"La cantidad debe ser 1 o 2."},status=status.HTTP_400_BAD_REQUEST)
        try: retiro=registrar_retiro(attendee,cantidad,request.user)
        except DjangoValidationError as exc:
            return Response({"detail":exc.messages[0]},status=status.HTTP_400_BAD_REQUEST)
        return Response(RetiroSerializer(retiro).data,status=201)
class AdminResumenView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        from torneos.models import Torneo
        areas=Area.objects.annotate(total=Count("asistente")).filter(total__gt=0).order_by("-total","orden","nombre")
        carreras=Carrera.objects.annotate(total=Count("asistente")).filter(total__gt=0).select_related("area").order_by("-total","nombre")
        configuracion=ConfiguracionEvento.obtener(); registrados=Asistente.objects.count()
        return Response({"total_registrados":registrados,"cupo_asistentes":configuracion.cupo_asistentes,"cupos_disponibles":max(0,configuracion.cupo_asistentes-registrados),"registro_abierto":configuracion.registro_abierto,"completos_comprometidos":registrados*configuracion.completos_por_asistente,"completos_entregados":RetiroCompleto.objects.aggregate(v=Sum("cantidad"))["v"] or 0,"completos_pendientes":Asistente.objects.aggregate(v=Sum(F("completos_asignados")-F("completos_retirados")))["v"] or 0,"inscritos_por_torneo":[{"slug":t.slug,"nombre":t.nombre,"inscritos":t.equipos.filter(estado="confirmado").count()} for t in Torneo.objects.all()],"aportes_comprometidos":{x["aporte"]:x["total"] for x in Asistente.objects.values("aporte").annotate(total=Count("id"))},"asistentes_por_area":[{"slug":x.slug,"nombre":x.nombre,"total":x.total} for x in areas],"asistentes_por_carrera":[{"slug":x.slug,"nombre":x.nombre,"area":x.area.slug,"total":x.total} for x in carreras]})
