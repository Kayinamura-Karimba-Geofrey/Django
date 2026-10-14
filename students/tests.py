import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.urls import reverse

from .models import Student
from .roles import STUDENT_GROUP, TEACHER_GROUP

User = get_user_model()


class RoleTestCase(TestCase):
    """Base fixture: both groups exist, plus a teacher and a student user."""

    @classmethod
    def setUpTestData(cls):
        # The role groups are created by students migration 0002;
        # get_or_create keeps the tests robust if that ever changes.
        cls.teacher_group, _ = Group.objects.get_or_create(name=TEACHER_GROUP)
        cls.student_group, _ = Group.objects.get_or_create(name=STUDENT_GROUP)

        cls.teacher = User.objects.create_user('teach', password='pass1234!')
        cls.teacher.groups.add(cls.teacher_group)

        cls.student_user = User.objects.create_user(
            'alice', email='alice@example.com', password='pass1234!'
        )
        cls.student_user.groups.add(cls.student_group)
        cls.alice = Student.objects.create(
            first_name='Alice', last_name='Ander',
            email='alice@example.com', user=cls.student_user,
        )
        cls.bob = Student.objects.create(
            first_name='Bob', last_name='Bee', email='bob@example.com',
        )

    def list_url(self):
        return reverse('student_list')

    def create_url(self):
        return reverse('student_create')

    def update_url(self, pk):
        return reverse('student_update', args=[pk])

    def delete_url(self, pk):
        return reverse('student_delete', args=[pk])


class RoleGroupsTests(RoleTestCase):
    def test_groups_created_by_migration(self):
        self.assertTrue(Group.objects.filter(name=TEACHER_GROUP).exists())
        self.assertTrue(Group.objects.filter(name=STUDENT_GROUP).exists())


class AnonymousAccessTests(RoleTestCase):
    """Everything requires login: anonymous users are redirected."""

    def test_anonymous_redirected_to_login_for_every_view(self):
        cases = {
            self.list_url(): 'student_list',
            self.create_url(): 'student_create',
            self.update_url(self.alice.pk): 'student_update',
            self.delete_url(self.alice.pk): 'student_delete',
        }
        for url, name in cases.items():
            with self.subTest(view=name):
                expected = f"{reverse('login')}?next={url}"
                self.assertRedirects(self.client.get(url), expected)

    def test_login_page_uses_our_template(self):
        # django.contrib.admin ships registration/*.html templates that would
        # otherwise shadow ours; the project-level DIRS entry must win.
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'School Portal')


class TeacherAccessTests(RoleTestCase):
    """Teachers have full CRUD access."""

    def setUp(self):
        self.client.force_login(self.teacher)

    def test_can_list_all_students(self):
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')
        self.assertContains(response, 'Bob')
        self.assertTrue(response.context['is_teacher'])
        self.assertEqual(response.context['user_role'], 'teacher')

    def test_can_create_student(self):
        response = self.client.post(self.create_url(), {
            'first_name': 'Carol', 'last_name': 'C',
            'email': 'carol@example.com', 'course': 'Math', 'user': '',
        })
        self.assertRedirects(response, self.list_url())
        self.assertTrue(Student.objects.filter(email='carol@example.com').exists())

    def test_can_update_student(self):
        response = self.client.post(self.update_url(self.bob.pk), {
            'first_name': 'Robert', 'last_name': 'Bee',
            'email': 'bob@example.com', 'course': 'Physics', 'user': '',
        })
        self.assertRedirects(response, self.list_url())
        self.bob.refresh_from_db()
        self.assertEqual(self.bob.first_name, 'Robert')

    def test_can_delete_student(self):
        response = self.client.post(self.delete_url(self.bob.pk))
        self.assertRedirects(response, self.list_url())
        self.assertFalse(Student.objects.filter(pk=self.bob.pk).exists())


class StudentAccessTests(RoleTestCase):
    """Students are read-only and see only their own record."""

    def setUp(self):
        self.client.force_login(self.student_user)

    def test_list_shows_only_own_record(self):
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')
        self.assertNotContains(response, 'Bob')
        self.assertFalse(response.context['is_teacher'])
        self.assertEqual(response.context['user_role'], 'student')

    def test_cannot_create(self):
        for method in (self.client.get, self.client.post):
            response = method(self.create_url())
            self.assertEqual(response.status_code, 403)
        self.assertFalse(Student.objects.filter(email='carol@example.com').exists())

    def test_cannot_update_own_or_others_record(self):
        for pk in (self.alice.pk, self.bob.pk):
            for method in (self.client.get, self.client.post):
                with self.subTest(pk=pk, method=method.__name__):
                    response = method(self.update_url(pk))
                    self.assertEqual(response.status_code, 403)

    def test_cannot_delete(self):
        response = self.client.post(self.delete_url(self.alice.pk))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Student.objects.filter(pk=self.alice.pk).exists())

    def test_no_action_buttons_in_template(self):
        response = self.client.get(self.list_url())
        self.assertNotContains(response, self.create_url())
        self.assertNotContains(response, 'Add New Student')


