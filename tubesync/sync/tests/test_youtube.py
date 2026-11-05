import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
import yt_dlp
from yt_dlp.utils import DownloadError
from sync.youtube import (
    YouTubeError,
    _age_restricted,
    download_media,
    get_media_info,
)


AGE_RESTRICTED_MSG = (
    'ERROR: [youtube] abcdefghijk: Sign in to confirm your age. '
    'This video may be inappropriate for some users.'
)
COOKIES_CONTENT = '# Netscape HTTP Cookie File\n'
VIDEO_URL = 'https://www.youtube.com/watch?v=abcdefghijk'
REAL_YOUTUBEDL = yt_dlp.YoutubeDL


class AgeRestrictedCookiesTestCase(SimpleTestCase):
    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_dir = Path(temp_dir.name)
        self.cookies_file = self.temp_dir / 'cookies-age-restricted.txt'
        self.cookies_file.write_text(COOKIES_CONTENT)
        self.output_file = self.temp_dir / 'downloads' / 'video.mkv'
        self.output_file.parent.mkdir()
        # Record the options and the cookie file contents yt-dlp is given,
        # since the temporary cookie file is removed after the retry.
        self.seen_opts = list()
        self.seen_cookies = list()
        # match the container settings, which always set a cache directory
        cache_patcher = patch.dict(
            'sync.youtube._defaults', {'cachedir': str(self.temp_dir / 'cache')}
        )
        cache_patcher.start()
        self.addCleanup(cache_patcher.stop)
        patcher = patch('sync.youtube.yt_dlp.YoutubeDL')
        self.mock_ytdl = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_ytdl.side_effect = self._record_ytdl
        # yt_dlp.parse_options() validates templates using the real class
        self.mock_ytdl.validate_outtmpl = REAL_YOUTUBEDL.validate_outtmpl
        self.mock_y = self.mock_ytdl.return_value.__enter__.return_value

    def _record_ytdl(self, opts):
        self.seen_opts.append(opts)
        cookiefile = opts.get('cookiefile')
        self.seen_cookies.append(Path(cookiefile).read_text() if cookiefile else None)
        # yt-dlp saves updated cookies back to the file it was given
        if cookiefile:
            Path(cookiefile).write_text(COOKIES_CONTENT + '# updated\n')
        return self.mock_ytdl.return_value

    def _settings(self, **kwargs):
        kwargs.setdefault('AGE_RESTRICTED_COOKIES_FILE', self.cookies_file)
        kwargs.setdefault('COOKIES_FILE', self.temp_dir / 'cookies.txt')
        return override_settings(**kwargs)

    def _download(self):
        return download_media(
            VIDEO_URL,
            'bestvideo+bestaudio',
            'mkv',
            str(self.output_file),
            False,
            skip_sponsors=False,
        )

    def _assert_used_temporary_copy(self, opts):
        temp_cookies = Path(opts['cookiefile'])
        self.assertNotEqual(temp_cookies.resolve(), self.cookies_file.resolve())
        self.assertEqual(temp_cookies.name, self.cookies_file.name)
        self.assertEqual(self.seen_cookies[-1], COOKIES_CONTENT)
        # the temporary copy is removed and the original is left untouched
        self.assertFalse(temp_cookies.exists())
        self.assertEqual(self.cookies_file.read_text(), COOKIES_CONTENT)

    def test_age_restricted_messages(self):
        self.assertTrue(_age_restricted(AGE_RESTRICTED_MSG))
        self.assertTrue(
            _age_restricted(
                'ERROR: [youtube] abcdefghijk: This video is age-restricted'
            )
        )
        self.assertTrue(
            _age_restricted('This video may be inappropriate for some users.')
        )
        self.assertFalse(_age_restricted(''))
        self.assertFalse(
            _age_restricted('ERROR: [youtube] abcdefghijk: Video unavailable')
        )
        self.assertFalse(
            _age_restricted(
                'ERROR: [youtube] abcdefghijk: Join this channel to get access'
            )
        )

    def test_get_media_info_retries_with_age_restricted_cookies(self):
        self.mock_y.extract_info.side_effect = [
            DownloadError(AGE_RESTRICTED_MSG),
            {'id': 'abcdefghijk'},
        ]
        with self._settings():
            response = get_media_info(VIDEO_URL)
        self.assertEqual(response, {'id': 'abcdefghijk'})
        self.assertEqual(self.mock_y.extract_info.call_count, 2)
        self.assertEqual(len(self.seen_opts), 2)
        self.assertNotIn('cookiefile', self.seen_opts[0])
        self._assert_used_temporary_copy(self.seen_opts[1])

    def test_get_media_info_age_restricted_without_cookies_file(self):
        self.mock_y.extract_info.side_effect = DownloadError(AGE_RESTRICTED_MSG)
        with (
            self._settings(AGE_RESTRICTED_COOKIES_FILE=self.temp_dir / 'missing.txt'),
            self.assertRaises(YouTubeError),
        ):
            get_media_info(VIDEO_URL)
        self.assertEqual(self.mock_y.extract_info.call_count, 1)

    def test_get_media_info_other_errors_do_not_use_age_restricted_cookies(self):
        self.mock_y.extract_info.side_effect = DownloadError(
            'ERROR: [youtube] abcdefghijk: Video unavailable'
        )
        with self._settings(), self.assertRaises(YouTubeError):
            get_media_info(VIDEO_URL)
        self.assertEqual(self.mock_y.extract_info.call_count, 1)
        self.assertNotIn('cookiefile', self.seen_opts[0])

    def test_get_media_info_age_restricted_retry_fails(self):
        self.mock_y.extract_info.side_effect = DownloadError(AGE_RESTRICTED_MSG)
        with (
            self._settings(),
            self.assertRaisesRegex(YouTubeError, 'Failed \\(again\\)'),
        ):
            get_media_info(VIDEO_URL)
        self.assertEqual(self.mock_y.extract_info.call_count, 2)
        self._assert_used_temporary_copy(self.seen_opts[1])

    def test_get_media_info_regular_cookies_are_replaced_for_retry(self):
        regular_cookies = self.temp_dir / 'cookies.txt'
        regular_cookies.write_text(COOKIES_CONTENT)
        self.mock_y.extract_info.side_effect = [
            DownloadError(AGE_RESTRICTED_MSG),
            {'id': 'abcdefghijk'},
        ]
        with self._settings(COOKIES_FILE=regular_cookies):
            get_media_info(VIDEO_URL)
        self.assertEqual(
            self.seen_opts[0]['cookiefile'], str(regular_cookies.resolve())
        )
        self._assert_used_temporary_copy(self.seen_opts[1])

    def test_download_media_retries_with_age_restricted_cookies(self):
        self.mock_y.download.side_effect = [
            DownloadError(AGE_RESTRICTED_MSG),
            0,
        ]
        with self._settings():
            self.assertEqual(self._download(), 0)
        self.assertEqual(self.mock_y.download.call_count, 2)
        self.assertNotIn('cookiefile', self.seen_opts[0])
        self._assert_used_temporary_copy(self.seen_opts[1])

    def test_download_media_age_restricted_without_cookies_file(self):
        self.mock_y.download.side_effect = DownloadError(AGE_RESTRICTED_MSG)
        with (
            self._settings(AGE_RESTRICTED_COOKIES_FILE=None),
            self.assertRaises(YouTubeError),
        ):
            self._download()
        self.assertEqual(self.mock_y.download.call_count, 1)

    def test_download_media_other_errors_do_not_use_age_restricted_cookies(self):
        self.mock_y.download.side_effect = DownloadError(
            'ERROR: [youtube] abcdefghijk: Video unavailable'
        )
        with self._settings(), self.assertRaises(YouTubeError):
            self._download()
        self.assertEqual(self.mock_y.download.call_count, 1)

    def test_download_media_age_restricted_retry_fails(self):
        self.mock_y.download.side_effect = DownloadError(AGE_RESTRICTED_MSG)
        with (
            self._settings(),
            self.assertRaisesRegex(YouTubeError, 'Failed to download'),
        ):
            self._download()
        self.assertEqual(self.mock_y.download.call_count, 2)
        self._assert_used_temporary_copy(self.seen_opts[1])
