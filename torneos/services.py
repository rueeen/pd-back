import math, random
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from evento.models import Asistente
from evento.validators import normalizar_rut
from .models import CambioIntegrante, Equipo, Integrante, Partida, Torneo

MAX_COMODINES_CAPITAN=2

def autorizacion_gestion_capitan(equipo):
    if equipo.torneo.estado in ("sorteado","en_curso","finalizado") or equipo.torneo.llave_publicada:
        return False,"La llave ya fue sorteada; debes hablar con el coordinador."
    if not equipo.torneo.inscripciones_abiertas: return False,"Las inscripciones no están abiertas."
    return True,None

def _related(items,filter_kwargs):
    """Use a prefetched relation when available, and its queryset otherwise."""
    cache=getattr(items.instance,"_prefetched_objects_cache",{})
    cache_name=items.field.remote_field.get_accessor_name()
    if cache_name in cache:
        values=cache[cache_name]
        return [x for x in values if all(getattr(x,k)==v for k,v in filter_kwargs.items())]
    return items.filter(**filter_kwargs)

def comodines_restantes_capitan(equipo):
    if equipo.torneo.estado=="inscripcion": return None
    cambios=_related(equipo.cambios,{"origen":"capitan"})
    usados=len(cambios) if isinstance(cambios,list) else cambios.count()
    return max(0,MAX_COMODINES_CAPITAN-usados)

def autorizacion_reemplazo_capitan(equipo):
    torneo=equipo.torneo
    if torneo.jugadores_por_equipo<=1: return False,"En torneos individuales el reemplazo lo hace el coordinador."
    if torneo.estado not in ("inscripcion","cerrado","sorteado","en_curso"):
        return False,"El torneo ya finalizó; no se pueden cambiar integrantes."
    if equipo.estado=="retirado": return False,"No se pueden cambiar integrantes de un equipo retirado."
    partidas=_related(torneo.partidas,{})
    if isinstance(partidas,list):
        eliminado=any(p.estado=="finalizada" and equipo.pk in (p.equipo_a_id,p.equipo_b_id) and p.ganador_id not in (None,equipo.pk) for p in partidas)
        jugando=any(p.estado=="en_curso" and equipo.pk in (p.equipo_a_id,p.equipo_b_id) for p in partidas)
    else:
        eliminado=(partidas.filter(Q(equipo_a=equipo)|Q(equipo_b=equipo),estado="finalizada")
                   .exclude(Q(ganador=equipo)|Q(ganador=None)).exists())
        jugando=partidas.filter(Q(equipo_a=equipo)|Q(equipo_b=equipo),estado="en_curso").exists()
    if eliminado: return False,"Tu equipo ya fue eliminado."
    if jugando: return False,"No puedes cambiar integrantes mientras tu equipo está jugando; hazlo antes de la siguiente partida."
    if comodines_restantes_capitan(equipo)==0: return False,"Tu equipo ya usó el máximo de comodines."
    return True,None