class UnlinkedStudentTests(RoleTestCase):
    """A student user without a linked record gets a friendly empty state."""

    def setUp(self):
        self.bob_user = User.objects.create_user('bob', password='pass1234!')
        self.bob_user.groups.add(self.student_group)
        self.client.force_login(self.bob_user)

    def test_empty_state_message(self):
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['students']), [])
        self.assertFalse(response.context['student_record_linked'])
        self.assertContains(response, "isn't linked to a student record")


class NoRoleTests(RoleTestCase):
    """Authenticated users with no role get the most restricted view."""

    def setUp(self):
        self.nobody = User.objects.create_user('nobody', password='pass1234!')
        self.client.force_login(self.nobody)

    def test_sees_no_records_and_no_write_access(self):
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['students']), [])
        self.assertIsNone(response.context['user_role'])
        self.assertEqual(self.client.get(self.create_url()).status_code, 403)


class GroupPermissionTests(TestCase):
    """The post_migrate handler keeps role-group permissions in sync.

    These run against a database built from migrations, so they also prove a
    brand-new deployment gets the same permissions as an existing one.
    """

    def test_teacher_group_has_full_record_permissions(self):
        teacher = Group.objects.get(name=TEACHER_GROUP)
        perms = {
            (p.content_type.app_label, p.codename)
            for p in teacher.permissions.select_related('content_type')
        }
        self.assertEqual(
            perms,
            {
                ('students', 'add_student'),
                ('students', 'change_student'),
                ('students', 'delete_student'),
                ('students', 'view_student'),
                ('auth', 'view_user'),  # Student admin's "user" autocomplete
            },
        )

    def test_student_group_has_no_model_permissions(self):
        # Django admin cannot scope its changelist to "own record only", so
        # students must not receive model permissions at all.
        student = Group.objects.get(name=STUDENT_GROUP)
        self.assertEqual(student.permissions.count(), 0)


class AdminAccessTests(RoleTestCase):
    """The assigned permissions have to actually work in the Django admin."""

    def test_teacher_can_manage_records_in_admin(self):
        self.teacher.is_staff = True
        self.teacher.save()
        self.client.force_login(self.teacher)
        changelist = reverse('admin:students_student_changelist')
        self.assertEqual(self.client.get(changelist).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:students_student_add')).status_code, 200)
        self.assertEqual(self.client.get(
            reverse('admin:students_student_change', args=[self.bob.pk])
        ).status_code, 200)

    def test_student_cannot_read_records_through_admin(self):
        # Even with the staff flag flipped on by hand, no model permissions
        # means no record data in the admin.
        self.student_user.is_staff = True
        self.student_user.save()
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('admin:students_student_changelist')).status_code,
            403,
        )


