from common.models import TaskHistory
from django_huey import DJANGO_HUEY, get_queue


def get_waiting_tasks():
    huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
    huey_queues = list(map(get_queue, huey_queue_names))

    # Fast Guard: Check counts across all Huey queues
    if not any(0 < (q.pending_count() + q.scheduled_count()) for q in huey_queues):
         return TaskHistory.objects.none()

    def id_generator(queue):
        # Stream pending tasks
        for task in queue.pending():
            yield str(task.id)

        # Stream scheduled tasks
        for task in queue.scheduled():
            yield str(task.id)

    def deduplicating_id_generator():
        seen = set()
        for q in huey_queues:
            for tid in id_generator(q):
                if tid not in seen:
                    seen.add(tid)
                    yield tid
        seen.clear()

    huey_task_ids = deduplicating_id_generator()
    return TaskHistory.objects.from_huey_ids(huey_task_ids)

