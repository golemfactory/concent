import datetime

from assertpy               import assert_that
from django.core.checks     import Error
from django.test            import override_settings
from django.test            import TestCase
from django.utils           import timezone
from mock                   import patch

from utils.helpers          import parse_datetime_to_timestamp
from utils.helpers          import parse_timestamp_to_utc_datetime
from utils.helpers          import storage_cluster_certificate_path_check


class HelpersTestCase(TestCase):

    def test_parse_datetime_to_timestamp_should_return_correct_utc_timestamp(self):
        """ Tests if parse_datetime_to_timestamp function works as expected. """

        timestamp = 946684800  # 2000-01-01 00:00
        assert datetime.datetime.fromtimestamp(timestamp) == datetime.datetime(2000, 1, 1, 0, 0)

        for date_time in [
            datetime.datetime(2000, 1, 1, 0, 0),
            datetime.datetime(2000, 1, 1, 0, 0,    tzinfo = timezone.pytz.timezone('UTC')),
            datetime.datetime(2000, 1, 1, 4, 37,   tzinfo = timezone.pytz.timezone('Asia/Kabul')),
            datetime.datetime(1999, 12, 31, 19, 4, tzinfo = timezone.pytz.timezone('US/Eastern')),
        ]:
            self.assertEqual(
                parse_datetime_to_timestamp(date_time),
                timestamp,
            )

        timestamp = 1321009860  # 2011-11-11 11:11
        assert datetime.datetime.fromtimestamp(timestamp) == datetime.datetime(2011, 11, 11, 11, 11)

        for date_time in [
            datetime.datetime(2011, 11, 11, 11, 11),
            datetime.datetime(2011, 11, 11, 11, 11, tzinfo = timezone.pytz.timezone('UTC')),
            datetime.datetime(2011, 11, 11, 20, 30, tzinfo = timezone.pytz.timezone('Asia/Tokyo')),
            datetime.datetime(2011, 11, 11, 1, 11,  tzinfo = timezone.pytz.timezone('US/Alaska')),
        ]:
            self.assertEqual(
                parse_datetime_to_timestamp(date_time),
                timestamp,
            )

    def test_parse_timestamp_to_utc_datetime_should_return_utc_datetime(self):
        """ Tests if parse_timestamp_to_utc_datetime function works as expected. """

        for timestamp, expected_datetime in {
            946684800:          datetime.datetime(year = 2000, month = 1,  day = 1,  hour = 0,  minute = 0,  second = 0,  tzinfo = timezone.utc),
            946684800 + 3666:   datetime.datetime(year = 2000, month = 1,  day = 1,  hour = 1,  minute = 1,  second = 6,  tzinfo = timezone.utc),
            1321009871:         datetime.datetime(year = 2011, month = 11, day = 11, hour = 11, minute = 11, second = 11, tzinfo = timezone.utc),
        }.items():
            self.assertEqual(
                parse_timestamp_to_utc_datetime(timestamp),
                expected_datetime
            )


# pylint: disable=R0201
class TestStorageClusterCertificatePathCheck(TestCase):
    file_with_wrong_extension = 'certificate.wrong_extension'

    @override_settings(
            STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = ''
    )
    def test_that_empty_string_does_not_produce_any_errors(self):
        errors = storage_cluster_certificate_path_check()

        assert_that(errors).is_instance_of(list)
        assert_that(errors).is_empty()

    @override_settings(
            STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = 'non_existing_path.crt'
    )
    def test_that_non_existing_path_produces_an_error(self):
        expected_error  = Error("File not found")
        errors          = storage_cluster_certificate_path_check()

        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(expected_error)

    @override_settings(
            STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = file_with_wrong_extension
    )
    @patch('utils.helpers.os.path.exists', return_value = True)
    def test_that_wrong_file_extension_produces_an_error(self, _):
        expected_error  = Error(f"{self.file_with_wrong_extension} is not a SSL certificate")
        errors          = storage_cluster_certificate_path_check()

        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(expected_error)

    @override_settings(
            STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = 'non_existing.wrong_extension'
    )
    @patch('utils.helpers.os.path.exists', return_value = False)
    @patch('utils.helpers.os.path.splitext', lambda x: (x[:-4], x[-4:]))
    def test_that_only_one_error_is_returned_and_path_existence_is_checked_first(self, _):
        expected_error  = Error("File not found")
        errors          = storage_cluster_certificate_path_check()

        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(expected_error)

    @override_settings(
            STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = 'existing_file.crt'
    )
    @patch('utils.helpers.os.path.exists', return_value = True)
    @patch('utils.helpers.os.path.splitext', lambda x: (x[:-4], x[-4:]))
    def test_that_correct_file_path_does_not_produce_any_error(self, _):
        errors = storage_cluster_certificate_path_check()

        assert_that(errors).is_instance_of(list)
        assert_that(errors).is_empty()
