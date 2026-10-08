from django.contrib import admin

from .models import Client, ClientContact


class ClientContactInline(admin.TabularInline):
    model = ClientContact
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    inlines = [ClientContactInline]
    list_display = ('name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email')
