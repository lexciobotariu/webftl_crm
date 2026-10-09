from django.contrib import admin

from .models import Estimate, EstimateLine, Invoice, InvoiceLine, Payment, RecurringInvoice


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['number', 'client', 'issue_date', 'due_date', 'tax_rate', 'sent_at']
    list_filter = ['sent_at']
    search_fields = ['number', 'client__name', 'bill_to_name']
    raw_id_fields = ['client']
    inlines = [InvoiceLineInline, PaymentInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'project', 'description', 'quantity', 'unit_price']
    raw_id_fields = ['invoice', 'project']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'date', 'amount', 'note']
    raw_id_fields = ['invoice']


@admin.register(RecurringInvoice)
class RecurringInvoiceAdmin(admin.ModelAdmin):
    list_display = ['template', 'frequency', 'next_date', 'end_date']
    raw_id_fields = ['template', 'created_by']


class EstimateLineInline(admin.TabularInline):
    model = EstimateLine
    extra = 0


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = ['number', 'client', 'issue_date', 'valid_until', 'sent_at', 'accepted_at', 'declined_at']
    search_fields = ['number', 'client__name', 'bill_to_name']
    raw_id_fields = ['client', 'invoice']
    inlines = [EstimateLineInline]