class PasswordChangeTests(RoleTestCase):
    """The password-change endpoints mounted under /accounts/ must work."""

    new_password = 'Nova-Willow-88'

    def test_wrong_current_password_is_rejected(self):
        self.client.force_login(self.student_user)
        response = self.client.post(reverse('password_change'), {
            'old_password': 'definitely-wrong',
            'new_password1': self.new_password,
            'new_password2': self.new_password,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errorlist')
        self.assertFalse(Client().login(username='alice', password=self.new_password))

    def test_password_change_flow(self):
        self.client.force_login(self.student_user)
        url = reverse('password_change')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        # our template, not django.contrib.admin's
        self.assertContains(page, 'Change my password')

        response = self.client.post(url, {
            'old_password': 'pass1234!',
            'new_password1': self.new_password,
            'new_password2': self.new_password,
        })
        self.assertRedirects(response, reverse('password_change_done'))

        # the new password works, the old one no longer does
        fresh = Client()
        self.assertTrue(fresh.login(username='alice', password=self.new_password))
        self.assertFalse(Client().login(username='alice', password='pass1234!'))


class PasswordResetTests(RoleTestCase):
    """The password-reset endpoints (and their e-mail) must work."""

    new_password = 'Cedar-Storm-31'

    def test_reset_flow(self):
        url = reverse('password_reset')
        self.assertEqual(self.client.get(url).status_code, 200)

        response = self.client.post(url, {'email': 'alice@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        # our e-mail body template, not django.contrib.admin's default wording
        self.assertIn('Someone requested a password reset', mail.outbox[0].body)

        match = re.search(r'/accounts/reset/[\w-]+/[\w-]+/', mail.outbox[0].body)
        self.assertIsNotNone(match, 'reset link missing from e-mail body')

        # first visit redirects to a token-free URL (token goes to the session)
        page = self.client.get(match.group(0), follow=True)
        self.assertEqual(page.status_code, 200)
        form_url = page.request['PATH_INFO']

        response = self.client.post(form_url, {
            'new_password1': self.new_password,
            'new_password2': self.new_password,
        })
        self.assertRedirects(response, reverse('password_reset_complete'))

        self.assertTrue(Client().login(username='alice', password=self.new_password))

    def test_reset_flow_for_unknown_address_stays_silent(self):
        response = self.client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)


class CreateSchoolUserCommandTests(TestCase):
    """create_school_user is the supported way to provision role accounts."""

    def test_creates_teacher_with_admin_access(self):
        call_command(
            'create_school_user', 'kofi', '--role', 'teacher',
            '--password', 'Quiet-Moon-51', '--email', 'kofi@example.com',
        )
        user = User.objects.get(username='kofi')
        self.assertTrue(user.check_password('Quiet-Moon-51'))
        self.assertEqual(sorted(user.groups.values_list('name', flat=True)), [TEACHER_GROUP])
        self.assertTrue(user.is_staff)
        self.assertEqual(user.email, 'kofi@example.com')

    def test_creates_student_without_admin_access(self):
        call_command('create_school_user', 'njeri', '--role', 'student',
                     '--password', 'Vast-Quartz-73')
        user = User.objects.get(username='njeri')
        self.assertEqual(sorted(user.groups.values_list('name', flat=True)), [STUDENT_GROUP])
        self.assertFalse(user.is_staff)

    def test_role_membership_is_exclusive(self):
        call_command('create_school_user', 'rot', '--role', 'teacher',
                     '--password', 'Amber-Ledger-84')
        call_command('create_school_user', 'rot', '--role', 'student')
        user = User.objects.get(username='rot')
        self.assertEqual(sorted(user.groups.values_list('name', flat=True)), [STUDENT_GROUP])
        self.assertFalse(user.is_staff)

    def test_password_rotation_on_existing_user(self):
        call_command('create_school_user', 'rot', '--role', 'teacher',
                     '--password', 'Amber-Ledger-84')
        call_command('create_school_user', 'rot', '--role', 'teacher',
                     '--password', 'Amber-Ledger-99')
        user = User.objects.get(username='rot')
        self.assertTrue(user.check_password('Amber-Ledger-99'))
        self.assertFalse(user.check_password('Amber-Ledger-84'))

    def test_rejects_weak_password(self):
        with self.assertRaises(CommandError):
            call_command('create_school_user', 'weaky', '--role', 'teacher',
                         '--password', '12345678')
        self.assertFalse(User.objects.filter(username='weaky').exists())

    def test_new_user_requires_password_non_interactively(self):
        with mock.patch('sys.stdin') as fake_stdin:
            fake_stdin.isatty.return_value = False
            with self.assertRaises(CommandError):
                call_command('create_school_user', 'ghost', '--role', 'teacher')
        self.assertFalse(User.objects.filter(username='ghost').exists())

    def test_links_student_record(self):
        record = Student.objects.create(
            first_name='Link', last_name='Test', email='link.test@example.com',
        )
        call_command('create_school_user', 'linker', '--role', 'student',
                     '--password', 'Paper-Kettle-61',
                     '--link-student', 'link.test@example.com')
        record.refresh_from_db()
        self.assertEqual(record.user.username, 'linker')

    def test_link_requires_student_role(self):
        with self.assertRaises(CommandError):
            call_command('create_school_user', 'nope', '--role', 'teacher',
                         '--password', 'Ink-Feather-12',
                         '--link-student', 'alice@example.com')

    def test_link_unknown_record_errors(self):
        with self.assertRaises(CommandError):
            call_command('create_school_user', 'nope', '--role', 'student',
                         '--password', 'Ink-Feather-12',
                         '--link-student', 'missing@example.com')
