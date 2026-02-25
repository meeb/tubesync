import uuid
from datetime import timedelta
from itertools import islice

from django.db import connection, models, transaction
from django.utils import timezone

from ..json import JSONEncoder
# from common.json import JSONEncoder
from ..utils import is_empty_iterator
#from common.utils import is_empty_iterator

# cls = TaskHistory
# TaskHistory is defined below this function in this file
def th_schedule(cls, task_wrapper, /, *args, remove_duplicates=False, vn_args=(), vn_fmt=None, **kwargs):
    assert vn_fmt is not None, 'vn_fmt is required'
    if vn_fmt is None:
        return False
    defaults = dict(
        queue=task_wrapper.huey.name,
        remove_duplicates=remove_duplicates,
        verbose_name=str(vn_fmt).format(*vn_args),
    )
    # support using the delay setting from the decorator
    if not ('delay' in kwargs or 'eta' in kwargs):
        kwargs['delay'] = task_wrapper.settings.get('delay') or int()
    task_obj = task_wrapper.s(*args, **kwargs)
    task_id = str(task_obj.id)
    scheduled_at = task_wrapper.huey.scheduled_at_from_task(task_obj)
    if scheduled_at:
        defaults['scheduled_at'] = scheduled_at
    defaults['end_at'] = timezone.datetime.now(timezone.timezone.utc)
    defaults['name'] = f'{task_obj.__module__}.{task_obj.name}'
    defaults['priority'] = task_obj.priority
    defaults['task_params'] = list((
        list(task_obj.args),
        repr(task_obj.kwargs),
    ))
    cls.objects.update_or_create(
        task_id=task_id,
        defaults=defaults,
        create_defaults={
            'task_id': task_id,
            **defaults,
        },
    )
    task_wrapper.huey.enqueue(task_obj)
    return True

# self = TaskHistoryQuerySet
# TaskHistoryQuerySet is defined below this function in this file
def thqs_from_huey_ids(self, /, huey_task_ids):
    """
    Robustly matches Huey task.id values to TaskHistory records.

    Optimized for large datasets across SQLite, PostgreSQL, and MariaDB.
    Bypasses SQL variable limits by using request-cycle temporary tables.
    """
    # 1. Guard clause for empty input - returns a valid, empty QuerySet
    empty, huey_task_ids = is_empty_iterator(huey_task_ids)
    if empty:
        return self.none()

    # 2. Dynamic metadata and unique naming
    task_history_table = self.model._meta.db_table
    unique_suffix = uuid.uuid4().hex[:8]
    input_tmp = f"tmp_huey_ids_{unique_suffix}"
    results_tmp = f"tmp_history_pks_{unique_suffix}"

    # 3. Database operations
    def validated_id_generator():
        for tid in huey_task_ids:
            try:
                # Validates format and normalizes to lowercase dashed string
                yield (str(uuid.UUID(str(tid))).lower(),)
            except (ValueError, TypeError, AttributeError):
                # Skip malformed IDs and log for troubleshooting
                from common.logger import log
                log.warning(f"Skipping malformed Huey task ID: {tid}")
                continue

    with transaction.atomic():
        with connection.cursor() as cursor:
            # Stage 1: Store and normalize input IDs
            cursor.execute(f"CREATE TEMPORARY TABLE {input_tmp} (tid VARCHAR(40) PRIMARY KEY)")

            # Single iteration: ensures dashed strings and lowercase for case-sensitive DBs
            # Batch stream
            batch_size = 40_000
            stream = validated_id_generator()
            while batch := list(islice(stream, batch_size)):
                cursor.executemany(f"INSERT INTO {input_tmp} VALUES (%s)", batch)

            # Stage 2: Filter to a PK-only results table
            cursor.execute(f"CREATE TEMPORARY TABLE {results_tmp} (id BIGINT)")
            cursor.execute(f"""
                INSERT INTO {results_tmp} (id)
                SELECT id FROM {task_history_table}
                WHERE task_id IN (SELECT tid FROM {input_tmp})
            """)

            # Index the result PKs to ensure dashboard pagination and ordering are fast
            cursor.execute(f"CREATE INDEX idx_{results_tmp} ON {results_tmp}(id)")

            # Immediate cleanup of the input string table to save memory
            cursor.execute(f"DROP TABLE IF EXISTS {input_tmp}")

    # 4. Return a Lazy QuerySet via RawSQL to bypass RawQuerySet.clone() limitations.
    # The 'results_tmp' table persists until the connection closes after the request.
    return self.filter(
        id__in=models.expressions.RawSQL(
            f"SELECT id FROM {results_tmp}",
            [],
        )
    )


class TaskHistoryQuerySet(models.QuerySet):

    def from_huey_ids(self, /, huey_task_ids):
        return thqs_from_huey_ids(self, huey_task_ids)

    def running(self, now=None, within=None):
        if now is None:
            now = timezone.now()
        qs = self.filter(
            start_at=models.F('end_at'),
            scheduled_at__lte=models.F('end_at'),
        ).order_by('end_at')
        if within:
            if not isinstance(within, timedelta):
                within = timedelta(seconds=within)
            time_limit = now - within
            qs = qs.filter(end_at__gt=time_limit)
        return qs

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
    task_id = models.CharField(max_length=40, unique=True)
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

    remove_duplicates = models.BooleanField(default=bool)

    objects = TaskHistoryQuerySet.as_manager()

    @classmethod
    def schedule(cls, task_wrapper, /, *args, vn_args=(), vn_fmt=None, **kwargs):
        return th_schedule(cls, task_wrapper, *args, vn_fmt=vn_fmt, vn_args=vn_args, **kwargs)

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


