from django.conf import settings
from django.db import models


class Student(models.Model):
    # Optional link to a user account; used to show a "student" role user
    # only their own record.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='student_record',
        help_text='User account that owns this student record.',
    )
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    course = models.CharField(max_length=100, default="Computer Science")
    registration_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'students'

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
