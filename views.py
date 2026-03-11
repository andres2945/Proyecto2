import json
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q

from .models import CierreCaja, Ingrediente, ItemPedido, Pedido, ProductoBase


# ─────────────────────────────────────────────
#  Helpers de roles
# ─────────────────────────────────────────────

def es_admin(user):
    return user.is_staff or user.is_superuser

def es_cajero(user):
    return user.groups.filter(name='cajero').exists() or user.is_staff

def es_cocina(user):
    return user.groups.filter(name='cocina').exists() or user.is_staff


# ─────────────────────────────────────────────
#  LOGIN  (reutilizado del código anterior)
# ─────────────────────────────────────────────

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm

def vista_login(request):
    if request.user.is_authenticated:
        return _redirigir_por_rol(request.user)

    form = AuthenticationForm(data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return _redirigir_por_rol(user)

    return render(request, 'pedidos/login.html', {'form': form})

def vista_logout(request):
    logout(request)
    return redirect('login')

def _redirigir_por_rol(user):
    if es_admin(user):
        return redirect('admin_dashboard')
    if es_cocina(user):
        return redirect('cocina')
    return redirect('cajero')


# ─────────────────────────────────────────────
#  CAJERO
# ─────────────────────────────────────────────

@login_required
def cajero(request):
    """Pantalla principal del cajero: lista pedidos activos + catalogo."""
    productos = ProductoBase.objects.filter(activo=True).prefetch_related(
        'ingredientes'
    )
    pedidos_activos = Pedido.objects.filter(
        estado__in=[Pedido.Estado.PENDIENTE, Pedido.Estado.PAGADO]
    ).prefetch_related('items__producto_base', 'items__ingredientes').order_by('-creado_en')

    return render(request, 'pedidos/cajero.html', {
        'productos': productos,
        'pedidos_activos': pedidos_activos,
    })


@login_required
@require_POST
def crear_pedido(request):
    """Crea un pedido vacío y devuelve su id."""
    nombre_cliente = request.POST.get('nombre_cliente', '').strip()
    pedido = Pedido.objects.create(
        cajero=request.user,
        nombre_cliente=nombre_cliente or None,
    )
    return JsonResponse({'ok': True, 'pedido_id': pedido.id})


@login_required
@require_POST
def agregar_item(request, pedido_id):
    """Agrega un ItemPedido al pedido. Recibe JSON."""
    pedido = get_object_or_404(Pedido, id=pedido_id)
    if not pedido.es_editable:
        return JsonResponse({'ok': False, 'error': 'El pedido ya no es editable.'}, status=400)

    data = json.loads(request.body)
    producto = get_object_or_404(ProductoBase, id=data['producto_id'], activo=True)

    item = ItemPedido.objects.create(
        pedido=pedido,
        producto_base=producto,
        cantidad=int(data.get('cantidad', 1)),
        notas=data.get('notas', ''),
    )

    # Solo ingredientes que pertenezcan a ese producto base
    ingrediente_ids = data.get('ingredientes', [])
    ingredientes = Ingrediente.objects.filter(
        id__in=ingrediente_ids,
        producto_base=producto,
        activo=True
    )
    item.ingredientes.set(ingredientes)
    item.calcular_subtotal()
    pedido.recalcular_total()

    return JsonResponse({'ok': True, 'item_id': item.id, 'subtotal': str(item.subtotal)})


@login_required
@require_POST
def duplicar_item(request, item_id):
    """Duplica un item existente dentro del mismo pedido."""
    original = get_object_or_404(ItemPedido, id=item_id)
    pedido = original.pedido

    if not pedido.es_editable:
        return JsonResponse({'ok': False, 'error': 'El pedido ya no es editable.'}, status=400)

    nuevo = ItemPedido.objects.create(
        pedido=pedido,
        producto_base=original.producto_base,
        cantidad=original.cantidad,
        notas=original.notas,
        subtotal=original.subtotal,
    )
    nuevo.ingredientes.set(original.ingredientes.all())
    pedido.recalcular_total()

    return JsonResponse({'ok': True, 'nuevo_item_id': nuevo.id})


@login_required
@require_POST
def eliminar_item(request, item_id):
    """Elimina un item del pedido."""
    item = get_object_or_404(ItemPedido, id=item_id)
    pedido = item.pedido

    if not pedido.es_editable:
        return JsonResponse({'ok': False, 'error': 'El pedido ya no es editable.'}, status=400)

    item.delete()
    pedido.recalcular_total()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def marcar_pagado(request, pedido_id):
    """Cajero marca el pedido como pagado → pasa a cocina."""
    pedido = get_object_or_404(Pedido, id=pedido_id)
    if pedido.estado != Pedido.Estado.PENDIENTE:
        return JsonResponse({'ok': False, 'error': 'Estado inválido.'}, status=400)

    pedido.estado = Pedido.Estado.PAGADO
    pedido.pagado_en = timezone.now()
    pedido.save(update_fields=['estado', 'pagado_en'])
    return JsonResponse({'ok': True})


@login_required
def detalle_pedido_json(request, pedido_id):
    """Devuelve el detalle completo de un pedido en JSON (para el cajero)."""
    pedido = get_object_or_404(Pedido, id=pedido_id)
    items = []
    for item in pedido.items.prefetch_related('ingredientes').select_related('producto_base'):
        items.append({
            'id': item.id,
            'producto': item.producto_base.nombre,
            'cantidad': item.cantidad,
            'ingredientes': [i.nombre for i in item.ingredientes.all()],
            'notas': item.notas,
            'subtotal': str(item.subtotal),
        })
    return JsonResponse({
        'pedido_id': pedido.id,
        'estado': pedido.estado,
        'es_editable': pedido.es_editable,
        'total': str(pedido.total),
        'nombre_cliente': pedido.nombre_cliente,
        'items': items,
    })


# ─────────────────────────────────────────────
#  COCINA
# ─────────────────────────────────────────────

@login_required
def cocina(request):
    """Pantalla de cocina: solo pedidos pagados, aceptados."""
    pedidos = Pedido.objects.filter(
        estado__in=[Pedido.Estado.PAGADO, Pedido.Estado.ACEPTADO]
    ).prefetch_related('items__producto_base', 'items__ingredientes').order_by('pagado_en')

    return render(request, 'pedidos/cocina.html', {'pedidos': pedidos})


@login_required
@require_POST
def aceptar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    if pedido.estado != Pedido.Estado.PAGADO:
        return JsonResponse({'ok': False, 'error': 'El pedido no está en estado PAGADO.'}, status=400)

    pedido.estado = Pedido.Estado.ACEPTADO
    pedido.cocinero = request.user
    pedido.aceptado_en = timezone.now()
    pedido.save(update_fields=['estado', 'cocinero', 'aceptado_en'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def marcar_listo(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    if pedido.estado != Pedido.Estado.ACEPTADO:
        return JsonResponse({'ok': False, 'error': 'El pedido no está ACEPTADO.'}, status=400)

    pedido.estado = Pedido.Estado.LISTO
    pedido.listo_en = timezone.now()
    pedido.save(update_fields=['estado', 'listo_en'])
    return JsonResponse({'ok': True})


# ─────────────────────────────────────────────
#  ADMIN
# ─────────────────────────────────────────────

@login_required
@user_passes_test(es_admin)
def admin_dashboard(request):
    """Dashboard principal del administrador."""
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())

    ventas_hoy = Pedido.objects.filter(
        estado__in=[Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO],
        pagado_en__date=hoy
    ).aggregate(total=Sum('total'), cantidad=Count('id'))

    ventas_semana = Pedido.objects.filter(
        estado__in=[Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO],
        pagado_en__date__gte=inicio_semana
    ).aggregate(total=Sum('total'))

    # Ventas por producto (top 5)
    top_productos = (
        ItemPedido.objects
        .filter(pedido__estado__in=[Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO],
                pedido__pagado_en__date=hoy)
        .values('producto_base__nombre')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    pedidos_recientes = Pedido.objects.all().select_related('cajero', 'cocinero')[:20]

    return render(request, 'pedidos/admin_dashboard.html', {
        'ventas_hoy': ventas_hoy,
        'ventas_semana': ventas_semana,
        'top_productos': top_productos,
        'pedidos_recientes': pedidos_recientes,
        'hoy': hoy,
    })


@login_required
@user_passes_test(es_admin)
def cierre_caja(request):
    """Cierre de caja diario."""
    hoy = date.today()
    fecha = request.GET.get('fecha', str(hoy))

    pedidos_del_dia = Pedido.objects.filter(
        estado__in=[Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO],
        pagado_en__date=fecha
    )
    total_sistema = pedidos_del_dia.aggregate(t=Sum('total'))['t'] or 0

    cierre_existente = CierreCaja.objects.filter(fecha=fecha).first()

    if request.method == 'POST':
        total_fisico = request.POST.get('total_fisico')
        observaciones = request.POST.get('observaciones', '')
        cierre, _ = CierreCaja.objects.update_or_create(
            fecha=fecha,
            defaults={
                'admin': request.user,
                'total_sistema': total_sistema,
                'total_fisico': total_fisico,
                'observaciones': observaciones,
            }
        )
        return redirect('cierre_caja')

    return render(request, 'pedidos/cierre_caja.html', {
        'fecha': fecha,
        'total_sistema': total_sistema,
        'pedidos_del_dia': pedidos_del_dia.select_related('cajero'),
        'cierre_existente': cierre_existente,
    })


@login_required
@user_passes_test(es_admin)
def historial_pedidos(request):
    """Historial completo con filtros."""
    fecha_desde = request.GET.get('desde', str(date.today() - timedelta(days=7)))
    fecha_hasta = request.GET.get('hasta', str(date.today()))
    cajero_id   = request.GET.get('cajero', '')
    estado      = request.GET.get('estado', '')

    pedidos = Pedido.objects.filter(
        creado_en__date__range=[fecha_desde, fecha_hasta]
    ).select_related('cajero', 'cocinero').prefetch_related('items__producto_base')

    if cajero_id:
        pedidos = pedidos.filter(cajero_id=cajero_id)
    if estado:
        pedidos = pedidos.filter(estado=estado)

    from django.contrib.auth.models import User
    cajeros = User.objects.filter(pedidos_cajero__isnull=False).distinct()

    return render(request, 'pedidos/historial.html', {
        'pedidos': pedidos,
        'cajeros': cajeros,
        'estados': Pedido.Estado.choices,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
    })


@login_required
@user_passes_test(es_admin)
def reportes(request):
    """Ventas por día y por producto."""
    dias = int(request.GET.get('dias', 7))
    desde = date.today() - timedelta(days=dias)

    ventas_por_dia = (
        Pedido.objects
        .filter(estado__in=[Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO],
                pagado_en__date__gte=desde)
        .extra(select={'dia': 'DATE(pagado_en)'})
        .values('dia')
        .annotate(total=Sum('total'), cantidad=Count('id'))
        .order_by('dia')
    )

    ventas_por_producto = (
        ItemPedido.objects
        .filter(pedido__estado__in=[Pedido.Estado.LISTO, Pedido.Estado.ENTREGADO],
                pedido__pagado_en__date__gte=desde)
        .values('producto_base__nombre')
        .annotate(cantidad=Count('id'), total=Sum('subtotal'))
        .order_by('-total')
    )

    return render(request, 'pedidos/reportes.html', {
        'ventas_por_dia': list(ventas_por_dia),
        'ventas_por_producto': ventas_por_producto,
        'dias': dias,
    })


# ─────────────────────────────────────────────
#  CATÁLOGO (admin gestiona productos)
# ─────────────────────────────────────────────

@login_required
@user_passes_test(es_admin)
def gestion_catalogo(request):
    productos = ProductoBase.objects.prefetch_related('ingredientes').all()
    return render(request, 'pedidos/catalogo.html', {'productos': productos})


@login_required
@user_passes_test(es_admin)
@require_POST
def crear_producto(request):
    nombre      = request.POST.get('nombre', '').strip()
    precio_base = request.POST.get('precio_base')
    descripcion = request.POST.get('descripcion', '')
    if nombre and precio_base:
        ProductoBase.objects.create(nombre=nombre, precio_base=precio_base, descripcion=descripcion)
    return redirect('gestion_catalogo')


@login_required
@user_passes_test(es_admin)
@require_POST
def crear_ingrediente(request):
    producto_id  = request.POST.get('producto_id')
    nombre       = request.POST.get('nombre', '').strip()
    precio_extra = request.POST.get('precio_extra', 0)
    if producto_id and nombre:
        producto = get_object_or_404(ProductoBase, id=producto_id)
        Ingrediente.objects.create(
            producto_base=producto,
            nombre=nombre,
            precio_extra=precio_extra
        )
    return redirect('gestion_catalogo')


@login_required
@user_passes_test(es_admin)
def ingredientes_por_producto(request, producto_id):
    """API JSON: ingredientes activos de un producto (para el cajero)."""
    ingredientes = Ingrediente.objects.filter(
        producto_base_id=producto_id, activo=True
    ).values('id', 'nombre', 'precio_extra')
    return JsonResponse({'ingredientes': list(ingredientes)})