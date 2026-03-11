from django.urls import path
from . import views

urlpatterns = [

    # verificar 
    path('',           views.vista_login,  name='login'),
    path('logout/',    views.vista_logout, name='logout'),

    # cajero
    path('cajero/',                              views.cajero,              name='cajero'),
    path('cajero/pedido/nuevo/',                 views.crear_pedido,        name='crear_pedido'),
    path('cajero/pedido/<int:pedido_id>/item/',  views.agregar_item,        name='agregar_item'),
    path('cajero/pedido/<int:pedido_id>/json/',  views.detalle_pedido_json, name='detalle_pedido_json'),
    path('cajero/pedido/<int:pedido_id>/pagar/', views.marcar_pagado,       name='marcar_pagado'),
    path('cajero/item/<int:item_id>/duplicar/',  views.duplicar_item,       name='duplicar_item'),
    path('cajero/item/<int:item_id>/eliminar/',  views.eliminar_item,       name='eliminar_item'),

    #cocina
    path('cocina/',                              views.cocina,          name='cocina'),
    path('cocina/pedido/<int:pedido_id>/aceptar/', views.aceptar_pedido, name='aceptar_pedido'),
    path('cocina/pedido/<int:pedido_id>/listo/',   views.marcar_listo,   name='marcar_listo'),

    # admin
    path('admin-panel/',              views.admin_dashboard,   name='admin_dashboard'),
    path('admin-panel/cierre/',       views.cierre_caja,       name='cierre_caja'),
    path('admin-panel/historial/',    views.historial_pedidos, name='historial_pedidos'),
    path('admin-panel/reportes/',     views.reportes,          name='reportes'),
    path('admin-panel/catalogo/',     views.gestion_catalogo,  name='gestion_catalogo'),
    path('admin-panel/catalogo/producto/nuevo/', views.crear_producto,    name='crear_producto'),
    path('admin-panel/catalogo/ingrediente/nuevo/', views.crear_ingrediente, name='crear_ingrediente'),

    #API REVISAR SI SE DEBE PROTEGER CON LOGIN
    path('api/ingredientes/<int:producto_id>/', views.ingredientes_por_producto, name='api_ingredientes'),
]