import math, random
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Equipo, Partida, Torneo

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
def generar_bracket(torneo):
    torneo=Torneo.objects.select_for_update().get(pk=torneo.pk)
    if torneo.estado=="finalizado": raise ValidationError("No se puede sortear un torneo finalizado.")
    teams=list(torneo.equipos.filter(estado="confirmado"))
    if len(teams)<2: raise ValidationError("Se requieren al menos 2 equipos confirmados.")
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
    torneo.estado="sorteado"; torneo.save(update_fields=["estado"])
    return torneo

def _limpiar_desde(partida,old_winner):
    current=partida.siguiente_partida
    while current:
        old=current.ganador
        if current.equipo_a_id==getattr(old_winner,"id",None): current.equipo_a=None
        if current.equipo_b_id==getattr(old_winner,"id",None): current.equipo_b=None
        current.ganador=None; current.score_a=current.score_b=0; current.estado="pendiente"; current.save()
        old_winner=old; current=current.siguiente_partida

@transaction.atomic
def registrar_resultado(partida,score_a,score_b,usuario=None,reabrir=False):
    partida=Partida.objects.select_for_update().select_related("torneo").get(pk=partida.pk)
    if partida.torneo.estado=="finalizado" and not reabrir:
        raise ValidationError("El torneo está finalizado; debe reabrirlo explícitamente para corregir resultados.")
    if not partida.equipo_a or not partida.equipo_b: raise ValidationError("La partida debe tener ambos equipos definidos.")
    if score_a==score_b: raise ValidationError("El resultado no puede ser empate.")
    if score_a<0 or score_b<0: raise ValidationError("Los marcadores no pueden ser negativos.")
    old=partida.ganador; winner=partida.equipo_a if score_a>score_b else partida.equipo_b
    if old and old != winner: _limpiar_desde(partida,old)
    partida.score_a=score_a; partida.score_b=score_b; partida.ganador=winner; partida.estado="finalizada"; partida.save()
    if partida.siguiente_partida:
        _colocar(partida,winner)
        if partida.torneo.estado in ("sorteado","finalizado"):
            partida.torneo.estado="en_curso"; partida.torneo.save(update_fields=["estado"])
    else: partida.torneo.estado="finalizado"; partida.torneo.save(update_fields=["estado"])
    if partida.torneo.estado=="sorteado":
        partida.torneo.estado="en_curso"; partida.torneo.save(update_fields=["estado"])
    return partida
