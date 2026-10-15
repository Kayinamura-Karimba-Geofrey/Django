from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Student
from .roles import TEACHER_GROUP

User = get_user_model()


class StudentForm(forms.ModelForm):
    """Create/update a student record.

    ``user`` is deliberately not a raw ``fields = '__all__'`` field: the
    account it links to must not be a teacher/superuser and must not already
    own a record, so the choices are scoped in ``linkable_users()`` (keeping
    the account already linked to the record being edited selectable).
    """

    class Meta:
        model = Student
        fields = ['user', 'first_name', 'last_name', 'email', 'course']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-select'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'type': 'email'}),
            'course': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'user': 'Linked user account',
            'first_name': 'First name',
            'last_name': 'Last name',
            'email': 'E-mail address',
            'course': 'Course',
        }
        help_texts = {
            'user': (
                'Optional. Only unlinked, non-teacher accounts are offered; '
                'a student user sees exactly this record after signing in.'
            ),
            'email': 'Must be unique; stored in lower case.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = self.linkable_users()

    def linkable_users(self):
        """Accounts that may own a record: unlinked, and not a teacher."""
        eligible = (
            User.objects.filter(student_record__isnull=True, is_superuser=False)
            .exclude(groups__name=TEACHER_GROUP)
            .order_by(User.USERNAME_FIELD)
        )
        instance = getattr(self, 'instance', None)
        if instance is not None and instance.pk and instance.user_id:
            # Keep the account already linked to this record selectable.
            eligible = User.objects.filter(
                Q(pk=instance.user_id) | Q(pk__in=eligible.values('pk'))
            ).order_by(User.USERNAME_FIELD)
        return eligible

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean(self):
        cleaned = super().clean()
        for field in ('first_name', 'last_name', 'course'):
            value = cleaned.get(field)
            if isinstance(value, str):
                cleaned[field] = value.strip()
        return cleaned
