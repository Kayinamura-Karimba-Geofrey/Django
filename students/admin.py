from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'course', 'registration_date', 'user')
    search_fields = ('first_name', 'last_name', 'email', 'course')
    list_filter = ('course', 'registration_date')
    autocomplete_fields = ('user',)
    # 'user' is a relational column: fetch it with the row instead of per row.
    list_select_related = True
    list_per_page = 50
    # Set on insert by auto_now_add; read-only documentation, never editable.
    readonly_fields = ('registration_date',)
    ordering = ('last_name', 'first_name')
