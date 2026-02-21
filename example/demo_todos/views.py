from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from example.authz import require_app_access
from example.decorators import app_permission

from .models import Todo


@login_required
def todo_list(request):
    # Check permissions and catch PermissionDenied to show in template
    try:
        require_app_access(request, "todos")
    except PermissionDenied as e:
        context = {
            "permission_error": str(e),
            "todos": [],
            "todos_completed": 0,
            "todos_pending": 0,
        }
        return render(request, "todos/todo_list.html", context)

    if request.method == "POST":
        text = request.POST.get("text")
        if text:
            Todo.objects.create(owner=request.user, text=text)
        return redirect("todos_list")

    todos = Todo.objects.filter(owner=request.user).order_by("-created_at")
    todos_completed = todos.filter(is_done=True).count()
    todos_pending = todos.filter(is_done=False).count()

    context = {
        "todos": todos,
        "todos_completed": todos_completed,
        "todos_pending": todos_pending,
    }
    return render(request, "todos/todo_list.html", context)


@app_permission("todos")
@require_http_methods(["POST"])
def todo_toggle(request, pk):
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    todo.is_done = not todo.is_done
    todo.save()
    return redirect("todos_list")


@app_permission("todos")
@require_http_methods(["POST"])
def todo_delete(request, pk):
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    todo.delete()
    return redirect("todos_list")
