from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import EmployeeSalary, Payment, SalaryMonth

User = get_user_model()

INPUT_CLASSES = 'w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'

MONTH_CHOICES = [
    (1, 'January'),
    (2, 'February'),
    (3, 'March'),
    (4, 'April'),
    (5, 'May'),
    (6, 'June'),
    (7, 'July'),
    (8, 'August'),
    (9, 'September'),
    (10, 'October'),
    (11, 'November'),
    (12, 'December'),
]


class EmployeeSalaryForm(forms.ModelForm):
    class Meta:
        model = EmployeeSalary
        fields = ['user', 'base_salary', 'currency']
        widgets = {
            'user': forms.Select(attrs={'class': INPUT_CLASSES}),
            'base_salary': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'currency': forms.Select(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show non-staff users who don't have a salary configuration yet
        # Staff users (admins) are not considered employees for salary purposes
        users_with_salary = EmployeeSalary.objects.values_list('user_id', flat=True)
        self.fields['user'].queryset = User.objects.filter(is_staff=False).exclude(id__in=users_with_salary)
        self.fields['user'].label = 'Employee'


class SalaryMonthForm(forms.ModelForm):
    month = forms.ChoiceField(choices=MONTH_CHOICES, widget=forms.Select(attrs={'class': INPUT_CLASSES}))

    class Meta:
        model = SalaryMonth
        fields = ['year', 'month', 'expected_amount']
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'min': 2020,
                'max': 2100,
            }),
            'expected_amount': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': '0.00',
                'step': '0.01',
            }),
        }

    def __init__(self, *args, employee_salary=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee_salary = employee_salary

        # Only pre-fill defaults for NEW records (not when editing)
        is_new = not self.instance.pk

        if is_new and not self.data:
            # Pre-fill with current date for new records
            now = timezone.now()
            self.initial['year'] = now.year
            self.initial['month'] = now.month

            # Pre-fill expected_amount with base salary for new records
            if employee_salary:
                self.initial['expected_amount'] = employee_salary.base_salary

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        month = cleaned_data.get('month')

        if year and month and self.employee_salary:
            # Convert month to int if it's a string (from form choice)
            month = int(month)
            cleaned_data['month'] = month

            # Check if this year/month already exists for this employee
            # Exclude the current instance when editing
            qs = SalaryMonth.objects.filter(
                employee_salary=self.employee_salary,
                year=year,
                month=month
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError(
                    f'A salary entry for {MONTH_CHOICES[month - 1][1]} {year} already exists for this employee.'
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.employee_salary:
            instance.employee_salary = self.employee_salary
        if commit:
            instance.save()
        return instance


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['salary_month', 'amount', 'payment_date', 'payment_method', 'notes']
        widgets = {
            'salary_month': forms.Select(attrs={'class': INPUT_CLASSES}),
            'amount': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'payment_date': forms.DateInput(attrs={
                'class': INPUT_CLASSES,
                'type': 'date',
            }),
            'payment_method': forms.Select(attrs={'class': INPUT_CLASSES}),
            'notes': forms.Textarea(attrs={
                'class': INPUT_CLASSES,
                'rows': 3,
                'placeholder': 'Optional notes about this payment...',
            }),
        }

    def __init__(self, *args, employee_salary=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee_salary = employee_salary

        # Notes is optional
        self.fields['notes'].required = False

        # Default payment_date to today for new records only
        is_new = not self.instance.pk
        if is_new and not self.data:
            self.initial['payment_date'] = timezone.now().date()

        # Filter salary_month queryset to only show months for this employee
        if employee_salary:
            months_qs = SalaryMonth.objects.filter(
                employee_salary=employee_salary
            ).order_by('-year', '-month')
            self.fields['salary_month'].queryset = months_qs

            # Customize labels to show "Month Year (remaining amount)"
            self.fields['salary_month'].label_from_instance = self._format_month_label
        else:
            self.fields['salary_month'].queryset = SalaryMonth.objects.none()

    def _format_month_label(self, month_obj):
        """Format salary month label as 'Month Year (remaining amount)'."""
        return f'{month_obj.month_name} {month_obj.year} ({month_obj.remaining} remaining)'
