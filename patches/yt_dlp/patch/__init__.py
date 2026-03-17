```python
# tests/utils.py

from yt_dlp.compat.compat_utils import passthrough_module

# Create a Container model to hold rows for containers that are supported
class Container:
    """Database model for container types."""
    
    def __init__(self, extension, asset_type, number_supported, codec):
        """
        Initialize a Container instance.

        Args:
            extension (str): File extension (e.g., m4a, webm, mkv).
            asset_type (str): Type of asset (e.g., audio, video).
            number_supported (int): Number of supported versions.
            codec (str): Codec used (e.g., aac, alac, vp9, av1, avc1).
        """
        self.extension = extension
        self.asset_type = asset_type
        self.number_supported = number_supported
        self.codec = codec

# Example usage:
# container = Container('m4a', 'audio', 1, 'aac')
# container = Container('webm', 'video', 1, 'vp9')

passthrough_module(__name__, ".patch")
del passthrough_module
```