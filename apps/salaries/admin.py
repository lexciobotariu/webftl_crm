from django.contrib import admin

from .models import EmployeeSalary, SalaryMonth, Payment


class SalaryMonthInline(admin.TabularInline):
    model = SalaryMonth
    extra = 0
    fields = ['year', 'month', 'expected_amount']
    readonly_fields = ['created_at']


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ['amount', 'payment_date', 'payment_method', 'notes']
    readonly_fields = ['created_at']


@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(admin.ModelAdmin):
    list_display = ['user', 'base_salary', 'currency', 'created_at']
    list_filter = ['currency']
    search_fields = ['user__name', 'user__email']
    raw_id_fields = ['user']
    inlines = [SalaryMonthInline]


@admin.register(SalaryMonth)
class SalaryMonthAdmin(admin.ModelAdmin):
    list_display = ['employee_salary', 'year', 'month', 'expected_amount', 'status', 'payment_count']
    list_filter = ['year', 'month', 'employee_salary__currency']
    search_fields = ['employee_salary__user__name']
    inlines = [PaymentInline]

    def status(self, obj):
        return obj.status

    def payment_count(self, obj):
        return obj.payment_count


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['salary_month', 'amount', 'payment_date', 'payment_method', 'created_at']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['salary_month__employee_salary__user__name', 'notes']
    date_hierarchy = 'payment_date'
