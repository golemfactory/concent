import uuid
from assertpy import assert_that

from core.constants import REGEX_FOR_VALID_UUID


class TestRegexForValidUUID():
    def test_that_regex_matches_uuid(self):  # pylint: disable=no-self-use
        assert_that(str(uuid.uuid4())).matches(REGEX_FOR_VALID_UUID)