@transaction.atomic
def reemplazar_integrante(equipo,rut_saliente,rut_entrante,usuario,motivo,detalle="",gamertag="",nombre_equipo=None,forzar=False,origen="admin"):
    equipo=Equipo.objects.select_for_update().select_related("torneo","capitan").get(pk=equipo.pk)
    if equipo.torneo.estado=="finalizado": raise ValidationError("El torneo ya finalizó; no se pueden cambiar integrantes.")
    if equipo.estado=="retirado": raise ValidationError("No se pueden cambiar integrantes de un equipo retirado.")
    rut_saliente=normalizar_rut(rut_saliente); rut_entrante=normalizar_rut(rut_entrante)
    if rut_saliente==rut_entrante: raise ValidationError("El integrante saliente y el entrante deben ser distintos.")
    integrante=Integrante.objects.select_for_update().filter(equipo=equipo,asistente__rut=rut_saliente).first()
    if not integrante: raise ValidationError(f"El RUT {rut_saliente} no es integrante de este equipo.")
    entrante=Asistente.objects.filter(rut=rut_entrante).first()
    if not entrante: raise ValidationError(f"El RUT {rut_entrante} no está registrado; debe registrarse primero al evento.")
    if Integrante.objects.filter(equipo__torneo=equipo.torneo,asistente=entrante).exclude(equipo__estado="retirado").exclude(pk=integrante.pk).exists():
        raise ValidationError(f"El asistente con RUT {rut_entrante} ya participa en un equipo de este torneo.")
    conflicto=(Integrante.objects.select_related("equipo__torneo")
               .filter(asistente=entrante,equipo__torneo__bloque=equipo.torneo.bloque)
               .exclude(equipo__torneo=equipo.torneo).exclude(equipo__estado="retirado").first()
               if equipo.torneo.bloque else None)
    if conflicto and not forzar:
        raise ValidationError(f"El asistente con RUT {rut_entrante} ya participa en {conflicto.equipo.torneo.nombre}, que se juega en el mismo bloque.")
    if motivo not in dict(CambioIntegrante.MOTIVOS): raise ValidationError("Motivo inválido.")
    nombre=str(nombre_equipo).strip() if nombre_equipo is not None else ""
    if nombre and Equipo.objects.filter(torneo=equipo.torneo,nombre__iexact=nombre).exclude(pk=equipo.pk).exists():
        raise ValidationError("El nombre ya está tomado en ese torneo, elige otro.")
    saliente=integrante.asistente
    integrante.asistente=entrante; integrante.gamertag=str(gamertag).strip(); integrante.save(update_fields=["asistente","gamertag"])
    fields=[]
    if equipo.capitan_id==saliente.pk: equipo.capitan=entrante; fields.append("capitan")
    if nombre: equipo.nombre=nombre; fields.append("nombre")
    if fields: equipo.save(update_fields=fields)
    CambioIntegrante.objects.create(equipo=equipo,saliente=saliente,entrante=entrante,motivo=motivo,detalle=str(detalle).strip(),realizado_por=usuario,origen=origen)
    return equipo

def _colocar(partida,equipo):
    target=partida.siguiente_partida
    if not target: return
    setattr(target,"equipo_a" if partida.slot_siguiente=="A" else "equipo_b",equipo)
    target.save(update_fields=["equipo_a","equipo_b"])

def _orden_siembra(size):
    orden=[0]
    while len(orden)<size:
        n=len(orden)
        complementarios=[2*n-1-i for i in orden]
        orden=[valor for pareja in zip(orden,complementarios) for valor in pareja]
    return orden

def _origen_pendiente(partida,slot):
    return partida.origen.filter(slot_siguiente=slot,estado="pendiente").exists()

def _resolver_byes_en_cascada(created):
    cambio=True
    while cambio:
        cambio=False
        for partida in created.values():
            if partida.estado != "pendiente":
                continue
            partida.refresh_from_db()
            puede_llegar_a=_origen_pendiente(partida,"A")
            puede_llegar_b=_origen_pendiente(partida,"B")
            presentes=[equipo for equipo in (partida.equipo_a,partida.equipo_b) if equipo]
            if len(presentes)==1 and not (puede_llegar_a or puede_llegar_b):
                partida.ganador=presentes[0]
                partida.estado="finalizada"
                partida.save(update_fields=["ganador","estado"])
                _colocar(partida,partida.ganador)
                cambio=True
            elif not presentes and not puede_llegar_a and not puede_llegar_b:
                partida.estado="finalizada"
                partida.save(update_fields=["estado"])
                cambio=True

