from unittest import TestCase
from assertpy import assert_that
import mock
import pytest

from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.factories.tasks import SubtaskResultsAcceptedFactory
from golem_messages.factories.tasks import TaskToComputeFactory
from golem_messages.factories.tasks import WantToComputeTaskFactory
from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import SubtaskResultsRejected
from golem_messages.message.tasks import TaskToCompute
from golem_messages.message.tasks import WantToComputeTask
from golem_messages.utils import encode_hex
from common.constants import ErrorCode
from common.exceptions import ConcentValidationError
from common.exceptions import NonPositivePriceTaskToComputeError
from common.helpers import sign_message
from common.testing_helpers import generate_ecc_key_pair
from common.testing_helpers import generate_priv_and_pub_eth_account_key
from common.validations import validate_secure_hash_algorithm

from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.constants import MESSAGE_TASK_ID_MAX_LENGTH
from core.exceptions import FrameNumberValidationError
from core.exceptions import HashingAlgorithmError
from core.subtask_helpers import are_keys_and_addresses_unique_in_message_subtask_results_accepted
from core.subtask_helpers import are_subtask_results_accepted_messages_signed_by_the_same_requestor
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import generate_uuid_for_tests
from core.validation import validate_all_messages_identical, validate_blender_output_format
from core.validation import validate_compute_task_def
from core.validation import validate_ethereum_addresses
from core.validation import validate_frames
from core.validation import validate_golem_message_subtask_results_rejected
from core.validation import validate_positive_task_price
from core.validation import validate_non_negative_integer_value
from core.validation import validate_positive_integer_value
from core.validation import validate_scene_file
from core.validation import validate_task_to_compute
from core.validation import validate_uuid


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_PROVIDER_PRIVATE_KEY, DIFFERENT_PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_REQUESTOR_PRIVATE_KEY, DIFFERENT_REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()
(PROVIDER_PRIV_ETH_KEY, PROVIDER_PUB_ETH_KEY) = generate_priv_and_pub_eth_account_key()
(REQUESTOR_PRIV_ETH_KEY, REQUESTOR_PUB_ETH_KEY) = generate_priv_and_pub_eth_account_key()
(DIFFERENT_PROVIDER_PRIV_ETH_KEY, DIFFERENT_PROVIDER_PUB_ETH_KEY) = generate_priv_and_pub_eth_account_key()
(DIFFERENT_REQUESTOR_PRIV_ETH_KEY, DIFFERENT_REQUESTOR_PUB_ETH_KEY) = generate_priv_and_pub_eth_account_key()


class TestValidateGolemMessageSubtaskResultsRejected(TestCase):
    def test_that_exception_is_raised_when_subtask_results_rejected_is_of_wrong_type(self):
        with self.assertRaises(ConcentValidationError):
            validate_golem_message_subtask_results_rejected(None)

    def test_that_exception_is_raised_when_subtask_results_rejected_contains_invalid_task_to_compute(self):
        task_to_compute = TaskToCompute(want_to_compute_task=WantToComputeTask())
        report_computed_task = ReportComputedTask(task_to_compute=task_to_compute)
        subtask_results_rejected = SubtaskResultsRejected(report_computed_task=report_computed_task)
        with self.assertRaises(ConcentValidationError):
            validate_golem_message_subtask_results_rejected(subtask_results_rejected)


class ValidatorsTest(TestCase):
    def test_that_function_raises_exception_when_ethereum_addres_has_wrong_type(self):
        with self.assertRaises(ConcentValidationError):
            validate_ethereum_addresses(int('1' * ETHEREUM_ADDRESS_LENGTH), 'a' * ETHEREUM_ADDRESS_LENGTH)

        with self.assertRaises(ConcentValidationError):
            validate_ethereum_addresses('a' * ETHEREUM_ADDRESS_LENGTH, int('1' * ETHEREUM_ADDRESS_LENGTH))

        with self.assertRaises(ConcentValidationError):
            validate_ethereum_addresses(int('1' * ETHEREUM_ADDRESS_LENGTH), int('1' * ETHEREUM_ADDRESS_LENGTH))

    def test_that_function_raises_exception_when_ethereum_addres_has_wrong_length(self):
        with self.assertRaises(ConcentValidationError):
            validate_ethereum_addresses('a' * 5, 'b' * 5)

        with self.assertRaises(ConcentValidationError):
            validate_ethereum_addresses('a' * 5, 'b' * ETHEREUM_ADDRESS_LENGTH)

        with self.assertRaises(ConcentValidationError):
            validate_ethereum_addresses('a' * ETHEREUM_ADDRESS_LENGTH, 'b' * 5)


