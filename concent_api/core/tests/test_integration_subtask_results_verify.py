from core.tests.utils import ConcentIntegrationTestCase


class SubtaskResultsVerifyIntegrationTest(ConcentIntegrationTestCase):
    def test_that_concent_responds_with_service_refused_when_verification_for_this_subtask_done_before(self):
        self.fail("not implemented yet")

    def test_that_concent_responds_with_service_refused_when_provider_fails_verification(self):  #TODO: is TC name OK?
        self.fail("not implemented yet")

    def test_that_concent_reponds_with_service_refused_when_subtask_results_rejected_is_invalid(self):
        self.fail("not implemented yet")

    def test_that_concent_reponds_with_service_refused_when_provider_has_negative_verification(self):
        self.fail("not implemented yet")

    def test_that_concent_reponds_with_insufficient_funds_when_requestor_doesnt_have_funds(self): # TODO requestor? or provider?
        self.fail("not implemented yet")

    def test_that_concent_accepts_valid_request_and_sends_verification_order_to_work_queue(self):
        self.fail("not implemented yet")
