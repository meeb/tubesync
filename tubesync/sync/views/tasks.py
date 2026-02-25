from django.conf import settings
from django.http import HttpResponseNotFound, HttpResponseRedirect
from django.views.generic import ListView
from django.views.generic.edit import FormView
from django.views.generic.detail import SingleObjectMixin
from django.urls import reverse_lazy
from django.db.models import F
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from common.models import TaskHistory
from common.timestamp import timestamp_to_datetime
from common.utils import append_uri_params, multi_key_sort
from common.huey import h_q_reset_tasks
from common.logger import log
from django_huey import DJANGO_HUEY, get_queue
from .utils import get_waiting_tasks
from ..models import Source
from ..forms import ResetTasksForm, ScheduleTaskForm
from ..tasks import (
    map_task_to_instance, get_error_message,
    get_running_tasks, check_source_directory_exists,
)


class TasksView(ListView):
    '''
        A list of tasks queued to be completed. This is, for example, scraping for new
        media or downloading media.
    '''

    template_name = 'sync/tasks.html'
    context_object_name = 'tasks'
    paginate_by = settings.TASKS_PER_PAGE
    messages = {
        'filter': _('Viewing tasks filtered for source: <strong>{name}</strong>'),
        'reset': _('All tasks have been reset'),
        'revoked': _('Revoked task: {task_id}'),
        'scheduled': _('Scheduled task: {name}'),
    }

    def __init__(self, *args, **kwargs):
        self.filter_source = None
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        filter_by = request.GET.get('filter', '')
        if filter_by:
            try:
                self.filter_source = Source.objects.get(pk=filter_by)
            except Source.DoesNotExist:
                self.filter_source = None
            else:
                if not message_key or 'filter' == message_key:
                    message = self.messages.get('filter', '')
                    self.message = message.format(
                        name=self.filter_source.name
                    )

        if message_key in ('revoked', 'scheduled'):
            fmt_vars = dict(
                pk=request.GET.get('pk', 'Unknown'),
                task_id=request.GET.get('task_id', 'Unknown'),
            )
            try:
                task = TaskHistory.objects.get(pk=fmt_vars['pk'])
            except TaskHistory.DoesNotExist:
                fmt_vars['name'] = fmt_vars['pk']
            else:
                fmt_vars['name'] = task.verbose_name or task.task_id or task.pk
                fmt_vars['task_id'] = task.task_id
            self.message = self.message.format(**fmt_vars)

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = get_waiting_tasks()
        if self.filter_source:
            params_prefix=f'[["{self.filter_source.pk}"'
            qs = qs.filter(task_params__istartswith=params_prefix)
        return qs.order_by(
            '-priority',
            'scheduled_at',
            'end_at',
        )

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        now_dt = timezone.now()
        scheduled_qs = get_waiting_tasks()
        # Huey removes running tasks,
        # so the waiting tasks will not include them.
        running_qs = get_running_tasks(now_dt)
        errors_qs = scheduled_qs.filter(
            attempts__gt=0
        ).exclude(last_error__exact='')

        # Add to context data from ListView
        data['message'] = self.message
        data['source'] = self.filter_source
        data['running'] = list()
        data['errors'] = list()
        data['total_errors'] = errors_qs.count()
        data['scheduled'] = list()
        data['total_scheduled'] = scheduled_qs.count()
        data['wait_for_database_queue'] = False

        def add_to_task(task):
            setattr(task, 'run_now', task.scheduled_at < now_dt)
            obj, url = map_task_to_instance(task)
            if obj:
                setattr(task, 'instance', obj)
                setattr(task, 'url', url)
            if task.has_error():
                error_message = get_error_message(task)
                setattr(task, 'error_message', error_message)
                return 'error'
            return True and obj

        for task in running_qs:
            if task in data['running']:
                    continue
            add_to_task(task)
            data['running'].append(task)

        # show all the errors when they fit on one page
        if (data['total_errors'] + len(data['running'])) < self.paginate_by:
            for task in errors_qs:
                if task in data['running']:
                    continue
                mapped = add_to_task(task)
                if 'error' == mapped:
                    data['errors'].append(task)
                elif mapped:
                    data['scheduled'].append(task)

        for task in data['tasks']:
            already_added = (
                task in data['running'] or
                task in data['errors'] or
                task in data['scheduled']
            )
            if already_added:
                continue
            mapped = add_to_task(task)
            if 'error' == mapped:
                data['errors'].append(task)
            elif mapped or settings.DEBUG:
                data['scheduled'].append(task)

        sort_keys = (
            # key, reverse
            ('priority', True),
            ('scheduled_at', False),
            ('run_now', True),
        )
        data['errors'] = multi_key_sort(data['errors'], sort_keys, attr=True)
        data['scheduled'] = multi_key_sort(data['scheduled'], sort_keys, attr=True)

        return data

    def paginate_queryset(self, queryset, page_size):
        """Paginate the queryset, if needed."""
        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page_kwarg = self.page_kwarg
        page = self.kwargs.get(page_kwarg) or self.request.GET.get(page_kwarg) or 1
        try:
            page_number = int(page)
        except ValueError:
            pass
        else:
            if page_number > paginator.num_pages:
                self.kwargs[page_kwarg] = 'last'
        return super().paginate_queryset(queryset, page_size)

    def get(self, *args, **kwargs):
        path = args[0].path
        if path.startswith('/task/') and path.endswith('/cancel'):
            try:
                task = TaskHistory.objects.get(pk=kwargs["pk"])
            except TaskHistory.DoesNotExist:
                return HttpResponseNotFound()
            else:
                huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
                huey_queues = { q.name: q for q in map(get_queue, huey_queue_names) }
                q = huey_queues.get(task.queue)
                if q is None:
                    msg = f'TasksView: queue not found: {task.pk=} {task.queue=}'
                    log.warning(msg)
                    return HttpResponseNotFound()
                # revoke the task we want to cancel
                q.revoke_by_id(id=task.task_id, revoke_once=True)
                vn = task.verbose_name or task.task_id or task.pk
                if not vn.startswith('[revoked] '):
                    task.verbose_name = f'[revoked] {vn}'
                    task.save()
                return HttpResponseRedirect(append_uri_params(
                    reverse_lazy('sync:tasks'),
                    dict(
                        message='revoked',
                        pk=str(task.pk),
                        task_id=str(task.task_id),
                    ),
                ))
        else:
            return super().get(self, *args, **kwargs)

