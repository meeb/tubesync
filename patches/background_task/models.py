# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone as tz
from hashlib import sha1
from pathlib import Path
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
from six import python_2_unicode_compatible

from background_task.exceptions import InvalidTaskError
from background_task.settings import app_settings
from background_task.signals import task_failed
from background_task.signals import task_rescheduled


logger = logging.getLogger(__name__)


class TaskQuerySet(models.QuerySet):

    def created_by(self, creator):
        """
        :return: A Task queryset filtered by creator
        """
        content_type = ContentType.objects.get_for_model(creator)
        return self.filter(
            creator_content_type=content_type,
            creator_object_id=creator.id,
        )


class TaskManager(models.Manager):

    _boot_time = posix_epoch = datetime(1970, 1, 1, tzinfo=tz.utc)

    @property
    def boot_time(self):
        if self._boot_time > self.posix_epoch:
            return self._boot_time
        stats = None
        boot_time = self.posix_epoch
        kcore_path = Path('/proc/kcore')
        if kcore_path.exists():
            stats = kcore_path.stat()
        if stats:
            boot_time += timedelta(seconds=stats.st_mtime)
        if boot_time > self._boot_time:
            self._boot_time = boot_time
        return self._boot_time

    def get_queryset(self):
        return TaskQuerySet(self.model, using=self._db)

    def created_by(self, creator):
        return self.get_queryset().created_by(creator)

    def find_available(self, queue=None):
        now = timezone.now()
        qs = self.unlocked(now)
        if queue:
            qs = qs.filter(queue=queue)
        ready = qs.filter(run_at__lte=now, failed_at=None)
        _priority_ordering = '{}priority'.format(
            app_settings.BACKGROUND_TASK_PRIORITY_ORDERING)
        ready = ready.order_by(_priority_ordering, 'run_at')

        if app_settings.BACKGROUND_TASK_RUN_ASYNC:
            currently_failed = self.failed().count()
            currently_locked = self.locked(now).count()
            count = app_settings.BACKGROUND_TASK_ASYNC_THREADS - \
                (currently_locked - currently_failed)
            if count > 0:
                ready = ready[:count]
            else:
                ready = self.none()
        return ready

    def unlocked(self, now):
        max_run_time = app_settings.BACKGROUND_TASK_MAX_RUN_TIME
        qs = self.get_queryset()
        expires_at = now - timedelta(seconds=max_run_time)
        unlocked = Q(locked_by=None) | Q(locked_at__lt=expires_at) | Q(locked_at__lt=self.boot_time)
        return qs.filter(unlocked)

    def locked(self, now):
        max_run_time = app_settings.BACKGROUND_TASK_MAX_RUN_TIME
        qs = self.get_queryset()
        expires_at = now - timedelta(seconds=max_run_time)
        locked = Q(locked_by__isnull=False) & Q(locked_at__gt=expires_at) & Q(locked_at__gt=self.boot_time)
        return qs.filter(locked)

    def failed(self):
        """
        `currently_locked - currently_failed` in `find_available` assues that
        tasks marked as failed are also in processing by the running PID.
        """
        qs = self.get_queryset()
        return qs.filter(failed_at__isnull=False)

    def new_task(self, task_name, args=None, kwargs=None,
                 run_at=None, priority=0, queue=None, verbose_name=None,
                 creator=None, repeat=None, repeat_until=None,
                 remove_existing_tasks=False):
        """
        If `remove_existing_tasks` is True, all unlocked tasks with the identical task hash will be removed.
        The attributes `repeat` and `repeat_until` are not supported at the moment.
        """
        args = args or ()
        kwargs = kwargs or {}
        if run_at is None:
            run_at = timezone.now()
        task_params = json.dumps((args, kwargs), sort_keys=True)
        s = "%s%s" % (task_name, task_params)
        task_hash = sha1(s.encode('utf-8')).hexdigest()
        if remove_existing_tasks:
            Task.objects.filter(task_hash=task_hash,
                                locked_at__isnull=True).delete()
        return Task(task_name=task_name,
                    task_params=task_params,
                    task_hash=task_hash,
                    priority=priority,
                    run_at=run_at,
                    queue=queue,
                    verbose_name=verbose_name,
                    creator=creator,
                    repeat=repeat or Task.NEVER,
                    repeat_until=repeat_until,
                    )

    def get_task(self, task_name, args=None, kwargs=None):
        args = args or ()
        kwargs = kwargs or {}
        task_params = json.dumps((args, kwargs), sort_keys=True)
        s = "%s%s" % (task_name, task_params)
        task_hash = sha1(s.encode('utf-8')).hexdigest()
        qs = self.get_queryset()
        return qs.filter(task_hash=task_hash)

    def drop_task(self, task_name, args=None, kwargs=None):
        return self.get_task(task_name, args, kwargs).delete()


