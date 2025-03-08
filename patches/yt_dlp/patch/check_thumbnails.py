from yt_dlp import YoutubeDL
from yt_dlp.utils import sanitize_url, LazyList

class PatchedYoutubeDL(YoutubeDL):

    def _sanitize_thumbnails(self, info_dict):
        thumbnails = info_dict.get('thumbnails')
        if thumbnails is None:
            thumbnail = info_dict.get('thumbnail')
            if thumbnail:
                info_dict['thumbnails'] = thumbnails = [{'url': thumbnail}]
        if not thumbnails:
            return


        def check_thumbnails(thumbnails):
            for t in thumbnails:
                self.to_screen(f'[info] Testing thumbnail {t["id"]}: {t["url"]!r}')
                try:
                    self.urlopen(HEADRequest(t['url']))
                except network_exceptions as err:
                    self.to_screen(f'[info] Unable to connect to thumbnail {t["id"]} URL {t["url"]!r} - {err}. Skipping...')
                    continue
                yield t


        self._sort_thumbnails(thumbnails)
        for i, t in enumerate(thumbnails):
            if t.get('id') is None:
                t['id'] = str(i)
            if t.get('width') and t.get('height'):
                t['resolution'] = '%dx%d' % (t['width'], t['height'])
            t['url'] = sanitize_url(t['url'])


        if self.params.get('check_thumbnails') is True:
            info_dict['thumbnails'] = LazyList(check_thumbnails(thumbnails[::-1]), reverse=True)
        else:
            info_dict['thumbnails'] = thumbnails


YoutubeDL.__unpatched___sanitize_thumbnails = YoutubeDL._sanitize_thumbnails
YoutubeDL._sanitize_thumbnails = PatchedYoutubeDL._sanitize_thumbnails
