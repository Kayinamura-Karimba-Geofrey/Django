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
`students.context_processors.user_role` context processor. The resolved role is
cached on the user object, so a request costs one group lookup instead of one per
call site.

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
- `/students/` — list (scoped by role, paginated for teachers)
- `/students/add/`, `/students/edit/<pk>/`, `/students/delete/<pk>/` — teachers only

## Configuration

Settings read the environment (`school_project/settings.py`) and switch behaviour
with `DJANGO_ENV`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_ENV` | `development` | `development` or `production`. Production turns on the HTTPS/cookie hardening, requires a secret key and hosts, and switches e-mail to SMTP. |
| `DJANGO_DEBUG` | on in dev, off in prod | Debug flag. |
| `DJANGO_SECRET_KEY` | random per boot (dev) | **Required in production** (50+ random characters). In development a fresh key is generated at start-up, so no usable key is ever committed — restarting `runserver` invalidates sessions. |
| `DJANGO_ALLOWED_HOSTS` | empty (dev) | **Required in production**, comma-separated hostnames. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated origins allowed to POST, e.g. `https://example.com`. |
| `DJANGO_EMAIL_HOST` / `DJANGO_EMAIL_PORT` / `DJANGO_EMAIL_USER` / `DJANGO_EMAIL_PASSWORD` / `DJANGO_EMAIL_USE_TLS` / `DJANGO_EMAIL_TIMEOUT` | `localhost` / `587` / – / – / on / `10` | SMTP server used by the `default` mailer in production. |
| `DJANGO_DEFAULT_FROM_EMAIL` | `webmaster@localhost` | From-address for outgoing mail. |
| `DJANGO_LOG_LEVEL` | `INFO` | Level for the `django` and `students` loggers (console handler). |
| `DJANGO_BEHIND_PROXY` | off | Set to `1` when a reverse proxy sets `X-Forwarded-Proto`, so `SECURE_SSL_REDIRECT` works behind it. |

## Getting started

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
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

## Deployment

```bash
export DJANGO_ENV=production
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
export DJANGO_ALLOWED_HOSTS=example.com
export DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com
export DJANGO_EMAIL_HOST=smtp.example.com   # plus port/user/password as needed

python manage.py check --deploy   # must report no issues
python manage.py migrate
python manage.py collectstatic    # assets land in STATIC_ROOT
```

In production the settings enable `SECURE_SSL_REDIRECT`, secure session/CSRF
cookies, HSTS (1 year, subdomains, preload), `nosniff` and `same-origin`
referrers, and refuse to boot without `DJANGO_SECRET_KEY` /
`DJANGO_ALLOWED_HOSTS`. Serve `STATIC_ROOT` from your web server (nginx,
WhiteNoise, …) and redirect traffic to HTTPS.

## E-mail

Password-reset e-mails go through the `MAILERS` setting in
`school_project/settings.py`:

- **development** — the console backend: the message (including the reset link)
  is printed to the terminal running `runserver`.
- **production** — SMTP, configured with the `DJANGO_EMAIL_*` variables above.

`manage.py check --deploy` fails (`mail.E001`) if the development backend is
still configured in production.

## Templates

All pages extend `templates/base.html` (head, viewport meta, the Bootstrap 5.3.0
CDN stylesheet with an **SRI integrity hash**, and flashed messages). Bootstrap
is the only third-party asset; add local assets under a `static/` directory and
serve them from `STATIC_ROOT`.

## Tests

```bash
python manage.py test students
ruff check .
python manage.py makemigrations --check --dry-run
```

Tests cover anonymous redirects, role-scoped list access, teacher CRUD, student
403s, group permissions after migration, admin access per role, the password
change/reset flows, template precedence over `django.contrib.admin`'s
`registration/*.html`, the `create_school_user` command, plus the
success messages, pagination/ordering, e-mail normalization and the scoped
"user account" choices on the student form.

`.github/workflows/ci.yml` runs lint, the missing-migration check,
`manage.py check`, `check --deploy` with production-shaped environment
variables, and the test suite against both development and production settings.
