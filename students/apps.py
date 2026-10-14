from django.apps import AppConfig
from django.db.models.signals import post_migrate


class StudentsConfig(AppConfig):
    name = 'students'

    def ready(self):
        from .roles import ensure_role_permissions

        post_migrate.connect(
            ensure_role_permissions,
            dispatch_uid='students.ensure_role_permissions',
        )