class TestIntegerValidations:

    @pytest.mark.parametrize(('value', 'error_code'), [
        ('5', ErrorCode.MESSAGE_VALUE_WRONG_TYPE),
        (-5, ErrorCode.MESSAGE_VALUE_NEGATIVE),
        (0, ErrorCode.MESSAGE_VALUE_NEGATIVE),
    ])  # pylint: disable=no-self-use
    def test_that_validate_positive_integer_function_raise_exception_when_wrong_value_given(self, value, error_code):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_positive_integer_value(value)
        assert_that(exception_wrapper.value.error_code).is_equal_to(error_code)

    @pytest.mark.parametrize(('value', 'error_code'), [
        ('5', ErrorCode.MESSAGE_VALUE_WRONG_TYPE),
        (-5, ErrorCode.MESSAGE_VALUE_NEGATIVE),
    ])  # pylint: disable=no-self-use
    def test_that_validate_non_negative_integer_function_raise_exception_when_wrong_value_given(self, value, error_code):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_non_negative_integer_value(value)
        assert_that(exception_wrapper.value.error_code).is_equal_to(error_code)

    def test_that_validate_positive_price_value_causes_non_positive_price_error(self):  # pylint: disable=no-self-use
        with pytest.raises(NonPositivePriceTaskToComputeError):
            validate_positive_task_price(0)


