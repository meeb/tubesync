from yt_dlp.extractor.youtube import YoutubeIE
from typing import Dict, Optional, Union

class PatchedYoutubeIE(YoutubeIE):
    """
    A patched version of YoutubeIE to modify _download_player_responses and _download_initial_webpage methods.
    """

    def _download_player_responses(
        self, url: str, smuggled_data: Dict, video_id: str, webpage_url: str
    ) -> tuple[Optional[str], Optional[Dict], list, str]:
        """
        Downloads player responses from the given URL.

        Args:
        url (str): The URL to download player responses from.
        smuggled_data (Dict): Smuggled data for the player responses.
        video_id (str): The video ID.
        webpage_url (str): The URL of the webpage.

        Returns:
        tuple[Optional[str], Optional[Dict], list, str]: A tuple containing the webpage, master_ytcfg, player responses, and player URL.
        """
        # If 'webpage' is not in player_skip, download the webpage with retries
        if 'webpage' not in self._configuration_arg('player_skip'):
            # Set query parameters for the webpage download
            query = {'bpctr': '9999999999', 'has_verified': '1'}
            # Get player parameters from configuration or default value
            pp = self._configuration_arg('player_params', [None], casesense=True)[0]
            if pp:
                query['pp'] = pp
            # Download the webpage with retries
            webpage = self._download_webpage_with_retries(webpage_url, video_id, retry_fatal=True, query=query)

        # Extract ytcfg from the webpage or default value
        master_ytcfg = self.extract_ytcfg(video_id, webpage) or self._get_default_ytcfg()

        # Extract player responses and player URL
        player_responses, player_url = self._extract_player_responses(
            self._get_requested_clients(url, smuggled_data),
            video_id, webpage, master_ytcfg, smuggled_data)

        return webpage, master_ytcfg, player_responses, player_url

    def _download_initial_webpage(
        self, webpage_url: str, webpage_client: str, video_id: str
    ) -> Optional[str]:
        """
        Downloads the initial webpage.

        Args:
        webpage_url (str): The URL of the webpage.
        webpage_client (str): The webpage client.
        video_id (str): The video ID.

        Returns:
        Optional[str]: The downloaded webpage or None if not downloaded.
        """
        # If webpage_url is not None and 'webpage' is not in player_skip, download the webpage with retries
        if webpage_url and 'webpage' not in self._configuration_arg('player_skip'):
            # Set query parameters for the webpage download
            query = {'bpctr': '9999999999', 'has_verified': '1'}
            # Get player parameters from configuration or default value
            pp = (
                self._configuration_arg('player_params', [None], casesense=True)[0]
                or traverse_obj(INNERTUBE_CLIENTS, (webpage_client, 'PLAYER_PARAMS', {str}))
            )
            if pp:
                query['pp'] = pp
            # Download the webpage with retries
            webpage = self._download_webpage_with_retries(
                webpage_url, video_id, retry_fatal=True, query=query,
                headers=traverse_obj(self._get_default_ytcfg(webpage_client), {
                    'User-Agent': ('INNERTUBE_CONTEXT', 'client', 'userAgent', {str}),
                }))
        return webpage


# Patch the original methods
YoutubeIE.__unpatched___download_player_responses = YoutubeIE._download_player_responses
YoutubeIE._download_player_responses = PatchedYoutubeIE._download_player_responses

YoutubeIE.__unpatched___download_initial_webpage = YoutubeIE._download_initial_webpage
YoutubeIE._download_initial_webpage = PatchedYoutubeIE._download_initial_webpage