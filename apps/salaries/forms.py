from django import forms
from django.contrib.auth import get_user_model

from .models import EmployeeSalary, SalaryMonth, Payment

User = get_user_model()

INPUT_CLASSES = 'w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'


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
