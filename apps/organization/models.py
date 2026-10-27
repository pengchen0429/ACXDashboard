from django.db import models
from django.contrib.auth.models import User


class Department(models.Model):
    name = models.CharField(
        verbose_name="部门名称",
        max_length=100,
        unique=True
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "部门"
        verbose_name_plural = "部门"


class Team(models.Model):
    name = models.CharField(
        verbose_name="班组名称",
        max_length=100
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        verbose_name="所属部门"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "班组"
        verbose_name_plural = "班组"


class Employee(models.Model):

    employee_no = models.CharField(
        verbose_name="工号",
        max_length=20,
        unique=True
    )

    name = models.CharField(
        verbose_name="姓名",
        max_length=50
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="部门"
    )

    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="班组"
    )

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="登录账号"
    )

    is_active = models.BooleanField(
        verbose_name="在职",
        default=True
    )

    def __str__(self):
        return f"{self.employee_no} - {self.name}"

    class Meta:
        verbose_name = "员工"
        verbose_name_plural = "员工"