from unittest import TestCase
from assertpy import assert_that
import mock
import pytest
from freezegun import freeze_time

from golem_messages.factories.concents import SubtaskResultsVerifyFactory
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.factories.tasks import SubtaskResultsAcceptedFactory
from golem_messages.factories.tasks import TaskToComputeFactory
from golem_messages.factories.tasks import WantToComputeTaskFactory
from golem_messages.message.concents import ForceGetTaskResultFailed
from golem_messages.message.concents import SubtaskResultsVerify
from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import SubtaskResultsRejected
from golem_messages.message.tasks import TaskToCompute
from golem_messages.message.tasks import WantToComputeTask
from golem_messages.utils import encode_hex
from golem_messages.utils import pubkey_to_address

from django.conf import settings

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
from core.exceptions import GolemMessageValidationError
from core.exceptions import HashingAlgorithmError
from core.subtask_helpers import are_keys_and_addresses_unique_in_message_subtask_results_accepted
from core.subtask_helpers import are_subtask_results_accepted_messages_signed_by_the_same_requestor
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import generate_uuid_for_tests
from core.validation import validate_all_messages_identical
from core.validation import validate_blender_output_format
from core.validation import validate_blender_script_parameters
from core.validation import validate_crops
from core.validation import validate_resolution
from core.validation import validate_samples
from core.validation import validate_use_compositing
from core.validation import validate_compute_task_def
from core.validation import validate_ethereum_addresses
from core.validation import validate_frames
from core.validation import validate_golem_message_subtask_results_rejected
from core.validation import validate_positive_task_price
from core.validation import validate_non_negative_integer_value
from core.validation import validate_positive_integer_value
from core.validation import validate_scene_file
from core.validation import validate_subtask_results_rejected_reason
from core.validation import validate_subtask_results_verify
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
                provider_public_key=encode_hex(PROVIDER_PUBLIC_KEY),
            ),
        )
        self.task_to_compute_1.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        self.task_to_compute_2 = TaskToComputeFactory(
            requestor_ethereum_public_key=encode_hex(REQUESTOR_PUB_ETH_KEY),
            requestor_public_key=encode_hex(REQUESTOR_PUBLIC_KEY),
            want_to_compute_task=WantToComputeTaskFactory(
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
        with freeze_time():
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
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(
            self.task_to_compute_1,
            self.task_to_compute_2,
        )
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_true()

    def test_that_if_different_requestor_ethereum_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.requestor_ethereum_public_key = encode_hex(DIFFERENT_REQUESTOR_PUB_ETH_KEY)
        self.task_to_compute_2.generate_ethsig(DIFFERENT_REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(
            self.task_to_compute_1,
            self.task_to_compute_2,
        )
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_different_requestor_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.requestor_public_key = encode_hex(DIFFERENT_REQUESTOR_PUBLIC_KEY)
        self.task_to_compute_2.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(
            self.task_to_compute_1,
            self.task_to_compute_2,
        )
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_different_provider_ethereum_addresses_are_given_method_should_return_false(self):
        self.task_to_compute_2.want_to_compute_task.provider_ethereum_address = pubkey_to_address(
            DIFFERENT_PROVIDER_PUB_ETH_KEY
        )
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(
            self.task_to_compute_1,
            self.task_to_compute_2,
        )
        result = are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list)
        assert_that(result).is_false()

    def test_that_if_different_provider_public_keys_are_given_method_should_return_false(self):
        self.task_to_compute_2.want_to_compute_task.provider_public_key = encode_hex(DIFFERENT_PROVIDER_PUBLIC_KEY)
        self.task_to_compute_2.generate_ethsig(REQUESTOR_PRIV_ETH_KEY)
        subtask_results_accepted_list = self.create_subtask_results_accepted_list(
            self.task_to_compute_1,
            self.task_to_compute_2,
        )
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
        (REQUESTOR_ETHEREUM_PRIVATE_KEY, REQUESTOR_ETHERUM_PUBLIC_KEY) = generate_ecc_key_pair()
        self.task_to_compute = TaskToComputeFactory(requestor_ethereum_public_key=encode_hex(REQUESTOR_ETHERUM_PUBLIC_KEY))
        self.task_to_compute.generate_ethsig(REQUESTOR_ETHEREUM_PRIVATE_KEY)
        self.task_to_compute.sign_all_promissory_notes(
            deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=REQUESTOR_ETHEREUM_PRIVATE_KEY,
        )

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


class TestValidateSceneResolution:

    @pytest.mark.parametrize(
        'resolution', [
            '400x400',
            [0, 0],
            [100, 0],
            [0, 100],
            [-100, 100],
            [100, -100],
            ['100', 100],
            [],
            ['400x800'],
            [71830.23, 1000],
        ]
    )  # pylint: disable=no-self-use
    def test_that_invalid_resolution_value_raise_exception(self, resolution):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_resolution(resolution)
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        'resolution', [
            [1, 1],
            [100000000, 100000000],
        ]
    )  # pylint: disable=no-self-use
    def test_that_valid_resolution_value_doesnt_raise_exception(self, resolution):
        try:
            validate_resolution(resolution)
        except Exception as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"


class TestValidateSceneUseCompositing:

    @pytest.mark.parametrize(
        'use_compositing', [
            'True',
            1,
            [True]
        ]
    )  # pylint: disable=no-self-use
    def test_that_invalid_use_compositing_value_raise_exception(self, use_compositing):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_use_compositing(use_compositing)
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        'use_compositing', [
            True,
            False
        ]
    )  # pylint: disable=no-self-use
    def test_that_valid_use_compositing_value_doesnt_raise_exception(self, use_compositing):
        try:
            validate_use_compositing(use_compositing)
        except ConcentValidationError as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"


