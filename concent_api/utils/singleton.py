from django.conf        import settings
from golem_sci.factory  import new_sci_rpc


class ConcentRPC:
    __instance = None

    def __new__(cls, *args, **kwargs):  # pylint: disable=unused-argument
        if cls.__instance is None:
            cls.__instance = new_sci_rpc(
                settings.GETH_ADDRESS,
                settings.CONCENT_ETHEREUM_ADDRESS,
                lambda tx: tx.sign(settings.CONCENT_ETHEREUM_PRIVATE_KEY)
            )
        return cls.__instance
