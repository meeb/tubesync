from django.apps import AppConfig


class SyncConfig(AppConfig):
    name = 'sync'

    def ready(self):
        from .tasks import cleanup_huey_storage
        self.cleanup_huey_storage_result = cleanup_huey_storage.enqueue()
