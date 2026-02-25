import uuid
from django.db import connection, transaction
from django.db.models.expressions import RawSQL
from common.models import TaskHistory
from common.logger import log
from django_huey import DJANGO_HUEY, get_queue


def get_histories_from_huey_ids(huey_task_ids):
    """
    Robustly matches Huey task.id values to TaskHistory records.

    Optimized for large datasets across SQLite, PostgreSQL, and MariaDB.
    Bypasses SQL variable limits by using request-cycle temporary tables.
    """
    # 1. Guard clause for empty input - returns a valid, empty QuerySet
    if not huey_task_ids:
        return TaskHistory.objects.none()

    # 2. Dynamic metadata and unique naming
    task_history_table = TaskHistory._meta.db_table
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
                log.warning(f"Skipping malformed Huey task ID: {tid}")
                continue

    with transaction.atomic():
        with connection.cursor() as cursor:
            # Stage 1: Store and normalize input IDs
            cursor.execute(f"CREATE TEMPORARY TABLE {input_tmp} (tid VARCHAR(40) PRIMARY KEY)")

            # Single iteration: ensures dashed strings and lowercase for case-sensitive DBs
            cursor.executemany(f"INSERT INTO {input_tmp} VALUES (%s)", validated_id_generator())

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
    return TaskHistory.objects.filter(
        id__in=RawSQL(f"SELECT id FROM {results_tmp}", [])
    )

def get_waiting_tasks():
    huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
    huey_queues = list(map(get_queue, huey_queue_names))
    huey_task_ids = {
        str(t.id) for q in huey_queues for t in set(
            q.pending()
        ).union(
            q.scheduled()
        )
    }
    return get_histories_from_huey_ids(huey_task_ids)
