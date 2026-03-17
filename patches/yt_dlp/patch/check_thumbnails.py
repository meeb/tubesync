```python
# models.py
from django.db import models

class Container(models.Model):
    """
    Model for a container that supports different asset types.

    Attributes:
        extension (str): The file extension of the container.
        asset_type (str): The type of asset that the container supports (e.g. audio, video).
        number_supported (int): The number of assets that the container supports.
        codec (str): The codec used by the container.
    """
    extension = models.CharField(max_length=10)
    asset_type = models.CharField(max_length=10)
    number_supported = models.IntegerField()
    codec = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.extension} ({self.asset_type}) - {self.number_supported}x {self.codec}"
```

```python
# tests/test_container.py
from django.test import TestCase
from .models import Container

class TestContainer(TestCase):
    def test_container_model(self):
        """
        Test the Container model.

        This test checks that the Container model can be created and saved correctly.
        """
        container = Container(
            extension="m4a",
            asset_type="audio",
            number_supported=1,
            codec="aac"
        )
        container.save()
        assert container.id is not None
        assert container.extension == "m4a"
        assert container.asset_type == "audio"
        assert container.number_supported == 1
        assert container.codec == "aac"

        # Test that the __str__ method returns the correct string
        assert str(container) == "m4a (audio) - 1x aac"
```

```python
# tests/test_container.py (continued)
class TestContainer(TestCase):
    def test_container_model_choices(self):
        """
        Test the Container model choices.

        This test checks that the Container model choices are correct.
        """
        # Define the choices for the Container model
        CHOICES = (
            ("m4a", "audio", 1, "aac"),
            ("m4a", "audio", 1, "alac"),
            ("webm", "audio", 8, "opus"),
            ("webm", "video", 1, "vp9"),
            ("webm", "video", 1, "av1"),
            ("mkv", "video", 1, "avc1"),
        )

        # Test that the choices are correct
        for extension, asset_type, number_supported, codec in CHOICES:
            container = Container(
                extension=extension,
                asset_type=asset_type,
                number_supported=number_supported,
                codec=codec
            )
            assert container.extension == extension
            assert container.asset_type == asset_type
            assert container.number_supported == number_supported
            assert container.codec == codec
```