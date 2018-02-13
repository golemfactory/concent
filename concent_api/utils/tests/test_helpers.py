import datetime

from django.test            import TestCase
from django.utils           import timezone

from utils.helpers          import parse_datetime_to_timestamp


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
