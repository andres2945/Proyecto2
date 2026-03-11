from django.contrib import admin
from .models import Licores

@admin.register(Licores)
class LicoresAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'stock', 'descripcion')
    search_fields = ('titulo',)