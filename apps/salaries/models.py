from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum


class EmployeeSalary(models.Model):
    """Salary configuration for an employee (User)."""

    CURRENCY_CHOICES = [
        ('USD', 'USD ($)'),
        ('EUR', 'EUR (€)'),
        ('GBP', 'GBP (£)'),
    ]
    CURRENCY_SYMBOLS = {
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='salary_config'
    )
    base_salary = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='EUR')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Employee salaries'
        ordering = ['user__name']

    def __str__(self):
        return f'{self.user.name} - {self.base_salary} {self.currency}'

    @property
    def currency_symbol(self):
        return self.CURRENCY_SYMBOLS.get(self.currency, '$')


class SalaryMonth(models.Model):
    """A specific month's salary record for an employee."""

    MONTH_NAMES = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]

    employee_salary = models.ForeignKey(
        EmployeeSalary,
        on_delete=models.CASCADE,
        related_name='months'
    )
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1-12
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['employee_salary', 'year', 'month']
        ordering = ['-year', '-month']

    def __str__(self):
        return f'{self.employee_salary.user.name} - {self.month_name} {self.year}'

    @property
    def month_name(self):
        """Return the month name (e.g., 'January')."""
        return self.MONTH_NAMES[self.month]

    @property
    def total_paid(self):
        """Sum of all payments for this month."""
        annotated = getattr(self, 'total_paid_sum', None)
        if annotated is not None:
            return annotated or Decimal('0')
        result = self.payments.aggregate(total=Sum('amount'))['total']
        return result or Decimal('0')

    @property
    def remaining(self):
        """Amount still owed (0 if overpaid)."""
        diff = self.expected_amount - self.total_paid
        return max(diff, Decimal('0'))

    @property
    def bonus_amount(self):
        """Amount paid over expected (0 if not overpaid)."""
        diff = self.total_paid - self.expected_amount
        return max(diff, Decimal('0'))

    @property
    def status(self):
        """Payment status: unpaid, partial, paid, or bonus."""
        total = self.total_paid
        if total == Decimal('0'):
            return 'unpaid'
        elif total < self.expected_amount:
            return 'partial'
        elif total == self.expected_amount:
            return 'paid'
        else:
            return 'bonus'

    @property
    def payment_count(self):
        """Number of payments for this month."""
        return self.payments.count()


class Payment(models.Model):
    """Individual payment transaction."""

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('other', 'Other'),
    ]

    salary_month = models.ForeignKey(
        SalaryMonth,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f'{self.amount} on {self.payment_date.strftime("%d/%m/%Y")}'
