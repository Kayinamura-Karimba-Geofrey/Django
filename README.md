# Django

Student records CRUD app with role-based access control.

## Roles

Roles are Django auth **groups** (created automatically by migration `students.0002`):

| Role | Group | Access rights |
|------|-------|--------------|
| Teacher | `teacher` | View all students; create, edit and delete records. |
| Student | `student` | Log in and view **only the record linked to their account** (`Student.user`). Read-only: add/edit/delete return HTTP 403. |

Every page requires login (`/accounts/login/`); anonymous visitors are redirected
there. Superusers are treated as teachers. Users with no role get the most
restricted view (their own linked record only, no write access).

Role logic lives in `students/roles.py`; the role badge/logout bar comes from the
`students.context_processors.user_role` context processor.

### Django admin permissions

`students.roles.ensure_role_permissions` runs on `post_migrate` (the same hook
Django uses for its own permissions) and keeps the groups' permissions in sync:

- `teacher` → `students.add/change/delete/view_student` plus `auth.view_user`
  (needed by the Student admin's "user" autocomplete widget).
- `student` → **no model permissions**, on purpose: the Django admin cannot scope
  its changelist to "own record only", so a student must not be able to read the
  records table there. Students use the regular views instead.

Admin access also requires the `is_staff` flag. `create_school_user` sets it for
teachers by default (students default to no); override with `--staff` / `--no-staff`.

## URLs

- `/accounts/login/`, `/accounts/logout/`
- `/accounts/password_change/`, `/accounts/password_reset/` and their completion
  pages (templates in `templates/registration/`)
- `/students/` — list (scoped by role)
- `/students/add/`, `/students/edit/<pk>/`, `/students/delete/<pk>/` — teachers only

## Getting started

```bash
python manage.py migrate
python manage.py runserver
```

### Provisioning users

Use the management command (this is the supported way to create accounts —
the login pair below is development-only and must not be reused elsewhere):

```bash
# teacher with Django-admin access
python manage.py create_school_user jdoe --role teacher --password 'Str0ng-Pass!'

# student linked to their record, no admin access
python manage.py create_school_user adal --role student --password 'Str0ng-Pass!' \
    --link-student adal@example.com

# rotate a password / switch role later (re-running is safe)
python manage.py create_school_user jdoe --role teacher --password 'Even-Str0nger!'
```

Passwords are validated with Django's password validators (including similarity
to the username). Without `--password` in a non-interactive shell the command
refuses to create a new user.

To use the admin, log in at `/admin/` with a staff-flagged account (the command
sets this for teachers).

### Development-only demo accounts

| Username | Password | Role |
|----------|----------|------|
| `teacher1` | `Teach-Mango-77` | teacher (full CRUD + admin) |
| `student1` | `Apple-Story-88` | student (linked to Ada Lovelace's record) |

These exist only in the local (git-ignored) `db.sqlite3` so you can try both
roles immediately. Delete or re-password them (`create_school_user ... --password`)
before deploying anywhere shared.

## E-mail

Password-reset e-mails go through the `MAILERS` setting in
`school_project/settings.py`, which uses the **console backend** in development:
the message (including the reset link) is printed to the terminal running
`runserver`. Configure a real mailer in production.

## Tests

```bash
python manage.py test students
```

Covers anonymous redirects, role-scoped list access, teacher CRUD, student 403s,
group permissions after migration, admin access per role, the password
change/reset flows, template precedence over `django.contrib.admin`'s
`registration/*.html`, and the `create_school_user` command.
