from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import StudentForm
from .models import Student
from .roles import is_teacher

# Rows per page for the (teacher) directory view.
STUDENTS_PER_PAGE = 25


def teacher_required(view_func):
    """Restrict a view to authenticated teachers.

    Anonymous users are sent to the login page; authenticated non-teachers
    get an HTTP 403.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_teacher(request.user):
            raise PermissionDenied('Only teachers can perform this action.')
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def visible_students(user):
    """Students see only their own record; teachers see everything."""
    if is_teacher(user):
        return Student.objects.all()
    return Student.objects.filter(user=user)


# 1. READ (List students — scoped by role)
@login_required
def student_list(request):
    """Role-scoped directory.

    Teachers get the full, paginated list. Everyone else holds at most one
    record (``Student.user`` is a OneToOneField), so their rows are fetched in
    a single query with no pagination.
    """
    if is_teacher(request.user):
        page_obj = Paginator(
            Student.objects.all(), STUDENTS_PER_PAGE
        ).get_page(request.GET.get('page'))
        students = page_obj.object_list
        linked = True
    else:
        students = list(Student.objects.filter(user=request.user))
        page_obj = None
        linked = bool(students)

    return render(
        request,
        'students/student_list.html',
        {
            'students': students,
            'page_obj': page_obj,
            'student_record_linked': linked,
        },
    )


# 2. CREATE (Register a new student) — teachers only
@teacher_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student = form.save()
            messages.success(request, f'Student “{student}” was created.')
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(
        request,
        'students/student_form.html',
        {'form': form, 'action': 'Register'},
    )


# 3. UPDATE (Edit existing student record) — teachers only
@teacher_required
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            updated = form.save()
            messages.success(request, f'Student “{updated}” was updated.')
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(
        request,
        'students/student_form.html',
        {'form': form, 'action': 'Update'},
    )


# 4. DELETE (Remove student record) — teachers only
@teacher_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        name = str(student)
        student.delete()
        messages.success(request, f'Student “{name}” was deleted.')
        return redirect('student_list')
    return render(
        request,
        'students/student_confirm_delete.html',
        {'student': student},
    )