@transaction.atomic
def generar_bracket(torneo,solo_acreditados=False):
    torneo=Torneo.objects.select_for_update().get(pk=torneo.pk)
    if torneo.estado=="inscripcion": raise ValidationError("Primero debes cerrar las inscripciones antes de sortear.")
    if torneo.estado!="cerrado": raise ValidationError("Solo se puede sortear un torneo con las inscripciones cerradas.")
    confirmados=torneo.equipos.filter(estado="confirmado")
    teams=list(confirmados.filter(acreditado=True) if solo_acreditados else confirmados)
    if len(teams)<2:
        if solo_acreditados:
            raise ValidationError(f"Hay {len(teams)} equipos acreditados de {confirmados.count()} inscritos; se requieren al menos 2 para sortear.")
        raise ValidationError("Se requieren al menos 2 equipos confirmados.")
    torneo.partidas.all().delete(); random.shuffle(teams)
    for seed,team in enumerate(teams,1): team.seed=seed; team.save(update_fields=["seed"])
    size=2**math.ceil(math.log2(len(teams)))
    slots=[teams[seed] if seed<len(teams) else None for seed in _orden_siembra(size)]
    rounds=int(math.log2(size))
    created={}
    for r in range(rounds,0,-1):
        for order in range(size//(2**r)):
            created[(r,order)]=Partida.objects.create(torneo=torneo,ronda=r,orden=order)
    for r in range(1,rounds):
        for order in range(size//(2**r)):
            p=created[(r,order)]; p.siguiente_partida=created[(r+1,order//2)]; p.slot_siguiente="A" if order%2==0 else "B"; p.save()
    for order in range(size//2):
        p=created[(1,order)]; p.equipo_a=slots[2*order]; p.equipo_b=slots[2*order+1]
        if bool(p.equipo_a) ^ bool(p.equipo_b):
            p.ganador=p.equipo_a or p.equipo_b; p.estado="finalizada"
        p.save()
        if p.ganador: _colocar(p,p.ganador)
    _resolver_byes_en_cascada(created)
    rotas=[]
    for p in created.values():
        p.refresh_from_db()
        if not p.equipo_a and not p.equipo_b and not p.origen.filter(estado="pendiente").exists():
            rotas.append(p.pk)
    if rotas:
        raise ValidationError("No se pudo generar un bracket válido.")
    torneo.estado="sorteado"; torneo.llave_publicada=True; torneo.save(update_fields=["estado","llave_publicada"])
    return torneo

def _limpiar_desde(partida,old_winner):
    current=partida.siguiente_partida
    while current:
        old=current.ganador
        if current.equipo_a_id==getattr(old_winner,"id",None): current.equipo_a=None
        if current.equipo_b_id==getattr(old_winner,"id",None): current.equipo_b=None
        current.ganador=None; current.score_a=current.score_b=0; current.por_walkover=False; current.estado="pendiente"; current.save()
        old_winner=old; current=current.siguiente_partida

@transaction.atomic
def registrar_resultado(partida,score_a=0,score_b=0,usuario=None,reabrir=False,walkover=None):
    partida=Partida.objects.select_for_update().select_related("torneo").get(pk=partida.pk)
    if partida.torneo.estado=="finalizado" and not reabrir:
        raise ValidationError("El torneo está finalizado; debe reabrirlo explícitamente para corregir resultados.")
    if not partida.equipo_a or not partida.equipo_b: raise ValidationError("La partida debe tener ambos equipos definidos.")
    if walkover not in (None,"a","b"): raise ValidationError("walkover debe ser 'a' o 'b'.")
    if walkover is None and score_a==score_b: raise ValidationError("El resultado no puede ser empate.")
    if score_a<0 or score_b<0: raise ValidationError("Los marcadores no pueden ser negativos.")
    old=partida.ganador
    winner=(partida.equipo_a if walkover=="a" else partida.equipo_b) if walkover else (partida.equipo_a if score_a>score_b else partida.equipo_b)
    if old and old != winner: _limpiar_desde(partida,old)
    partida.score_a=0 if walkover else score_a; partida.score_b=0 if walkover else score_b
    partida.por_walkover=bool(walkover); partida.ganador=winner; partida.estado="finalizada"; partida.save()
    if partida.siguiente_partida:
        _colocar(partida,winner)
        if partida.torneo.estado in ("sorteado","finalizado"):
            partida.torneo.estado="en_curso"; partida.torneo.save(update_fields=["estado"])
    else: partida.torneo.estado="finalizado"; partida.torneo.save(update_fields=["estado"])
    if partida.torneo.estado=="sorteado":
        partida.torneo.estado="en_curso"; partida.torneo.save(update_fields=["estado"])
    return partida
