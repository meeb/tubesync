from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_url, LazyList
from yt_dlp.utils import network_exceptions
from urllib.request import HEADRequest

class PatchedYoutubeDL(YoutubeDL):
    """
    A patched version of YoutubeDL to sanitize thumbnails.
    """

    def _sanitize_thumbnails(self, info_dict: dict) -> None:
        """
        Sanitizes the thumbnails in the info dictionary.

        Args:
            info_dict (dict): The info dictionary to sanitize.
        """
        # Get the thumbnails from the info dictionary
        thumbnails = info_dict.get('thumbnails')

        # If thumbnails are not present, create a single thumbnail
        if thumbnails is None:
            thumbnail = info_dict.get('thumbnail')
            if thumbnail:
                info_dict['thumbnails'] = thumbnails = [{'url': thumbnail}]
        elif not thumbnails:
            # If thumbnails are empty, do nothing
            return

        # Define a generator to check thumbnails
        def check_thumbnails(thumbnails: list) -> LazyList:
            """
            Checks each thumbnail URL and yields the thumbnail if it's accessible.

            Args:
                thumbnails (list): The list of thumbnails to check.
            """
            for t in thumbnails:
                # Log a message for each thumbnail
                self.to_screen(f'[info] Testing thumbnail {t["id"]}: {t["url"]!r}')
                try:
                    # Try to open the thumbnail URL
                    self.urlopen(HEADRequest(t['url']))
                except network_exceptions as err:
                    # Log an error if the URL is not accessible
                    self.to_screen(f'[info] Unable to connect to thumbnail {t["id"]} URL {t["url"]!r} - {err}. Skipping...')
                    continue
                yield t

        # Sort the thumbnails
        self._sort_thumbnails(thumbnails)

        # Update the thumbnails with sanitized data
        for i, t in enumerate(thumbnails):
            # Assign an ID to the thumbnail if it's missing
            if t.get('id') is None:
                t['id'] = str(i)
            # Calculate the resolution if it's missing
            if t.get('width') and t.get('height'):
                t['resolution'] = '%dx%d' % (t['width'], t['height'])
            # Sanitize the URL
            t['url'] = sanitize_url(t['url'])

        # Check thumbnails if required
        if self.params.get('check_thumbnails') is True:
            # Use a LazyList to check thumbnails in reverse order
            info_dict['thumbnails'] = LazyList(check_thumbnails(thumbnails[::-1]), reverse=True)
        else:
            # Otherwise, just use the sanitized thumbnails
            info_dict['thumbnails'] = thumbnails

# Patch the original YoutubeDL
YoutubeDL.__unpatched___sanitize_thumbnails = YoutubeDL._sanitize_thumbnails
YoutubeDL._sanitize_thumbnails = PatchedYoutubeDL._sanitize_thumbnails