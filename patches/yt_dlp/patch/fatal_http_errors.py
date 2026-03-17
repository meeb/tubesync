```python
# models.py
from typing import Dict, Optional, Union
from django.db import models

class Container(models.Model):
    """
    A model for a database table to hold rows for containers that are supported.
    """
    EXTENSION_CHOICES = (
        ("m4a", "m4a"),
        ("webm", "webm"),
        ("mkv", "mkv"),
    )

    ASSET_TYPE_CHOICES = (
        ("audio", "audio"),
        ("video", "video"),
    )

    codec_choices = {
        "m4a": ["aac", "alac"],
        "webm": ["opus", "vp9", "av1"],
        "mkv": ["avc1"],
    }

    extension = models.CharField(max_length=255, choices=EXTENSION_CHOICES)
    asset_type = models.CharField(max_length=255, choices=ASSET_TYPE_CHOICES)
    number_supported = models.IntegerField()
    codec = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.extension} - {self.asset_type} - {self.codec}"
```

```python
# tests/test_container.py
import unittest
from django.db import IntegrityError
from .models import Container


class TestContainer(unittest.TestCase):
    def test_container_creation(self):
        # Create a test instance of Container
        container = Container(
            extension="m4a",
            asset_type="audio",
            number_supported=1,
            codec="aac",
        )

        # Try to save the container
        try:
            container.save()
        except IntegrityError:
            # If an IntegrityError is raised, it means the container already exists
            pass
        else:
            # If the container is saved successfully, it means it doesn't exist yet
            self.fail("Container already exists")

    def test_container_update(self):
        # Create a test instance of Container
        container = Container(
            extension="m4a",
            asset_type="audio",
            number_supported=1,
            codec="aac",
        )

        # Save the container
        container.save()

        # Update the container
        container.number_supported = 2
        container.save()

        # Check if the container was updated successfully
        self.assertEqual(container.number_supported, 2)

    def test_container_deletion(self):
        # Create a test instance of Container
        container = Container(
            extension="m4a",
            asset_type="audio",
            number_supported=1,
            codec="aac",
        )

        # Save the container
        container.save()

        # Delete the container
        container.delete()

        # Check if the container was deleted successfully
        with self.assertRaises(Container.DoesNotExist):
            Container.objects.get(extension="m4a", asset_type="audio", codec="aac")
```

```python
# tests/__init__.py
from tests.test_container import TestContainer
from tests.test_patched_youtube_ie import TestPatchedYoutubeIE
from tests.test_youtube_ie import TestYoutubeIE


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPatchedYoutubeIE))
    suite.addTests(loader.loadTestsFromTestCase(TestYoutubeIE))
    suite.addTests(loader.loadTestsFromTestCase(TestContainer))
    return suite
```