import json
from datetime import datetime
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.views.generic import TemplateView
from django.contrib.auth import get_user_model
from django.utils.translation import gettext, gettext_lazy as _

from tasks.models import Task, TaskCategory, TaskSubcategory, Department

User = get_user_model()


class TaskDashboardView(TemplateView):
    template_name = 'dashboards/task_dashboard.html'

    def get_filter_queryset(self):
        qs = Task.objects.all()
        start_date = self.request.GET.get('start')
        end_date = self.request.GET.get('end')
        user = self.request.GET.get('user')
        category = self.request.GET.get('category')
        subcategory = self.request.GET.get('subcategory')
        department = self.request.GET.get('department')
        if start_date:
            try:
                start = datetime.fromisoformat(start_date).date()
                qs = qs.filter(start_date__gte=start)
            except ValueError:
                pass
        if end_date:
            try:
                end = datetime.fromisoformat(end_date).date()
                qs = qs.filter(due_date__lte=end)
            except ValueError:
                pass
        if user:
            qs = qs.filter(assignments__user_id=user)
        if category:
            qs = qs.filter(category_id=category)
        if subcategory:
            qs = qs.filter(subcategory_id=subcategory)
        if department:
            qs = qs.filter(department_id=department)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_filter_queryset()

        status_data = list(
            qs.values('status').annotate(total=Count('id')).order_by('status')
        )
        status_labels = [
            gettext(dict(Task.StatusChoices.choices).get(d["status"], d["status"]))
            for d in status_data
        ]
        status_values = [d['total'] for d in status_data]

        user_data = list(
            qs.values('assignments__user__username')
            .annotate(total=Count('id'))
            .order_by('-total')[:10]
        )
        none_label = gettext("None")
        user_labels = [d["assignments__user__username"] or none_label for d in user_data]
        user_values = [d['total'] for d in user_data]

        cat_data = list(
            qs.values('category__name').annotate(total=Count('id')).order_by('-total')[:10]
        )
        cat_labels = [d["category__name"] or none_label for d in cat_data]
        cat_values = [d['total'] for d in cat_data]

        subcat_data = list(
            qs.values('subcategory__name').annotate(total=Count('id')).order_by('-total')[:10]
        )
        subcat_labels = [d["subcategory__name"] or none_label for d in subcat_data]
        subcat_values = [d['total'] for d in subcat_data]

        month_data = list(
            qs.annotate(month=TruncMonth('due_date'))
            .values('month')
            .annotate(total=Count('id'))
            .order_by('month')
        )
        month_labels = [d["month"].strftime("%Y-%m") if d["month"] else none_label for d in month_data]
        month_values = [d['total'] for d in month_data]

        dept_data = list(
            qs.values('department__name').annotate(total=Count('id')).order_by('-total')[:10]
        )
        dept_labels = [d["department__name"] or none_label for d in dept_data]
        dept_values = [d['total'] for d in dept_data]

        context.update(
            status_labels=json.dumps(status_labels),
            status_values=json.dumps(status_values),
            user_labels=json.dumps(user_labels),
            user_values=json.dumps(user_values),
            category_labels=json.dumps(cat_labels),
            category_values=json.dumps(cat_values),
            subcategory_labels=json.dumps(subcat_labels),
            subcategory_values=json.dumps(subcat_values),
            month_labels=json.dumps(month_labels),
            month_values=json.dumps(month_values),
            department_labels=json.dumps(dept_labels),
            department_values=json.dumps(dept_values),
            users=User.objects.all(),
            categories=TaskCategory.objects.all(),
            subcategories=TaskSubcategory.objects.all(),
            departments=Department.objects.all(),
        )
        return context
