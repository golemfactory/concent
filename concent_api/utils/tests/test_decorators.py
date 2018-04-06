from base64                         import b64encode
import json
import mock

from django.conf                    import settings
from django.http.response           import HttpResponse
from django.shortcuts               import reverse
from django.test                    import override_settings
from django.test                    import RequestFactory
from core.tests.utils               import ConcentIntegrationTestCase
from django.test                    import TransactionTestCase
from django.views.decorators.http   import require_POST
from golem_messages                 import dump
from golem_messages                 import load
from golem_messages                 import message

from core.exceptions                import Http400
from core.models                    import Client
from utils.api_view                 import api_view
from utils.helpers                  import get_current_utc_timestamp
from utils.testing_helpers          import generate_ecc_key_pair


# (CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()

# @override_settings(
#     CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
#     CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
# )
# class DecoratorsTestCase(ConcentIntegrationTestCase):
