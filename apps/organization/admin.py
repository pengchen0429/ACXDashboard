from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .models import Department, Team, Employee


class EmployeeInline(admin.StackedInline):
    model = Employee
    fields = ["employee_no", "name", "department", "team", "is_active"]
    extra = 1
    max_num = 1
    can_delete = False
    show_change_link = True


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class OrganizationUserAdmin(UserAdmin):
    inlines = [EmployeeInline]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "department"]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        "employee_no",
        "name",
        "department",
        "team",
        "user",
        "is_active"
    ]

    list_select_related = ["department", "team", "user"]
    autocomplete_fields = ["user"]

    search_fields = [
        "employee_no",
        "name",
        "user__username"
    ]

    list_filter = [
        "department",
        "team",
        "is_active"
    ]