from datetime import timedelta

from django.db import models
from django.utils import timezone

from ..json import JSONEncoder
# from common.json import JSONEncoder

# cls = TaskHistory
# TaskHistory is defined below this function in this file
def set_verbose_name(cls, task_wrapper, /, *args, vn_args=(), vn_fmt=None, **kwargs):
    assert vn_fmt is not None, 'vn_fmt is required'
    if vn_fmt is None:
        return False
    # support using the delay setting from the decorator
    if not ('delay' in kwargs or 'eta' in kwargs):
        kwargs['delay'] = task_wrapper.settings.get('delay') or int()
    result = task_wrapper.schedule(*args, **kwargs)
    try:
        task_history = cls.objects.get(task_id=str(result.id))
    except cls.DoesNotExist:
        pass
    else:
        task_history.verbose_name = str(vn_fmt).format(*vn_args)
        task_history.save()
        return True
    return False


class TaskHistoryQuerySet(models.QuerySet):

    def failed(self, within=None):
        """
        :param within: A timedelta object
        :return: A queryset of CompletedTasks that failed within the given timeframe (e.g. less than 1h ago)
        """
        qs = self.filter(
            failed_at__isnull=False,
        )
        if within:
            if not isinstance(within, timedelta):
                within = timedelta(seconds=within)
            time_limit = timezone.now() - within
            qs = qs.filter(failed_at__gt=time_limit)
        return qs

    def succeeded(self, within=None):
        """
        :param within: A timedelta object
        :return: A queryset of CompletedTasks that completed successfully within the given timeframe
        (e.g. less than 1h ago)
        """
        qs = self.filter(
            failed_at__isnull=True,
        )
        if within:
            if not isinstance(within, timedelta):
                within = timedelta(seconds=within)
            time_limit = timezone.now() - within
            qs = qs.filter(end_at__gt=time_limit)
        return qs


class TaskHistory(models.Model):
    # the "name" of the task/function to be run
    name = models.CharField(max_length=190, db_index=True)
    task_id = models.CharField(max_length=40, db_index=True)
    # the json encoded parameters to pass to the task
    task_params = models.JSONField(default=dict, encoder=JSONEncoder)

    verbose_name = models.CharField(max_length=255, null=True, blank=True)

    start_at = models.DateTimeField(db_index=True, null=True, blank=True)
    # when the task was scheduled to run
    scheduled_at = models.DateTimeField(default=timezone.now, db_index=True)
    # when the task was completed
    end_at = models.DateTimeField(default=timezone.now, db_index=True)

    # what priority the task had
    priority = models.IntegerField(default=0, db_index=True)
    # the "name" of the queue this is to be run on
    queue = models.CharField(max_length=190, db_index=True, null=True, blank=True)

    # how many times the task has been tried
    attempts = models.IntegerField(default=int, db_index=True)
    # when the task last failed
    failed_at = models.DateTimeField(db_index=True, null=True, blank=True)
    # details of the error that occurred
    last_error = models.TextField(blank=True)

    elapsed = models.FloatField(default=float)
    repeat = models.BigIntegerField(default=int)
    repeat_until = models.DateTimeField(null=True, blank=True)

    objects = TaskHistoryQuerySet.as_manager()

    @classmethod
    def schedule(cls, task_wrapper, /, *args, vn_args=(), vn_fmt=None, **kwargs):
        return set_verbose_name(cls, task_wrapper, *args, vn_fmt=vn_fmt, vn_args=vn_args, **kwargs)

    def save(self, *args, **kwargs):
        self.queue = self.queue or None
        self.verbose_name = self.verbose_name or None
        return super().save(*args, **kwargs)
        
    def has_error(self):
        """
        Check if the last_error field is empty.
        """
        return bool(self.last_error)

    def __str__(self):
        return u'{} - {}'.format(
            self.verbose_name or self.name,
            self.end_at,
        )