class TestValidateAllMessagesIdentical(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.report_computed_task = self._get_deserialized_report_computed_task()

    def test_that_function_pass_when_in_list_is_one_item(self):

        try:
            validate_all_messages_identical([self.report_computed_task])
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_function_pass_when_in_list_are_two_same_report_computed_task(self):
        try:
            validate_all_messages_identical([self.report_computed_task, self.report_computed_task])
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_function_raise_http400_when_any_slot_will_be_different_in_messages(self):
        different_report_computed_task = self._get_deserialized_report_computed_task(size = 10)
        with self.assertRaises(ConcentValidationError):
            validate_all_messages_identical([self.report_computed_task, different_report_computed_task])


UUID: str = generate_uuid_for_tests()


class TestValidateIdValue:

    @pytest.mark.parametrize('id_', [
        UUID.replace('-', ''),
        UUID,
    ])  # pylint: disable=no-self-use
    def test_that_function_should_pass_when_value_is_allowed(self, id_):

        try:
            validate_uuid(id_)
        except Exception as exception:  # pylint: disable=broad-except
            pytest.fail(f'{exception}')

    @pytest.mark.parametrize('id_', [
        f'{UUID}{UUID}',
        UUID[1:],
        UUID[:-1],
        UUID + '1',
        '',
    ])  # pylint: disable=no-self-use
    def test_that_function_should_raise_exception_when_value_is_not_allowed(self, id_):

        with pytest.raises(ConcentValidationError) as exception:
            validate_uuid(id_)
        assert_that(exception.value.error_code).is_equal_to(ErrorCode.MESSAGE_WRONG_UUID_VALUE)

    @pytest.mark.parametrize('id_', [
        int('1' * MESSAGE_TASK_ID_MAX_LENGTH),
        None
    ])  # pylint: disable=no-self-use
    def test_that_function_should_raise_exception_when_type_is_not_allowed(self, id_):

        with pytest.raises(ConcentValidationError) as exception:
            validate_uuid(id_)
        assert_that(exception.value.error_code).is_equal_to(ErrorCode.MESSAGE_WRONG_UUID_TYPE)


class TestInvalidHashAlgorithms(TestCase):

    def test_that_validation_should_raise_exception_when_checksum_is_invalid(self):
        invalid_values_with_expected_error_code = {
            123456789: ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_TYPE,
            '': ErrorCode.MESSAGE_FILES_CHECKSUM_EMPTY,
            'sha14452d71687b6bc2c9389c3349fdc17fbd73b833b': ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_FORMAT,
            'sha2:4452d71687b6bc2c9389c3349fdc17fbd73b833b': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            'sha1:xyz2d71687b6bc2c9389c3349fdc17fbd73b833b': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
            'sha1:': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
        }
        for invalid_value, error_code in invalid_values_with_expected_error_code.items():
            with self.assertRaises(HashingAlgorithmError) as context:
                validate_secure_hash_algorithm(invalid_value)
            self.assertEqual(context.exception.error_code, error_code)


class TestAreEthereumAddressesAndKeysUnique(TestCase):

    def setUp(self):
        self.task_to_compute_1 = TaskToComputeFactory(
            requestor_ethereum_public_key=encode_hex(REQUESTOR_PUB_ETH_KEY),
            requestor_public_key=encode_hex(REQUESTOR_PUBLIC_KEY),
            want_to_compute_task=WantToComputeTaskFactory(
                provider_ethereum_public_key=encode_hex(PROVIDER_PUB_ETH_KEY),
                provider_public_key=encode_hex(PROVIDER_PUBLIC_KEY),
            ),
        )
        self.task_to_compute_1.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        self.task_to_compute_2 = TaskToComputeFactory(
            requestor_ethereum_public_key=encode_hex(REQUESTOR_PUB_ETH_KEY),
            requestor_public_key=encode_hex(REQUESTOR_PUBLIC_KEY),
            want_to_compute_task=WantToComputeTaskFactory(
                provider_ethereum_public_key=encode_hex(PROVIDER_PUB_ETH_KEY),
                provider_public_key=encode_hex(PROVIDER_PUBLIC_KEY),
            ),
        )
        self.task_to_compute_2.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)

    def create_subtask_results_accepted_list(  # pylint: disable=no-self-use
        self,
        task_to_compute_1,
        task_to_compute_2,
        subtask_1_signed_by=REQUESTOR_PRIVATE_KEY,
        subtask_2_signed_by=REQUESTOR_PRIVATE_KEY,
    ) -> list:
        subtask_results_accepted_1 = SubtaskResultsAcceptedFactory(
            report_computed_task=ReportComputedTaskFactory(
                task_to_compute=task_to_compute_1
            )
        )
        sign_message(subtask_results_accepted_1, subtask_1_signed_by)
        subtask_results_accepted_2 = SubtaskResultsAcceptedFactory(
            report_computed_task=ReportComputedTaskFactory(
                task_to_compute=task_to_compute_2
            )
        )
        sign_message(subtask_results_accepted_2, subtask_2_signed_by)
        subtask_results_accepted_list = [
            subtask_results_accepted_1,
            subtask_results_accepted_2,
        ]
        return subtask_results_accepted_list

    def test_that_if_the_same_values_given_method_should_return_true(self):
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(self.task_to_compute_1, self.task_to_compute_2)
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_true()

    def test_that_if_different_requestor_ethereum_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.requestor_ethereum_public_key = encode_hex(DIFFERENT_REQUESTOR_PUB_ETH_KEY)
        self.task_to_compute_2.generate_ethsig(DIFFERENT_REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(self.task_to_compute_1, self.task_to_compute_2)
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_different_requestor_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.requestor_public_key = encode_hex(DIFFERENT_REQUESTOR_PUBLIC_KEY)
        self.task_to_compute_2.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(self.task_to_compute_1, self.task_to_compute_2)
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_different_provider_ethereum_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.want_to_compute_task.provider_ethereum_public_key = encode_hex(DIFFERENT_PROVIDER_PUB_ETH_KEY)
        self.task_to_compute_2.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(self.task_to_compute_1, self.task_to_compute_2)
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_different_provider_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.want_to_compute_task.provider_public_key = encode_hex(DIFFERENT_PROVIDER_PUBLIC_KEY)
        self.task_to_compute_2.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(self.task_to_compute_1, self.task_to_compute_2)
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_messages_are_signed_by_different_requestors_method_should_return_false(self):
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(
            self.task_to_compute_1,
            self.task_to_compute_2,
            subtask_2_signed_by=DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )
        result = are_subtask_results_accepted_messages_signed_by_the_same_requestor(subtask_results_accepted_list)
        assert_that(result).is_false()


class TestFramesListValidation(TestCase):

    def test_that_list_of_ints_is_valid(self):
        try:
            validate_frames([1, 2])
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_if_frames_is_not_a_list_of_ints_method_should_raise_exception(self):
        with self.assertRaises(FrameNumberValidationError):
            validate_frames({'1': 1})

        with self.assertRaises(FrameNumberValidationError):
            validate_frames((1, 2))

    def test_that_if_frames_are_not_grater_than_0_method_should_raise_exception(self):
        with self.assertRaises(FrameNumberValidationError):
            validate_frames([-1, 1])

        with self.assertRaises(FrameNumberValidationError):
            validate_frames([0, 1])

    def test_that_if_frames_are_not_one_after_the_other_method_should_pass(self):
        try:
            validate_frames([1, 3, 5])
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_if_frames_are_not_integers_method_should_raise_exception(self):
        with self.assertRaises(FrameNumberValidationError):
            validate_frames(['1', '2'])


class TestValidateComputeTaskDef(object):
    compute_task_def = None

    @pytest.fixture(autouse=True)
    def setup(self):
        self.compute_task_def = ComputeTaskDefFactory()
        self.compute_task_def["extra_data"] = {
            "output_format": "PNG",
            "scene_file": "/golem/resources/nice_photo.blend",
            "frames": [1, 2, 3],
        }

    def test_that_valid_compute_task_def_doesnt_raise_any_exception(self):
        try:
            validate_compute_task_def(self.compute_task_def)
        except Exception as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"

    def test_that_mising_extra_data_causes_message_validation_error(self):
        del self.compute_task_def['extra_data']
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_compute_task_def(self.compute_task_def)
        assert_that(exception_wrapper.value.error_message).contains(f"extra_data")
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        "missing_data", [
            "output_format",
            "scene_file",
            "frames",
        ]
    )
    def test_that_missing_entries_in_extra_data_causes_message_validation_error(self, missing_data):
        del self.compute_task_def["extra_data"][missing_data]
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_compute_task_def(self.compute_task_def)
        assert_that(exception_wrapper.value.error_message).contains(f"{missing_data}")
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        "value_with_wrong_type", [
            "output_format",
            "scene_file",
        ]
    )
    def test_that_wrong_field_types_causes_message_validation_error(self, value_with_wrong_type):
        self.compute_task_def["extra_data"][value_with_wrong_type] = mock.sentinel.wrongtype
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_compute_task_def(self.compute_task_def)
        assert_that(exception_wrapper.value.error_message).contains(f"{value_with_wrong_type}")
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_VALUE_NOT_STRING)


