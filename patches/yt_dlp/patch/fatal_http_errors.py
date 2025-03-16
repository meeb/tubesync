from yt_dlp.extractor.youtube import YoutubeIE


class PatchedYoutubeIE(YoutubeIE):

    def _download_player_responses(self, url, smuggled_data, video_id, webpage_url):
        webpage = None
        if 'webpage' not in self._configuration_arg('player_skip'):
            query = {'bpctr': '9999999999', 'has_verified': '1'}
            pp = self._configuration_arg('player_params', [None], casesense=True)[0]
            if pp:
                query['pp'] = pp
            webpage = self._download_webpage_with_retries(webpage_url, video_id, retry_fatal=True, query=query)

        master_ytcfg = self.extract_ytcfg(video_id, webpage) or self._get_default_ytcfg()

        player_responses, player_url = self._extract_player_responses(
            self._get_requested_clients(url, smuggled_data),
            video_id, webpage, master_ytcfg, smuggled_data)

        return webpage, master_ytcfg, player_responses, player_url


YoutubeIE.__unpatched___download_player_responses = YoutubeIE._download_player_responses
YoutubeIE._download_player_responses = PatchedYoutubeIE._download_player_responses
