import datetime

from django.test            import TestCase
from django.utils           import timezone

from golem_messages         import message
from utils.helpers          import join_messages
from utils.helpers          import parse_datetime_to_timestamp
from utils.helpers          import parse_timestamp_to_utc_datetime
from utils.helpers          import sign_message
from utils.testing_helpers  import generate_ecc_key_pair

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


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

    def test_add_signature_with_correct_keys_pair(self):
        ping_message = message.Ping()
        self.assertEqual(ping_message.sig, None)

        ping_message = sign_message(ping_message, CONCENT_PRIVATE_KEY)

        self.assertIsNot(ping_message.sig, None)
        self.assertIsInstance(ping_message.sig, bytes)

    def test_join_messages_should_return_joined_string_separeted_with_whitespace(self):
        """ Tests if join_messages function works as expected. """
        for messages, expected_join in {
            ('Error in Golem Message.', 'Invalid value'): 'Error in Golem Message. Invalid value',
            ('  Error in Golem Message.', '  Invalid value'): 'Error in Golem Message. Invalid value',
            ('Error in Golem Message.  ', 'Invalid value '): 'Error in Golem Message. Invalid value',
            ('Error in Golem Message.', 'Invalid value', 'for enum slot'): 'Error in Golem Message. Invalid value for enum slot',
            (' Error in Golem Message.', 'Invalid value ', 'for enum slot '): 'Error in Golem Message. Invalid value for enum slot',
        }.items():
            self.assertEqual(join_messages(*messages), expected_join)

    def test_join_messages_with_single_argument_should_return_single_string(self):
        self.assertEqual(join_messages('Error in Golem Message.'), 'Error in Golem Message.')
