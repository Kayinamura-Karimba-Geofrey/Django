"""Role definitions.

Roles are implemented with Django's built-in auth groups. Two groups exist:

* ``teacher`` - full CRUD access to student records.
* ``student`` - read-only access to their own linked record.

Superusers always count as teachers.

Role lookups hit the database, so the resolved role is cached on the user
object for the lifetime of the request: templates call ``is_teacher`` from the
context processor, the views call it again and ``role_name`` once more, which
would otherwise cost three identical queries per request.
"""

TEACHER_GROUP = 'teacher'
STUDENT_GROUP = 'student'

# Sentinel so "no role" can be cached too (None is a valid result).
_MISSING = object()
_ROLE_CACHE_ATTR = '_school_role_cache'


def role_name(user):
    """Return 'teacher', 'student' or None for the user's role.

    Superusers always resolve to 'teacher'. The result is cached on the user
    instance, so group changes made through the same object are only picked up
    after the cache is cleared (``clear_role_cache``).
    """
    if not user or not user.is_authenticated:
        return None

    cached = getattr(user, _ROLE_CACHE_ATTR, _MISSING)
    if cached is not _MISSING:
        return cached

    if user.is_superuser:
        name = TEACHER_GROUP
    else:
        # One query for both groups, not one per role check.
        groups = set(
            user.groups.filter(name__in=(TEACHER_GROUP, STUDENT_GROUP)).values_list(
                'name', flat=True
            )
        )
        if TEACHER_GROUP in groups:
            name = TEACHER_GROUP
        elif STUDENT_GROUP in groups:
            name = STUDENT_GROUP
        else:
            name = None

    setattr(user, _ROLE_CACHE_ATTR, name)
    return name


def clear_role_cache(user):
    """Forget the cached role (used after changing a user's groups)."""
    try:
        delattr(user, _ROLE_CACHE_ATTR)
    except AttributeError:
        pass


def is_teacher(user):
    """True for users allowed to create/edit/delete student records."""
    return role_name(user) == TEACHER_GROUP


def is_student(user):
    """True for users in the student group (and not a teacher)."""
    return role_name(user) == STUDENT_GROUP


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
