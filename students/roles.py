"""Role definitions.

Roles are implemented with Django's built-in auth groups. Two groups exist:

* ``teacher`` - full CRUD access to student records.
* ``student`` - read-only access to their own linked record.

Superusers always count as teachers.
"""

TEACHER_GROUP = 'teacher'
STUDENT_GROUP = 'student'


def _in_group(user, group_name):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()


def is_teacher(user):
    """True for users allowed to create/edit/delete student records."""
    return _in_group(user, TEACHER_GROUP)


def is_student(user):
    """True for users in the student group (and not a teacher)."""
    return _in_group(user, STUDENT_GROUP)


def role_name(user):
    """Return 'teacher', 'student' or None for display purposes."""
    if not user or not user.is_authenticated:
        return None
    if is_teacher(user):
        return TEACHER_GROUP
    if user.groups.filter(name=STUDENT_GROUP).exists():
        return STUDENT_GROUP
    return None


def ensure_role_permissions(sender, using='default', verbosity=1, apps=None, **kwargs):
    """Keep the role groups' model permissions in sync.

    Connected to the ``post_migrate`` signal from ``StudentsConfig.ready()``
    (the same hook Django itself uses to create permissions), so it runs on
    every ``manage.py migrate`` -- for brand-new databases and existing ones
    alike, and it is idempotent.

    Policy:

    * ``teacher`` gets full CRUD on student records (plus ``auth.view_user``,
      which the Student admin needs for its "user" autocomplete widget).
    * ``student`` deliberately gets **no** model permissions: Django admin
      cannot scope the changelist to "own record only", so handing students
      even ``view_student`` would let a staff-flagged student read every
      record. Students interact through the regular site views, which apply
      the own-record scoping themselves.
    """
    if getattr(sender, 'label', None) != 'students':
        return

    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    from .models import Student

    if apps is None:
        from django.apps import apps as global_apps
        apps = global_apps

    # Ensure the model's default permissions (add/change/delete/view) exist.
    # Django's own receiver normally ran already for this emission, but calling
    # it keeps this independent of INSTALLED_APPS ordering; it only creates
    # rows that are missing.
    create_permissions(sender, verbosity=0, interactive=False, using=using, apps=apps)

    student_ct = ContentType.objects.db_manager(using).get_for_model(Student)
    record_perms = list(Permission.objects.using(using).filter(content_type=student_ct))
    view_user = list(
        Permission.objects.using(using).filter(
            content_type__app_label='auth',
            content_type__model='user',
            codename='view_user',
        )
    )

    teacher, _ = Group.objects.db_manager(using).get_or_create(name=TEACHER_GROUP)
    # also guarantee the student group exists even if 0002 was bypassed
    Group.objects.db_manager(using).get_or_create(name=STUDENT_GROUP)

    # add() only inserts missing rows, so manual adjustments made in the admin
    # are never silently removed, and re-running migrate changes nothing.
    teacher.permissions.add(*(record_perms + view_user))
