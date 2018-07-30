import random

from ethereum.utils import denoms
from golem_messages.factories.helpers import MessageFactory
import factory.fuzzy

from concent_golem_messages.message import NonceAbstractMessage
from concent_golem_messages.message import SignedTransaction
from concent_golem_messages.message import TransactionRejected
from concent_golem_messages.message import TransactionSigningRequest


class NonceAbstractMessageFactory(MessageFactory):
    class Meta:
        model = NonceAbstractMessage

    nonce = factory.LazyFunction(
        lambda: random.randint(0, denoms.turing)
    )


class TransactionAbstractMessage(NonceAbstractMessageFactory):
    class Meta:
        model = NonceAbstractMessage

    gasprice = factory.LazyFunction(
        lambda: random.randint(0, denoms.turing)
    )
    startgas = factory.LazyFunction(
        lambda: random.randint(0, denoms.turing)
    )
    to = factory.fuzzy.FuzzyText(length=20, chars='0123456789abcdef')
    value = factory.LazyFunction(
        lambda: random.randint(0, denoms.turing)
    )
    data = b''


class TransactionSigningRequestFactory(TransactionAbstractMessage):
    class Meta:
        model = TransactionSigningRequest

    # pylint: disable=no-self-argument

    @factory.post_generation
    def arct_report_computed_task(msg, _create, _extracted, **kwargs):  # pylint: disable=unused-argument
        setattr(msg, 'from', factory.fuzzy.FuzzyText(length=20, chars='0123456789abcdef').fuzz())

        # pylint: enable=no-self-argument


class SignedTransactionFactory(TransactionAbstractMessage):
    class Meta:
        model = SignedTransaction

    v = factory.fuzzy.FuzzyChoice(choices=[28, 29])
    r = factory.LazyFunction(
        lambda: random.randint(0, denoms.turing)
    )
    s = factory.LazyFunction(
        lambda: random.randint(0, denoms.turing)
    )


class TransactionRejectedFactory(NonceAbstractMessageFactory):
    class Meta:
        model = TransactionRejected

    reason = factory.fuzzy.FuzzyChoice(TransactionRejected.REASON)
