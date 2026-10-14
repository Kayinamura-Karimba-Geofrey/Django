"""Create or update a user account and put it in the right role group.

Examples:

    manage.py create_school_user jdoe --role teacher --password 'Str0ng-Pass!'
    manage.py create_school_user adal --role student --password 'Str0ng-Pass!' \\
        --link-student adal@example.com

Running the command again with the same username updates that user instead of
failing, so it is safe to re-run (and useful for rotating a password).
"""

import argparse
import getpass
import sys

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from students.models import Student
from students.roles import STUDENT_GROUP, TEACHER_GROUP


class Command(BaseCommand):
    help = (
        'Create or update a user account with the "teacher" or "student" role. '
        'This is the supported way to provision accounts (the README login pair '
        'is development-only). Re-running it updates the same user.'
    )

    def add_arguments(self, parser):
        parser.add_argument('username', help='Login name of the account.')
        parser.add_argument(
            '--role',
            required=True,
            choices=[TEACHER_GROUP, STUDENT_GROUP],
            help='Which role group the user belongs to.',
        )
        parser.add_argument(
            '--password',
            help='Password for the account. Required when creating a new user '
                 'non-interactively; omit to keep the existing password.',
        )
        parser.add_argument('--email', default='', help='Optional e-mail address.')
        parser.add_argument(
            '--staff',
            action=argparse.BooleanOptionalAction,
            default=None,
            help='Whether the account may use the Django admin site '
                 '(teachers default to yes, students to no).',
        )
        parser.add_argument(
            '--link-student',
            metavar='EMAIL',
            help='For --role student: link the student record with this e-mail '
                 'address to the account, so the user sees their own record.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        role = options['role']
        password = options['password']

        user = User.objects.filter(username=username).first()
        created = user is None

        if created:
            if not password:
                if not sys.stdin.isatty():
                    raise CommandError(
                        '--password is required when creating a new user non-interactively.'
                    )
                password = self._prompt_password()
            user = User(username=username)

        if password:
            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                raise CommandError('Password rejected: ' + ' '.join(exc.messages))
            user.set_password(password)

        if options['email']:
            try:
                validate_email(options['email'])
            except ValidationError:
                raise CommandError(f'Invalid e-mail address: {options["email"]!r}')
            user.email = options['email']

        # Teachers can use the Django admin; students cannot. Never strip the
        # staff flag from an existing superuser by accident.
        if options['staff'] is None:
            user.is_staff = user.is_staff if user.is_superuser else (role == TEACHER_GROUP)
        else:
            user.is_staff = options['staff']
        user.save()

        # A user holds exactly one role: drop the other group if present.
        other_name = STUDENT_GROUP if role == TEACHER_GROUP else TEACHER_GROUP
        other_group, _ = Group.objects.get_or_create(name=other_name)
        user.groups.remove(other_group)
        role_group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(role_group)

        linked = None
        if options['link_student']:
            if role != STUDENT_GROUP:
                raise CommandError('--link-student only makes sense with --role student.')
            record = Student.objects.filter(email=options['link_student']).first()
            if record is None:
                raise CommandError(
                    f'No student record with e-mail {options["link_student"]!r}.'
                )
            if record.user_id not in (None, user.pk):
                raise CommandError(
                    f'That record is already linked to user {record.user.username!r}.'
                )
            # free this account from any previously linked record first
            Student.objects.filter(user=user).exclude(pk=record.pk).update(user=None)
            record.user = user
            record.save(update_fields=['user'])
            linked = record

        state = 'Created' if created else 'Updated'
        staff = 'yes' if user.is_staff else 'no'
        summary = (
            f"{state} user '{user.username}' (role={role}, staff={staff}, "
            f"password={'changed' if password else 'unchanged'})"
        )
        if linked:
            summary += f'; linked to student record {linked}'
        self.stdout.write(self.style.SUCCESS(summary))

    def _prompt_password(self):
        first = getpass.getpass('Password: ')
        second = getpass.getpass('Repeat password: ')
        if not first:
            raise CommandError('Password must not be empty.')
        if first != second:
            raise CommandError('Passwords do not match.')
        return first