@python_2_unicode_compatible
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
    # The repeat implementation is based on this encoding
    HOURLY = 3600
    DAILY = 24 * HOURLY
    WEEKLY = 7 * DAILY
    EVERY_2_WEEKS = 2 * WEEKLY
    EVERY_4_WEEKS = 4 * WEEKLY
    NEVER = 0
    REPEAT_CHOICES = (
        (HOURLY, 'hourly'),
        (DAILY, 'daily'),
        (WEEKLY, 'weekly'),
        (EVERY_2_WEEKS, 'every 2 weeks'),
        (EVERY_4_WEEKS, 'every 4 weeks'),
        (NEVER, 'never'),
    )
    repeat = models.BigIntegerField(choices=REPEAT_CHOICES, default=NEVER)
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

    creator_content_type = models.ForeignKey(
        ContentType, null=True, blank=True,
        related_name='background_task', on_delete=models.CASCADE
    )
    creator_object_id = models.PositiveIntegerField(null=True, blank=True)
    creator = GenericForeignKey('creator_content_type', 'creator_object_id')

    objects = TaskManager()

    @property
    def nodename(self):
        return os.uname().nodename[:(64-10)]
 
    def locked_by_pid_running(self):
        """
        Check if the locked_by process is still running.
        """
        if self in Task.objects.locked(timezone.now()) and self.locked_by:
            pid, nodename = self.locked_by.split('/', 1)
            # locked by a process on this node?
            if nodename != self.nodename:
                return False
            # is the process still running?
            try:
                # Signal number zero won't kill the process.
                os.kill(int(pid), 0)
                return True
            except:
                return False
        else:
            return None
    locked_by_pid_running.boolean = True

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

    def lock(self, locked_by):
        now = timezone.now()
        owner = f'{locked_by[:8]}/{self.nodename}'
        unlocked = Task.objects.unlocked(now).filter(pk=self.pk)
        updated = unlocked.update(locked_by=owner, locked_at=now)
        if updated:
            return Task.objects.get(pk=self.pk)
        return None

    def _extract_error(self, type, err, tb):
        file = StringIO()
        traceback.print_exception(type, err, tb, None, file)
        return file.getvalue()

    def increment_attempts(self):
        self.attempts += 1
        self.save()

    def has_reached_max_attempts(self):
        max_attempts = app_settings.BACKGROUND_TASK_MAX_ATTEMPTS
        return self.attempts >= max_attempts

    def is_repeating_task(self):
        return self.repeat > self.NEVER

    def reschedule(self, type, err, traceback):
        '''
        Set a new time to run the task in future, or create a CompletedTask and delete the Task
        if it has reached the maximum of allowed attempts
        '''
        self.last_error = self._extract_error(type, err, traceback)
        self.increment_attempts()
        if self.has_reached_max_attempts() or isinstance(err, InvalidTaskError):
            self.failed_at = timezone.now()
            logger.warning('Marking task %s as failed', self)
            completed = self.create_completed_task()
            task_failed.send(sender=self.__class__,
                             task_id=self.id, completed_task=completed)
            self.delete()
        else:
            backoff = timedelta(seconds=(self.attempts ** 4) + 5)
            self.run_at = timezone.now() + backoff
            logger.warning('Rescheduling task %s for %s later at %s', self,
                           backoff, self.run_at)
            task_rescheduled.send(sender=self.__class__, task=self)
            self.locked_by = None
            self.locked_at = None
            self.save()

    def create_completed_task(self):
        '''
        Returns a new CompletedTask instance with the same values
        '''
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

    def create_repetition(self):
        """
        :return: A new Task with an offset of self.repeat, or None if the self.repeat_until is reached
        """
        if not self.is_repeating_task():
            return None

        if self.repeat_until and self.repeat_until <= timezone.now():
            # Repeat chain completed
            return None

        args, kwargs = self.params()
        new_run_at = self.run_at + timedelta(seconds=self.repeat)
        while new_run_at < timezone.now():
            new_run_at += timedelta(seconds=self.repeat)

        new_task = TaskManager().new_task(
            task_name=self.task_name,
            args=args,
            kwargs=kwargs,
            run_at=new_run_at,
            priority=self.priority,
            queue=self.queue,
            verbose_name=self.verbose_name,
            creator=self.creator,
            repeat=self.repeat,
            repeat_until=self.repeat_until,
        )
        new_task.save()
        return new_task

    def save(self, *arg, **kw):
        # force NULL rather than empty string
        self.locked_by = self.locked_by or None
        return super(Task, self).save(*arg, **kw)

    def __str__(self):
        return u'{}'.format(self.verbose_name or self.task_name)

    class Meta:
        db_table = 'background_task'


class CompletedTaskQuerySet(models.QuerySet):

    def created_by(self, creator):
        """
        :return: A CompletedTask queryset filtered by creator
        """
        content_type = ContentType.objects.get_for_model(creator)
        return self.filter(
            creator_content_type=content_type,
            creator_object_id=creator.id,
        )

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


@python_2_unicode_compatible
class CompletedTask(models.Model):
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

    repeat = models.BigIntegerField(
        choices=Task.REPEAT_CHOICES, default=Task.NEVER)
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

    creator_content_type = models.ForeignKey(
        ContentType, null=True, blank=True,
        related_name='completed_background_task', on_delete=models.CASCADE
    )
    creator_object_id = models.PositiveIntegerField(null=True, blank=True)
    creator = GenericForeignKey('creator_content_type', 'creator_object_id')

    objects = CompletedTaskQuerySet.as_manager()

    def locked_by_pid_running(self):
        """
        Check if the locked_by process is still running.
        """
        if self.locked_by:
            pid, node = self.locked_by.split('/', 1)
            # locked by a process on this node?
            if os.uname().nodename[:(64-10)] != node:
                return False
            # is the process still running?
            try:
                # won't kill the process. kill is a bad named system call
                os.kill(int(pid), 0)
                return True
            except:
                return False
        else:
            return None
    locked_by_pid_running.boolean = True

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