class TestValidateSceneSamples:

    @pytest.mark.parametrize(
        'samples', [
            [1],
            1.2,
            '1',
            -1,
        ]
    )  # pylint: disable=no-self-use
    def test_that_invalid_samples_value_raise_exception(self, samples):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_samples(samples)
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        'samples', [
            0,
            1,
            1000000000,
        ]
    )  # pylint: disable=no-self-use
    def test_that_valid_samples_value_doesnt_raise_exception(self, samples):
        try:
            validate_samples(samples)
        except ConcentValidationError as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"


class TestValidateSceneCrop:

    def create_crop_dict(self, borders_x, borders_y):  # pylint: disable=no-self-use
        return dict(
            borders_x=borders_x,
            borders_y=borders_y,
        )

    @pytest.mark.parametrize(
        ['borders_x', 'borders_y'], [
            [[0.0, 1.0], [0.0, 1.0]],
            [[0.71830, 1.0], [0.9, 1.0]],
        ]
    )
    def test_that_valid_crops_value_doesnt_raise_exception(self, borders_x, borders_y):
        try:
            validate_crops([self.create_crop_dict(borders_x, borders_y)])
        except ConcentValidationError as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"

    @pytest.mark.parametrize(
        ['borders_x', 'borders_y'], [
            [[0, 1], [0.0, 1.0]],
            [[0.0, 1.0], [0, 1]],
            [[1.0, 1.0], [0.0, 1.0]],
            [[0.0, 1.0], [1.0, 1.0]],
            [[0.5, 0.4], [0.0, 1.0]],
            [[0.0, 1.0], [0.5, 0.4]],
            [[1.0], [0.1, 0.0]],
            [[0.0, 1.0], [1.0]],
            [[], [0.0, 1.0]],
            [[0.0, 1.0], []],
            [(0.0, 1.0), [0.0, 1.0]],
            [[0.0, 1.0], (0.0, 1.0)],
            [None, [0.0, 1.0]],
            [[0.0, 1.0], None],
            [[0.0, 2.0], [0.0, 1.0]],
            [[0.0, 1.0], [0.0, 2.0]],
            [[-1.0, 1.0], [0.0, 1.0]],
            [[0.0, 1.0], [-1.0, 1.0]],
        ]
    )
    def test_that_invalid_borders_values_in_crops_dict_raise_exception(self, borders_x, borders_y):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_crops([self.create_crop_dict(borders_x, borders_y)])
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)

    @pytest.mark.parametrize(
        'crops', [
            [
                dict(borders_x=[0.0, 1.0], borders_y=[0.0, 1.0]),
                dict(borders_x=[0.0, 1.0], borders_y=[0.0, 1.0]),
            ],
            (
                dict(borders_x=[0.0, 1.0], borders_y=[0.0, 1.0]),
            ),
            [
                dict(borders_x=[0.0, 1.0]),
            ],
            [
                dict(borders_y=[0.0, 1.0]),
            ]
        ]
    )  # pylint: disable=no-self-use
    def test_that_invalid_crops_list_raise_exception(self, crops):
        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_crops(crops)
        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)


