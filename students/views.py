from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404

from .forms import StudentForm
from .models import Student
from .roles import is_teacher


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
    students = visible_students(request.user)
    linked = is_teacher(request.user) or students.exists()
    return render(
        request,
        'students/student_list.html',
        {'students': students, 'student_record_linked': linked},
    )


# 2. CREATE (Register a new student) — teachers only
@teacher_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'students/student_form.html', {'form': form, 'action': 'Register'})


# 3. UPDATE (Edit existing student record) — teachers only
@teacher_required
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(request, 'students/student_form.html', {'form': form, 'action': 'Update'})


# 4. DELETE (Remove student record) — teachers only
@teacher_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        return redirect('student_list')
    return render(request, 'students/student_confirm_delete.html', {'student': student})