class TestValidateSceneFile:

    @pytest.mark.parametrize(
        'scene_file', [
            '/golem/resources/scene_file.png',
            'golem/resources/scene_file.blend',
            'resources/abc/scene_file.blend',
            '/resources/abc/scene_file.blend',
            '/golem/scene_file.blend',
        ]  # pylint: disable=no-self-use
    )
    def test_that_wrong_scene_file_name_causes_validation_error(self, scene_file):  # pylint: disable=no-self-use
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_scene_file(scene_file)
        assert_that(exception_wrapper.value.error_message).contains(f'{scene_file}')
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        'scene_file', [
            '/golem/resources/scene_file.blend',
            '/golem/resources/abc/scene_file.blend',
        ]  # pylint: disable=no-self-use
    )
    def test_that_valid_scene_file_name_doesnt_raise_any_error(self, scene_file):
        try:
            validate_scene_file(scene_file)
        except Exception as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"


class TestValidateTaskToCompute(object):

    @pytest.fixture(autouse=True)
    def setUp(self):
        self.task_to_compute = TaskToComputeFactory()

    def test_that_valid_task_to_compute_doesnt_raise_any_exception(self):
        try:
            validate_task_to_compute(self.task_to_compute)
        except Exception as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"

    def test_that_other_messages_than_task_to_compute_causes_message_validation_error(self):  # pylint: disable=no-self-use
        wrong_message = ComputeTaskDefFactory()
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_task_to_compute(wrong_message)
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)


class TestValidateOutputFormat:

    @pytest.mark.parametrize(
        'output_format', [
            'JPEG',
            'PNG',
            'EXR'
        ]
    )  # pylint: disable=no-self-use
    def test_that_valid_output_formats_dont_raise_any_exception(self, output_format):
        try:
            validate_blender_output_format(output_format)
        except Exception as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"

    def test_that_unsupported_format_raises_concent_validation_error(self):  # pylint: disable=no-self-use
        unsupported_format = 'BMP'
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_blender_output_format(unsupported_format)
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_VALUE_NOT_ALLOWED)
