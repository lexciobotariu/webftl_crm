from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import EmployeeSalary, SalaryMonth, Payment

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
        # Only show users who don't have a salary configuration yet
        users_with_salary = EmployeeSalary.objects.values_list('user_id', flat=True)
        self.fields['user'].queryset = User.objects.exclude(id__in=users_with_salary)
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

        # Pre-fill with current date
        now = timezone.now()
        if not self.data:
            self.initial['year'] = now.year
            self.initial['month'] = now.month

        # Pre-fill expected_amount with base salary
        if employee_salary and not self.data:
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
            if SalaryMonth.objects.filter(
                employee_salary=self.employee_salary,
                year=year,
                month=month
            ).exists():
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