@mock.patch('core.validation.validate_use_compositing')
@mock.patch('core.validation.validate_samples')
@mock.patch('core.validation.validate_crops')
@mock.patch('core.validation.validate_resolution')
class TestValidateBlenderScriptParameters:

    @pytest.fixture(autouse=True)
    def _create_blender_script_parameters(self, resolution=None, use_compositing=None, samples=None, crops=None):  # pylint: disable=no-self-use
        return dict(
            resolution=resolution,
            use_compositing=use_compositing,
            samples=samples,
            crops=crops,
        )

    def test_that_valid_extra_data_doesnt_raise_exception(self, mocked_use_compositing_validator, mocked_samples_validator, mocked_crops_validator, mocked_resolution_validator):
        try:
            validate_blender_script_parameters(self._create_blender_script_parameters())
        except Exception as exception:  # pylint: disable=broad-except
            assert False, f"Unexpected exception has been raised: {str(exception)}"

        assert_that(mocked_use_compositing_validator.called).is_true()
        assert_that(mocked_samples_validator.called).is_true()
        assert_that(mocked_crops_validator.called).is_true()
        assert_that(mocked_resolution_validator.called).is_true()

    @pytest.mark.parametrize(
        'field_to_delete', [
            'resolution',
            'use_compositing',
            'samples',
            'crops',
        ]
    )
    def test_that_invalid_extra_data_raise_exception(self, mocked_use_compositing_validator, mocked_samples_validator, mocked_crops_validator, mocked_resolution_validator, field_to_delete):
        extra_data = self._create_blender_script_parameters()
        extra_data.pop(field_to_delete)

        with pytest.raises(ConcentValidationError) as exception_wrapper:
            validate_blender_script_parameters(extra_data)

        assert_that(exception_wrapper.value.error_code).is_equal_to(ErrorCode.MESSAGE_INVALID)
        assert_that(field_to_delete in exception_wrapper.value.error_message).is_true()
        assert_that(mocked_use_compositing_validator.called).is_false()
        assert_that(mocked_samples_validator.called).is_false()
        assert_that(mocked_crops_validator.called).is_false()
        assert_that(mocked_resolution_validator.called).is_false()


class TestValidateSubtaskResultsVerify:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.provider_private_key, self.provider_public_key = generate_ecc_key_pair()
        self.deposit_contract_address = '0xcfB81A6EE3ae6aD4Ac59ddD21fB4589055c13DaD'

        want_to_compute_task = WantToComputeTaskFactory(
            provider_public_key=encode_hex(self.provider_public_key)
        )
        arguments = {
            'subtask_results_rejected__'
            'report_computed_task__'
            'task_to_compute__'
            'want_to_compute_task': want_to_compute_task
        }
        self.subtask_results_verify: SubtaskResultsVerify = SubtaskResultsVerifyFactory(**arguments)

    def test_that_correct_signature_doesnt_raise_any_exception(self):
        self.subtask_results_verify.sign_concent_promissory_note(
            self.deposit_contract_address,
            self.provider_private_key,
        )
        try:
            validate_subtask_results_verify(self.subtask_results_verify, self.deposit_contract_address)
        except Exception as exception:  # pylint: disable=broad-except
            pytest.fail(f"Unexpected exception has been raised: {exception}")

    def test_that_incorrect_signature_raises_concent_validation_error(self):
        different_provider_private_key, _ = generate_ecc_key_pair()

        self.subtask_results_verify.sign_concent_promissory_note(
            self.deposit_contract_address,
            different_provider_private_key,
        )
        with pytest.raises(ConcentValidationError):
            validate_subtask_results_verify(self.subtask_results_verify, self.deposit_contract_address)

    def test_that_wrong_deposit_address_raises_concent_validation_error(self):
        different_deposit_contract_address = '0x89915ddA14eFd6b064da953431E8b7f902d89c83'

        self.subtask_results_verify.sign_concent_promissory_note(
            self.deposit_contract_address,
            self.provider_private_key,
        )
        with pytest.raises(ConcentValidationError):
            validate_subtask_results_verify(self.subtask_results_verify, different_deposit_contract_address)


class TestSubtaskResultsRejectedValidator:
    def test_that_no_reason_raise_validation_error(self):  # pylint: disable=no-self-use
        subtask_result_rejected = SubtaskResultsRejected()
        with pytest.raises(GolemMessageValidationError):
            validate_subtask_results_rejected_reason(subtask_result_rejected)

    def test_that_message_with_verification_negative_reason_will_not_raise_exception(self):  # pylint: disable=no-self-use
        subtask_result_rejected = SubtaskResultsRejected(reason=SubtaskResultsRejected.REASON.VerificationNegative)
        validate_subtask_results_rejected_reason(subtask_result_rejected)

    def test_that_message_with_force_resources_failure_and_force_get_task_result_failed_will_not_raise_exception(self):  # pylint: disable=no-self-use
        subtask_result_rejected = SubtaskResultsRejected(reason=SubtaskResultsRejected.REASON.ForcedResourcesFailure)
        force_get_task_result_failed = ForceGetTaskResultFailed(task_to_compute=subtask_result_rejected.task_to_compute)
        subtask_result_rejected.force_get_task_result_failed = force_get_task_result_failed
        validate_subtask_results_rejected_reason(subtask_result_rejected)

    def test_that_message_with_force_resources_failure_and_without_force_get_task_result_failed_will_raise_exception(self):  # pylint: disable=no-self-use
        subtask_result_rejected = SubtaskResultsRejected(reason=SubtaskResultsRejected.REASON.ForcedResourcesFailure)
        with pytest.raises(GolemMessageValidationError):
            validate_subtask_results_rejected_reason(subtask_result_rejected)
