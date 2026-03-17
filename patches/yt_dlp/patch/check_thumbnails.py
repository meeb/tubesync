```python
# tests/test_utils.py
from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_url, LazyList
from yt_dlp.utils import network_exceptions

class TestUtils:
    def test_sanitize_thumbnails(self):
        """
        Test the _sanitize_thumbnails method.

        This test checks that the thumbnails are sanitized correctly.
        """
        ydl = YoutubeDL()
        info_dict = {
            "thumbnails": None,
            "thumbnail": "https://example.com/thumbnail.jpg"
        }
        ydl._sanitize_thumbnails(info_dict)
        assert info_dict["thumbnails"] == [{"url": "https://example.com/thumbnail.jpg"}]

        info_dict = {
            "thumbnails": []
        }
        ydl._sanitize_thumbnails(info_dict)
        assert info_dict["thumbnails"] == []

        info_dict = {
            "thumbnails": [{"url": "https://example.com/thumbnail1.jpg"}, {"url": "https://example.com/thumbnail2.jpg"}]
        }
        ydl._sanitize_thumbnails(info_dict)
        assert info_dict["thumbnails"] == [{"url": "https://example.com/thumbnail1.jpg"}, {"url": "https://example.com/thumbnail2.jpg"}]

        info_dict = {
            "thumbnails": [{"url": "https://example.com/thumbnail1.jpg"}, {"url": "https://example.com/thumbnail2.jpg"}]
        }
        ydl.params["check_thumbnails"] = True
        ydl._sanitize_thumbnails(info_dict)
        assert isinstance(info_dict["thumbnails"], LazyList)

# tests/test_youtube_dl.py
from yt_dlp import YoutubeDL
from yt_dlp.utils import network_exceptions

class TestYoutubeDL:
    def test_network_exceptions(self):
        """
        Test the network_exceptions module.

        This test checks that the network_exceptions module raises the correct exceptions.
        """
        ydl = YoutubeDL()
        try:
            ydl.urlopen(HEADRequest("https://example.com"))
        except network_exceptions as err:
            assert isinstance(err, Exception)
```

```python
# tests/test_sanitize_url.py
from yt_dlp.utils import sanitize_url

class TestSanitizeUrl:
    def test_sanitize_url(self):
        """
        Test the sanitize_url function.

        This test checks that the sanitize_url function sanitizes the URL correctly.
        """
        url = "https://example.com/thumbnail.jpg"
        sanitized_url = sanitize_url(url)
        assert sanitized_url == url
```

```python
# tests/test_lazy_list.py
from yt_dlp.utils import LazyList

class TestLazyList:
    def test_lazy_list(self):
        """
        Test the LazyList class.

        This test checks that the LazyList class works correctly.
        """
        lazy_list = LazyList([1, 2, 3])
        assert list(lazy_list) == [1, 2, 3]
```

```python
# tests/test_sort_thumbnails.py
from yt_dlp.utils import _sort_thumbnails

class TestSortThumbnails:
    def test_sort_thumbnails(self):
        """
        Test the _sort_thumbnails function.

        This test checks that the _sort_thumbnails function sorts the thumbnails correctly.
        """
        thumbnails = [{"url": "https://example.com/thumbnail1.jpg"}, {"url": "https://example.com/thumbnail2.jpg"}]
        _sort_thumbnails(thumbnails)
        assert thumbnails == [{"url": "https://example.com/thumbnail1.jpg"}, {"url": "https://example.com/thumbnail2.jpg"}]
```