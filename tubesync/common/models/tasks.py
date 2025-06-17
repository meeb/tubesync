

from datetime import timedelta
from hashlib import sha1
import json
import logging
import os
import traceback

from io import StringIO
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone

from background_task.exceptions import InvalidTaskError
from background_task.settings import app_settings
from background_task.signals import task_failed
from background_task.signals import task_rescheduled

'''
logger = logging.getLogger(__name__)


class Task(models.Model):
    # the "name" of the task/function to be run
    task_name = models.CharField(max_length=190, db_index=True)
    # the json encoded parameters to pass to the task
    task_params = models.TextField()
    # a sha1 hash of the name and params, to lookup already scheduled tasks
    task_hash = models.CharField(max_length=40, db_index=True)

    verbose_name = models.CharField(max_length=255, null=True, blank=True)

    # what priority the task has
    priority = models.IntegerField(default=0, db_index=True)
    # when the task should be run
    run_at = models.DateTimeField(db_index=True)

    # Repeat choices are encoded as number of seconds
    repeat = models.BigIntegerField(default=0)
    repeat_until = models.DateTimeField(null=True, blank=True)

    # the "name" of the queue this is to be run on
    queue = models.CharField(max_length=190, db_index=True,
                             null=True, blank=True)

    # how many times the task has been tried
    attempts = models.IntegerField(default=0, db_index=True)
    # when the task last failed
    failed_at = models.DateTimeField(db_index=True, null=True, blank=True)
    # details of the error that occurred
    last_error = models.TextField(blank=True)

    # details of who's trying to run the task at the moment
    locked_by = models.CharField(max_length=64, db_index=True,
                                 null=True, blank=True)
    locked_at = models.DateTimeField(db_index=True, null=True, blank=True)

    def has_error(self):
        """
        Check if the last_error field is empty.
        """
        return bool(self.last_error)
    has_error.boolean = True

    def params(self):
        args, kwargs = json.loads(self.task_params)
        # need to coerce kwargs keys to str
        kwargs = dict((str(k), v) for k, v in kwargs.items())
        return args, kwargs

    def _extract_error(self, type, err, tb):
        file = StringIO()
        traceback.print_exception(type, err, tb, None, file)
        return file.getvalue()

    def create_completed_task(self):
        """
        Returns a new CompletedTask instance with the same values
        """
        completed_task = CompletedTask(
            task_name=self.task_name,
            task_params=self.task_params,
            task_hash=self.task_hash,
            priority=self.priority,
            run_at=timezone.now(),
            queue=self.queue,
            attempts=self.attempts,
            failed_at=self.failed_at,
            last_error=self.last_error,
            locked_by=self.locked_by,
            locked_at=self.locked_at,
            verbose_name=self.verbose_name,
            creator=self.creator,
            repeat=self.repeat,
            repeat_until=self.repeat_until,
        )
        completed_task.save()
        return completed_task

    def save(self, *arg, **kw):
        # force NULL rather than empty string
        self.locked_by = self.locked_by or None
        return super(Task, self).save(*arg, **kw)

    def __str__(self):
        return u'{}'.format(self.verbose_name or self.task_name)

    class Meta:
        db_table = 'background_task'
'''

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
            time_limit = timezone.now() - within
            qs = qs.filter(run_at__gt=time_limit)
        return qs


class TaskHistory(models.Model):
    # the "name" of the task/function to be run
    name = models.CharField(max_length=190, db_index=True)
    # the json encoded parameters to pass to the task
    task_params = models.TextField()

    verbose_name = models.CharField(max_length=255, null=True, blank=True)

    # what priority the task has
    priority = models.IntegerField(default=0, db_index=True)
    # when the task was completed
    end_at = models.DateTimeField(db_index=True)

    repeat = models.BigIntegerField(default=0)
    repeat_until = models.DateTimeField(null=True, blank=True)

    # the "name" of the queue this is to be run on
    queue = models.CharField(max_length=190, db_index=True,
                             null=True, blank=True)

    # how many times the task has been tried
    attempts = models.IntegerField(default=0, db_index=True)
    # when the task last failed
    failed_at = models.DateTimeField(db_index=True, null=True, blank=True)
    # details of the error that occurred
    last_error = models.TextField(blank=True)

    locked_at = models.DateTimeField(db_index=True, null=True, blank=True)

    objects = TaskHistoryQuerySet.as_manager()

    def has_error(self):
        """
        Check if the last_error field is empty.
        """
        return bool(self.last_error)
    has_error.boolean = True

    def __str__(self):
        return u'{} - {}'.format(
            self.verbose_name or self.task_name,
            self.run_at,
        )


