from django.contrib import admin

from .models import Company, Currency


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('legal_name', 'email', 'phone', 'tax_id')


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'symbol', 'symbol_before')
    search_fields = ('code', 'name')

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('code',)
        return ()
