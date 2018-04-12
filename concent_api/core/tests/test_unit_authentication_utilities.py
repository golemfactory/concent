from django.test                    import override_settings
from django.test                    import TestCase

from golem_messages                 import message
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from core.exceptions                import Http400
from core.validation                import validate_golem_message_client_authorization
from core.validation                import validate_golem_message_signed_with_key
from core.validation                import validate_list_of_identical_task_to_compute
from utils.shortcuts                import load_without_public_key
from utils.testing_helpers          import generate_ecc_key_pair


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
        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']     = '1'
        compute_task_def['subtask_id']  = '2'
        compute_task_def['deadline']    = 1510912800

        # Create TaskToCompute
        task_to_compute = message.TaskToCompute(
            compute_task_def = compute_task_def,
            price=0,
        )

        # Dump TaskToCompute to make it signed
        dumped_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        loaded_task_to_compute_with_utility_function    = load_without_public_key(
            dumped_task_to_compute,
        )

        loaded_task_to_compute_with_golem_messages_load = load(
            dumped_task_to_compute,
            CONCENT_PRIVATE_KEY,
            REQUESTOR_PUBLIC_KEY,
        )

        self.assertEqual(loaded_task_to_compute_with_utility_function, loaded_task_to_compute_with_golem_messages_load)


class ValidateGolemMessageClientAuthorizationUnitTest(TestCase):

    def test_validate_golem_message_client_authorization_should_not_raise_error_if_correct_message_is_used(self):
        client_authorization = message.concents.ClientAuthorization(
            client_public_key = CONCENT_PUBLIC_KEY
        )

        try:
            validate_golem_message_client_authorization(client_authorization)
        except Http400:
            self.fail()

    def test_validate_golem_message_client_authorization_should_raise_400_error_when_wrong_message_is_used(self):
        ping = message.Ping()

        with self.assertRaises(Http400):
            validate_golem_message_client_authorization(ping)

    def test_validate_golem_message_client_authorization_should_raise_400_error_when_public_key_is_not_string(self):
        client_authorization = message.concents.ClientAuthorization(
            client_public_key = 111
        )

        with self.assertRaises(Http400):
            validate_golem_message_client_authorization(client_authorization)

    def test_validate_golem_message_client_authorization_should_raise_400_error_when_public_key_is_not_bytes(self):
        client_authorization = message.concents.ClientAuthorization(
            client_public_key = 'key'
        )

        with self.assertRaises(Http400):
            validate_golem_message_client_authorization(client_authorization)

    def test_validate_golem_message_client_authorization_should_raise_400_error_when_public_key_length_is_wrong(self):
        client_authorization = message.concents.ClientAuthorization(
            client_public_key = CONCENT_PUBLIC_KEY[:-1]
        )

        with self.assertRaises(Http400):
            validate_golem_message_client_authorization(client_authorization)


class ValidateGolemMessageSignedWithKeyUnitTest(TestCase):

    def test_validate_golem_message_signed_with_key_should_not_raise_error_if_correct_message_and_key_is_used(self):
        ping = message.Ping()

        dumped_ping = dump(ping, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        ping = load(dumped_ping, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        assert ping.sig is not None

        try:
            validate_golem_message_signed_with_key(
                ping,
                CONCENT_PUBLIC_KEY,
            )
        except Http400:
            self.fail()

    def test_validate_golem_message_signed_with_key_should_raise_error_if_incorrect_message_and_key_is_used(self):
        ping = message.Ping()

        dumped_ping = dump(ping, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        ping = load(dumped_ping, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        assert ping.sig is not None

        with self.assertRaises(Http400):
            validate_golem_message_signed_with_key(
                ping,
                REQUESTOR_PUBLIC_KEY,
            )


class ValidateListOfIdenticalTaskToComputeUnitTest(TestCase):

    def test_validate_list_of_identical_task_to_compute_should_raise_error_when_not_list_is_used(self):

        with self.assertRaises(AssertionError):
            validate_list_of_identical_task_to_compute({})

        with self.assertRaises(AssertionError):
            validate_list_of_identical_task_to_compute(1)

        with self.assertRaises(AssertionError):
            validate_list_of_identical_task_to_compute('str')

        with self.assertRaises(AssertionError):
            validate_list_of_identical_task_to_compute(True)

    def test_validate_list_of_identical_task_to_compute_should_raise_error_when_not_all_list_items_are_instances_of_task_to_compute(self):

        with self.assertRaises(AssertionError):
            validate_list_of_identical_task_to_compute(
                [
                    message.TaskToCompute(),
                    message.TaskToCompute(),
                    message.Ping(),
                ]
            )

    def test_validate_list_of_identical_task_to_compute_should_return_true_if_list_has_0_or_one_element(self):
        self.assertTrue(
            validate_list_of_identical_task_to_compute([])
        )

        self.assertTrue(
            validate_list_of_identical_task_to_compute(
                [
                    message.TaskToCompute(),
                ]
            )
        )

    def test_validate_list_of_identical_task_to_compute_should_raise_http400_when_not_all_task_to_compute_are_identical(self):
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

        with self.assertRaises(Http400):
            validate_list_of_identical_task_to_compute(
                list_of_not_identical_task_to_compute
            )

    def test_validate_list_of_identical_task_to_compute_should_not_raise_http400_when_all_task_to_compute_are_identical(self):
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
            validate_list_of_identical_task_to_compute(
                list_of_identical_task_to_compute
            )
        except Http400:
            self.fail()
