from assertpy import assert_that
from django.conf import settings

from django.test import override_settings
import pytest

from concent_api.system_check import check_verifier_download_chunk_size
from concent_api.system_check import create_error_29_verifier_download_chunk_size_is_not_defined
from concent_api.system_check import create_error_30_verifier_download_chunk_size_has_wrong_type
from concent_api.system_check import create_error_31_verifier_download_chunk_size_has_wrong_value


# pylint: disable=no-self-use
class TestVerifierDownloadChunkSize():

    @pytest.mark.parametrize(('verifier_download_chunk_size', 'verifier_feature', 'expected'), [
        (1, ['verifier'], []),
        (None, ['verifier'], [create_error_30_verifier_download_chunk_size_has_wrong_type(type(None))]),
        ('1', ['verifier'], [create_error_30_verifier_download_chunk_size_has_wrong_type(str)]),
        (-1, ['verifier'], [create_error_31_verifier_download_chunk_size_has_wrong_value(-1)]),
        (0, ['verifier'], [create_error_31_verifier_download_chunk_size_has_wrong_value(0)]),
        (1, [], []),
        (-1, [], []),
    ])
    def test_verifier_download_chunk_size_system_check(self, verifier_download_chunk_size, verifier_feature, expected):
        with override_settings(
            VERIFIER_DOWNLOAD_CHUNK_SIZE=verifier_download_chunk_size,
            CONCENT_FEATURES=verifier_feature,
        ):
            errors = check_verifier_download_chunk_size()

        assert_that(errors).is_equal_to(expected)

    def test_that_verifier_download_chunk_size_is_not_set_when_verifier_is_in_concent_features(self):
        with override_settings(CONCENT_FEATURES=['verifier']):
            del settings.VERIFIER_DOWNLOAD_CHUNK_SIZE

            errors = check_verifier_download_chunk_size()

        assert_that(errors).is_equal_to([create_error_29_verifier_download_chunk_size_is_not_defined()])
