from django.test                    import override_settings
from django.test                    import TestCase

from golem_messages                 import message
from golem_messages.factories       import tasks
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from common.exceptions import ConcentValidationError
from common.shortcuts import load_without_public_key
from common.testing_helpers import generate_ecc_key_pair

from core.exceptions import Http400
from core.tests.utils import generate_uuid
from core.validation import validate_that_golem_messages_are_signed_with_key
from core.validation import validate_all_messages_identical

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)       = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)   = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY       = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY        = CONCENT_PUBLIC_KEY,
)
class LoadWithoutPublicKeyUnitTest(TestCase):

    def test_load_without_public_key_should_load_message(self):
        """
        Test that message loaded with load_without_public_key function will be the same as load
        with golem_messages load function.
        """

        # Create and fill some data into ComputeTaskDef
        compute_task_def = tasks.ComputeTaskDefFactory(
            task_id=generate_uuid(),
            subtask_id=generate_uuid(),
            deadline=1510912800,
        )

        # Create TaskToCompute
        task_to_compute = tasks.TaskToComputeFactory(
            compute_task_def = compute_task_def,
            price=0,
        )

        # Dump TaskToCompute to make it signed
        dumped_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        loaded_task_to_compute_with_utility_function    = load_without_public_key(
            dumped_task_to_compute,
            REQUESTOR_PUBLIC_KEY,
        )

        loaded_task_to_compute_with_golem_messages_load = load(
            dumped_task_to_compute,
            CONCENT_PRIVATE_KEY,
            REQUESTOR_PUBLIC_KEY,
        )

        self.assertEqual(loaded_task_to_compute_with_utility_function, loaded_task_to_compute_with_golem_messages_load)


class ValidateGolemMessageSignedWithKeyUnitTest(TestCase):

    def test_validate_that_golem_messages_are_signed_with_key_should_not_raise_error_if_correct_message_and_key_is_used(self):
        task_to_compute = tasks.TaskToComputeFactory()

        dumped_task_to_compute = dump(task_to_compute, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        task_to_compute = load(dumped_task_to_compute, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        assert task_to_compute.sig is not None
        assert task_to_compute.SIGN is not False

        try:
            validate_that_golem_messages_are_signed_with_key(
                CONCENT_PUBLIC_KEY,
                task_to_compute,
            )
        except Http400:
            self.fail()

    def test_validate_that_golem_messages_are_signed_with_key_should_raise_error_if_incorrect_message_and_key_is_used(self):
        task_to_compute = tasks.TaskToComputeFactory()

        dumped_task_to_compute = dump(task_to_compute, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        task_to_compute = load(dumped_task_to_compute, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        assert task_to_compute.sig is not None
        assert task_to_compute.SIGN is not False

        with self.assertRaises(Http400):
            validate_that_golem_messages_are_signed_with_key(
                REQUESTOR_PUBLIC_KEY,
                task_to_compute,
            )


class ValidateListOfIdenticalTaskToComputeUnitTest(TestCase):

    def test_that_validate_all_messages_identical_should_raise_error_when_not_list_is_used(self):

        with self.assertRaises(AssertionError):
            validate_all_messages_identical({})

        with self.assertRaises(AssertionError):
            validate_all_messages_identical(1)

        with self.assertRaises(AssertionError):
            validate_all_messages_identical('str')

        with self.assertRaises(AssertionError):
            validate_all_messages_identical(True)

    def test_that_validate_all_messages_identical_should_raise_error_when_not_all_list_items_are_instances_of_task_to_compute(self):

        with self.assertRaises(AssertionError):
            validate_all_messages_identical(
                [
                    message.TaskToCompute(),
                    message.TaskToCompute(),
                    message.Ping(),
                ]
            )

    def test_that_function_raises_assertion_error_when_list_has_0_elements(self):
        with self.assertRaises(AssertionError):
            validate_all_messages_identical([])

    def test_that_function_passes_when_list_has_1_elemt(self):
        try:
            validate_all_messages_identical([message.TaskToCompute()])
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_validate_all_messages_identical_should_raise_http400_when_not_all_task_to_compute_are_identical(self):
        list_of_not_identical_task_to_compute = [
            message.TaskToCompute(
                requestor_id = 1
            ),
            message.TaskToCompute(
                requestor_id = 2
            ),
            message.TaskToCompute(
                requestor_id = 1
            ),
        ]

        with self.assertRaises(ConcentValidationError):
            validate_all_messages_identical(
                list_of_not_identical_task_to_compute
            )

    def test_that_validate_all_messages_identical_should_not_raise_http400_when_all_task_to_compute_are_identical(self):
        list_of_identical_task_to_compute = [
            message.TaskToCompute(
                requestor_id = 1
            ),
            message.TaskToCompute(
                requestor_id = 1
            ),
            message.TaskToCompute(
                requestor_id = 1
            ),
        ]

        try:
            validate_all_messages_identical(
                list_of_identical_task_to_compute
            )
        except Http400:
            self.fail()
