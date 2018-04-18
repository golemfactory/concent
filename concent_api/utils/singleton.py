from django.conf        import settings
from golem_sci.factory  import new_sci_rpc


class Concent_RPC:
    __instance = None

    def __new__(class_, *args, **kwargs):  # pylint: disable=unused-argument, bad-classmethod-argument
        if not isinstance(class_.__instance, class_):
            class_.__instance = new_sci_rpc(
                settings.GETH_CONTAINER_ADDRESS,
                settings.CONCENT_ETHEREUM_ADDRESS,
                lambda tx: tx.sign(settings.CONCENT_ETHEREUM_PRIVATE_KEY)
            )
        return class_.__instance