class CompletedTasksView(ListView):
    '''
        List of tasks which have been completed with an optional per-source filter.
    '''

    template_name = 'sync/tasks-completed.html'
    context_object_name = 'tasks'
    paginate_by = settings.TASKS_PER_PAGE
    messages = {
        'filter': _('Viewing tasks filtered for source: <strong>{name}</strong>'),
    }

    def __init__(self, *args, **kwargs):
        self.filter_source = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        filter_by = request.GET.get('filter', '')
        if filter_by:
            try:
                self.filter_source = Source.objects.get(pk=filter_by)
            except Source.DoesNotExist:
                self.filter_source = None
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = TaskHistory.objects.filter(
            start_at__isnull=False,
            end_at__gt=F('start_at'),
        )
        if self.filter_source:
            params_prefix=f'[["{self.filter_source.pk}"'
            qs = qs.filter(task_params__istartswith=params_prefix)
        return qs.order_by('-end_at')

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        for task in data['tasks']:
            if task.has_error():
                error_message = get_error_message(task)
                setattr(task, 'error_message', error_message)
        data['message'] = ''
        data['source'] = self.filter_source
        if self.filter_source:
            message = str(self.messages.get('filter', ''))
            data['message'] = message.format(name=self.filter_source.name)
        return data


class ResetTasks(FormView):
    '''
        Confirm that all tasks should be reset. As all tasks are triggered from
        signals by checking for files existing etc. this can be done by just deleting
        all tasks and then calling every Source objects .save() method.
    '''

    template_name = 'sync/tasks-reset.html'
    form_class = ResetTasksForm

    def form_valid(self, form):
        # Delete all tasks
        huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
        for queue_name in huey_queue_names:
            h_q_reset_tasks(queue_name)
        # Iter all tasks
        for source in Source.objects.all():
            check_source_directory_exists(str(source.pk))
            # This also chains down to call each Media objects .save() as well
            source.save()
        return super().form_valid(form)

    def get_success_url(self):
        url = reverse_lazy('sync:tasks')
        return append_uri_params(url, {'message': 'reset'})


class TaskScheduleView(FormView, SingleObjectMixin):
    '''
        Confirm that the task should be re-scheduled.
    '''

    template_name = 'sync/task-schedule.html'
    form_class = ScheduleTaskForm
    model = TaskHistory
    context_object_name = 'task'
    errors = dict(
        invalid_when=_('The type ({}) was incorrect.'),
        when_before_now=_('The date and time must be in the future.'),
    )

    def __init__(self, *args, **kwargs):
        self.now = timezone.now()
        self.object = None
        self.timestamp = None
        self.when = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.now = timezone.now()
        self.object = self.get_object()
        self.timestamp = kwargs.get('timestamp')
        try:
            self.when = timestamp_to_datetime(self.timestamp)
        except AssertionError:
            self.when = None
        if self.when is None:
            self.when = self.now
        # Use the next minute and zero seconds
        # The web browser does not select seconds by default
        self.when = self.when.replace(second=0) + timezone.timedelta(minutes=1)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['now'] = self.now
        initial['when'] = self.when
        return initial

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['now'] = self.now
        data['when'] = self.when
        return data

    def get_success_url(self):
        return append_uri_params(
            reverse_lazy('sync:tasks'),
            dict(
                message='scheduled',
                pk=str(self.object.pk),
                task_id=str(self.object.task_id),
            ),
        )

    def form_valid(self, form):
        when = form.cleaned_data.get('when')

        if not isinstance(when, self.now.__class__):
            form.add_error(
                'when',
                ValidationError(
                    self.errors['invalid_when'].format(
                        type(when),
                    ),
                ),
            )
        if when < self.now:
            form.add_error(
                'when',
                ValidationError(self.errors['when_before_now']),
            )

        if form.errors:
            return super().form_invalid(form)

        pk = self.object.pk
        queue = self.object.queue
        task_id = self.object.task_id
        huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
        huey_queues = { q.name: q for q in map(get_queue, huey_queue_names) }
        q = huey_queues.get(queue)
        if q is None:
            msg = f'TaskScheduleView: queue not found: {pk=} {queue=}'
            log.warning(msg)
        else:
            eta = max(self.now, when)
            if q.reschedule(task_id, eta):
                vn = self.object.verbose_name or task_id or pk
                self.object.verbose_name = f'[revoked] {vn}'
                self.object.save()
            else:
                msg = f'TaskScheduleView: task not found: {pk=} {task_id=}'
                log.warning(msg)

        return super().form_valid(form)
