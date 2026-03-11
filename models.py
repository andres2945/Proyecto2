from django.db import models
from django.contrib.auth.models import User


# ─────────────────────────────────────────────
#  CATÁLOGO
# ─────────────────────────────────────────────

class ProductoBase(models.Model):
    """Ej: Hamburguesa, Perro caliente, Salchipapa…"""
    nombre = models.CharField(max_length=100, verbose_name='Nombre')
    precio_base = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio base')
    descripcion = models.TextField(verbose_name='Descripción', blank=True, null=True)
    activo = models.BooleanField(default=True, verbose_name='Activo')
    orden = models.PositiveIntegerField(default=0, verbose_name='Orden de visualización')

    class Meta:
        verbose_name = 'Producto base'
        verbose_name_plural = 'Productos base'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


class Ingrediente(models.Model):
    """Ingrediente extra, siempre ligado a un ProductoBase."""
    producto_base = models.ForeignKey(
        ProductoBase,
        on_delete=models.CASCADE,
        related_name='ingredientes',
        verbose_name='Producto base'
    )
    nombre = models.CharField(max_length=100, verbose_name='Nombre')
    precio_extra = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0, verbose_name='Precio extra'
    )
    activo = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        verbose_name = 'Ingrediente'
        verbose_name_plural = 'Ingredientes'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} ({self.producto_base.nombre})'


# ─────────────────────────────────────────────
#  PEDIDOS
# ─────────────────────────────────────────────

class Pedido(models.Model):
    """Cabecera del pedido."""

    class Estado(models.TextChoices):
        PENDIENTE  = 'PENDIENTE',  'Pendiente de pago'
        PAGADO     = 'PAGADO',     'Pagado – en espera de cocina'
        ACEPTADO   = 'ACEPTADO',   'Aceptado por cocina'
        LISTO      = 'LISTO',      'Listo para recoger'
        ENTREGADO  = 'ENTREGADO',  'Entregado al cliente'
        CANCELADO  = 'CANCELADO',  'Cancelado'

    cajero = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='pedidos_cajero', verbose_name='Cajero'
    )
    cocinero = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedidos_cocinero', verbose_name='Cocinero'
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices,
        default=Estado.PENDIENTE, verbose_name='Estado'
    )
    total = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0, verbose_name='Total'
    )
    nombre_cliente = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name='Nombre del cliente'
    )

    # Trazabilidad de tiempos
    creado_en      = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    pagado_en      = models.DateTimeField(null=True, blank=True, verbose_name='Pagado')
    aceptado_en    = models.DateTimeField(null=True, blank=True, verbose_name='Aceptado')
    listo_en       = models.DateTimeField(null=True, blank=True, verbose_name='Listo')
    entregado_en   = models.DateTimeField(null=True, blank=True, verbose_name='Entregado')

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-creado_en']

    def __str__(self):
        return f'Pedido #{self.id} – {self.estado}'

    def recalcular_total(self):
        """Suma todos los subtotales de los items y actualiza el campo total."""
        total = sum(item.subtotal for item in self.items.all())
        self.total = total
        self.save(update_fields=['total'])

    @property
    def es_editable(self):
        """El cajero puede editar solo mientras no esté aceptado por cocina."""
        return self.estado in (self.Estado.PENDIENTE, self.Estado.PAGADO)


class ItemPedido(models.Model):
    """Una línea dentro del pedido: 1 producto base + sus ingredientes elegidos."""
    pedido = models.ForeignKey(
        Pedido, on_delete=models.CASCADE,
        related_name='items', verbose_name='Pedido'
    )
    producto_base = models.ForeignKey(
        ProductoBase, on_delete=models.PROTECT,
        verbose_name='Producto base'
    )
    ingredientes = models.ManyToManyField(
        Ingrediente, blank=True,
        verbose_name='Ingredientes extras'
    )
    cantidad = models.PositiveIntegerField(default=1, verbose_name='Cantidad')
    subtotal = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0, verbose_name='Subtotal'
    )
    notas = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name='Notas adicionales'
    )

    class Meta:
        verbose_name = 'Ítem de pedido'
        verbose_name_plural = 'Ítems de pedido'

    def __str__(self):
        return f'{self.cantidad}x {self.producto_base.nombre} (Pedido #{self.pedido.id})'

    def calcular_subtotal(self):
        """Precio base + suma de extras, por cantidad."""
        precio = self.producto_base.precio_base
        precio += sum(i.precio_extra for i in self.ingredientes.all())
        self.subtotal = precio * self.cantidad
        self.save(update_fields=['subtotal'])
        return self.subtotal


# ─────────────────────────────────────────────
#  CIERRE DE CAJA
# ─────────────────────────────────────────────

class CierreCaja(models.Model):
    """Registro del cierre diario de caja."""
    admin = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        verbose_name='Administrador'
    )
    fecha = models.DateField(verbose_name='Fecha del cierre')
    total_sistema = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name='Total según sistema'
    )
    total_fisico = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name='Efectivo contado físicamente'
    )
    diferencia = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name='Diferencia (físico - sistema)'
    )
    observaciones = models.TextField(
        blank=True, null=True,
        verbose_name='Observaciones'
    )
    cerrado_en = models.DateTimeField(auto_now_add=True, verbose_name='Fecha/hora de cierre')

    class Meta:
        verbose_name = 'Cierre de caja'
        verbose_name_plural = 'Cierres de caja'
        ordering = ['-fecha']

    def save(self, *args, **kwargs):
        self.diferencia = self.total_fisico - self.total_sistema
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Cierre {self.fecha} – diferencia: ${self.diferencia}'