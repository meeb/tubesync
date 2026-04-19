import uuid
from django.db import IntegrityError
from django.test import TestCase
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from sync.models import Codec, Subtitle


class SubtitleModelTestCase(TestCase):
    '''Example-based tests for the Subtitle model.'''

    def _make_codec(self):
        codec, _ = Codec.objects.get_or_create(
            asset_type='subtitle',
            codec='vtt',
            defaults={
                'uuid': uuid.uuid4(),
                'description': 'Web Video Text Tracks',
            },
        )
        return codec

    def test_create_with_valid_fields(self):
        # Req 8.1: create with valid fields and codec=None persists without error
        subtitle = Subtitle.objects.create(
            language='en-US',
            extension='vtt',
            original_language=None,
            machine_generated=False,
            codec=None,
        )
        self.assertIsNotNone(subtitle.pk)

    def test_original_language_none_stores_null(self):
        # Req 8.2 / 1.3: original_language=None stores NULL, not empty string
        Subtitle.objects.create(
            language='en-US',
            extension='vtt',
            original_language=None,
        )
        subtitle = Subtitle.objects.get(language='en-US', extension='vtt')
        self.assertIsNone(subtitle.original_language)

    def test_duplicate_language_extension_raises_integrity_error(self):
        # Req 8.3 / 2.1 / 2.2: unique_together on (language, extension)
        Subtitle.objects.create(language='en-US', extension='vtt')
        with self.assertRaises(IntegrityError):
            Subtitle.objects.create(language='en-US', extension='vtt')

    def test_str_representation(self):
        # Req 8.4 / 3.1: __str__ returns '{language} ({extension})'
        subtitle = Subtitle(language='en-US', extension='vtt')
        self.assertEqual(str(subtitle), 'en-US (vtt)')

    def test_machine_generated_defaults_to_false(self):
        # Req 1.4: machine_generated defaults to False
        subtitle = Subtitle.objects.create(language='fr-FR', extension='srt')
        self.assertFalse(subtitle.machine_generated)

    def test_codec_set_null_on_codec_deletion(self):
        # Req 1.5: SET_NULL — deleting Codec sets subtitle.codec to None
        codec = self._make_codec()
        subtitle = Subtitle.objects.create(
            language='es-US',
            extension='vtt',
            codec=codec,
        )
        codec.delete()
        subtitle.refresh_from_db()
        self.assertIsNone(subtitle.codec)


class SubtitleStrPropertyTest(HypothesisTestCase):
    '''Property-based test: __str__ format is universal (Property 1).'''

    @given(
        language=st.text(min_size=1, max_size=16).filter(lambda s: s == s.strip()),
        extension=st.text(min_size=1, max_size=8).filter(lambda s: s == s.strip()),
    )
    @settings(max_examples=100)
    def test_str_format_property(self, language, extension):
        # Property 1: for any non-empty language and extension,
        # str(Subtitle) == f'{language} ({extension})'
        subtitle = Subtitle(language=language, extension=extension)
        self.assertEqual(str(subtitle), f'{language} ({extension})')

