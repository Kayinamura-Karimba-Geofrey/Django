from .roles import is_teacher, role_name


def user_role(request):
    """Make ``is_teacher`` and ``user_role`` available in every template."""
    user = getattr(request, 'user', None)
    return {
        'is_teacher': is_teacher(user),
        'user_role': role_name(user),
    }
