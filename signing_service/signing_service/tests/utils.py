import datetime

from freezegun import freeze_time
from golem_messages import dump
from mypy.types import Union

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest
from middleman_protocol.concent_golem_messages.message import TransactionRejected


def get_timestamp_string() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SigningServiceIntegrationTestCase:

    def _get_deserialized_transaction_signing_request(  # pylint: disable=no-self-use
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
        nonce: int= None,
    ) -> TransactionSigningRequest:
        with freeze_time(timestamp or get_timestamp_string()):
            transaction_signing_request = TransactionSigningRequest(
                nonce=nonce if nonce is not None else 1,
                gasprice=10 ** 6,
                startgas=80000,
                to=b'7917bc33eea648809c28',
                value=10,
                data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
                from_address=b'7917bc33eea648809c29',
            )
            return transaction_signing_request

    def _get_serialized_transaction_signing_request(
        self,
        signed_transaction: SignedTransaction,
        concent_private_key: bytes,
        public_key: bytes,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> bytes:
        return dump(
            msg=(signed_transaction if signed_transaction is not None
                 else self._get_deserialized_transaction_signing_request(timestamp)),
            privkey=concent_private_key,
            pubkey=public_key,
        )

    def _get_deserialized_signed_transaction(  # pylint: disable=no-self-use
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> SignedTransaction:
        with freeze_time(timestamp or get_timestamp_string()):
            return SignedTransaction(
                nonce=1,
                gasprice=10 ** 6,
                startgas=80000,
                to=b'7917bc33eea648809c28',
                value=10,
                data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
                v=28,
                r=105276041803796697890139158600495981346175539693000174052040367753737207356915,
                s=51455402244652678469360859593599492752947853083356495769067973718806366068077,
            )

    def _get_serialized_signed_transaction(
        self,
        transaction_signing_request: TransactionSigningRequest,
        concent_private_key: bytes,
        public_key: bytes,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> bytes:
        return dump(
            msg=(transaction_signing_request if transaction_signing_request is not None
                 else self._get_deserialized_transaction_signing_request(timestamp)),
            privkey=concent_private_key,
            pubkey=public_key,
        )

    def _get_deserialized_transaction_rejected(  # pylint: disable=no-self-use
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> TransactionRejected:
        with freeze_time(timestamp or get_timestamp_string()):
            return TransactionRejected(
                reason=TransactionRejected.REASON.InvalidTransaction
            )

    def _get_serialized_transaction_rejected(
        self,
        transaction_rejected: TransactionRejected,
        concent_private_key: bytes,
        public_key: bytes,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> bytes:
        return dump(
            msg=(transaction_rejected if transaction_rejected is not None
                 else self._get_deserialized_transaction_signing_request(timestamp)),
            privkey=concent_private_key,
            pubkey=public_key,
        )
