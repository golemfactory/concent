import importlib
import os

from django.core.checks     import Error
from django.core.checks     import Warning  # pylint: disable=redefined-builtin
from django.core.checks     import register
from django.conf            import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from concent_api.constants  import AVAILABLE_CONCENT_FEATURES


def create_error_13_ssl_cert_path_is_none():
    return Error(
        "None is not a valid value for STORAGE_CLUSTER_SSL_CERTIFICATE_PATH",
        hint    = "If no SSL certificate should be use for storage cluster STORAGE_CLUSTER_SSL_CERTIFICATE_PATH should be an empty string",
        id      = "concent.E013",
    )


def create_error_14_cert_path_does_not_exist(path):
    return Error(
        f"'{path}' does not exist",
        id = "concent.E014",
    )


def create_error_15_ssl_cert_path_is_not_a_file(path):
    return Error(
        f"{path} is not a file",
        hint    = "STORAGE_CLUSTER_SSL_CERTIFICATE_PATH should be an OpenSSL certificate file",
        id      = "concent.E015",
    )


def create_error_15_if_new_chain_segment_time_not_integer():
    return Error(
        "CREATION_NEW_CHAIN_SEGMENT_TIME should be integer",
        hint    = "Set correct value for CREATION_NEW_CHAIN_SEGMENT_TIME in your local_settings.py",
        id      = "concent.E015",
    )


def create_error_16_if_new_chain_segment_time_is_not_bigger_than_0():
    return Error(
        "CREATION_NEW_CHAIN_SEGMENT_TIME should be bigger than 0",
        hint    = "Set correct value for CREATION_NEW_CHAIN_SEGMENT_TIME in your local_settings.py",
        id      = "concent.E016",
    )


def create_error_17_if_geth_container_address_has_wrong_value():
    return Error(
        "GETH_CONTAINER_ADDRESS should be a valid url address",
        hint    = "Set correct value for GETH_CONTAINER_ADDRESS in your local_settings.py",
        id      = "concent.E017",
    )


def create_error_18_atomic_requests_not_set_for_database(database_name):
    return Error(
        f"ATOMIC_REQUESTS for database {database_name} is not set to True",
        hint="ATOMIC_REQUESTS must be set to True for all databases because our views rely on the fact that on errors "
             "all database changes are rolled back",
        id="concent.E018",
    )


@register()
def check_settings_concent_features(app_configs, **kwargs):  # pylint: disable=unused-argument

    if not isinstance(settings.CONCENT_FEATURES, list):
        return [Error(
            'The value of CONCENT_FEATURES setting is not a list',
            id = 'concent.E001',
        )]

    uknown_features = set(settings.CONCENT_FEATURES) - AVAILABLE_CONCENT_FEATURES.keys()
    if len(uknown_features) > 0:
        return [Error(
            'Unknown features specified CONCENT_FEATURES setting',
            hint = 'Did you make a typo in the name?',
            id   = 'concent.E002',
        )]

    errors_and_warnings = []
    if len(set(settings.CONCENT_FEATURES)) != len(settings.CONCENT_FEATURES):
        errors_and_warnings.append(Warning(
            'Some features appear multiple times in CONCENT_FEATURES setting',
            hint = 'Remove the duplicate names.',
            id   = 'concent.W001',
        ))

    for feature in settings.CONCENT_FEATURES:
        if not set(AVAILABLE_CONCENT_FEATURES[feature]['required_django_apps']).issubset(set(settings.INSTALLED_APPS)):
            errors_and_warnings.append(Error(
                'Not all apps required by feature "{}" are enabled in INSTALLED_APPS'.format(feature),
                hint = 'Add the following apps to INSTALLED_APPS: {}'.format(AVAILABLE_CONCENT_FEATURES[feature]['required_django_apps']),
                id   = 'concent.E003',
            ))

    return errors_and_warnings


@register()
def check_settings_storage_cluster_address(app_configs, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'STORAGE_CLUSTER_ADDRESS') and 'gatekeeper' in settings.CONCENT_FEATURES:
        return [Error(
            'STORAGE_CLUSTER_ADDRESS setting is not defined',
            hint = 'Set STORAGE_CLUSTER_ADDRESS in your local_settings.py to the address of a Concent storage cluster that offers the /upload/ and /download/ endpoints.',
            id   = 'concent.E010',
        )]

    if hasattr(settings, 'STORAGE_CLUSTER_ADDRESS'):
        url_validator = URLValidator(schemes = ['http', 'https'])
        try:
            url_validator(settings.STORAGE_CLUSTER_ADDRESS)
        except ValidationError as error:
            return [Error(
                'STORAGE_CLUSTER_ADDRESS is not a valid URL',
                hint = '{}'.format(error),
                id   = 'concent.E011',
            )]

    return []


@register()
def check_payment_backend(app_configs, **kwargs):  # pylint: disable=unused-argument
    if 'concent-api' in settings.CONCENT_FEATURES and (
        not hasattr(settings, 'PAYMENT_BACKEND') or
        settings.PAYMENT_BACKEND in [None, '']
    ):
        return [Error(
            'PAYMENT_BACKEND setting is not defined',
            hint = 'Set PAYMENT_BACKEND in your local_settings.py to the python module realizing payment API.',
            id   = 'concent.E012',
        )]

    try:
        importlib.import_module(settings.PAYMENT_BACKEND)
    except ImportError as error:
        return [Error(
            'PAYMENT_BACKEND settings is not a valid python module',
            hint = '{}'.format(error),
            id   = 'concent.E011',
        )]

    return []


@register()
def storage_cluster_certificate_path_check(app_configs = None, **kwargs):  # pylint: disable=unused-argument
    errors = []
    certificate_path = settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH
    if certificate_path != '':
        if certificate_path is None:
            errors.append(create_error_13_ssl_cert_path_is_none())
        elif not os.path.exists(certificate_path):
            errors.append(create_error_14_cert_path_does_not_exist(certificate_path))
        elif not os.path.isfile(certificate_path):
            errors.append(create_error_15_ssl_cert_path_is_not_a_file(certificate_path))
    return errors


@register()
def creation_new_chain_segment_time_check(app_configs, **kwargs):  # pylint: disable=unused-argument
    errors = []
    if (
        hasattr(settings, 'PAYMENT_BACKEND') and
        settings.PAYMENT_BACKEND == 'core.payments.sci_backend'
    ):
        if (
            hasattr(settings, 'CREATION_NEW_CHAIN_SEGMENT_TIME')
        ):
            creation_new_chain_segment_time = settings.CREATION_NEW_CHAIN_SEGMENT_TIME
            if not isinstance(creation_new_chain_segment_time, int):
                errors.append(create_error_15_if_new_chain_segment_time_not_integer())
            elif not creation_new_chain_segment_time > 0:
                errors.append(create_error_16_if_new_chain_segment_time_is_not_bigger_than_0())
    return errors


@register
def geth_container_address_check(app_configs, **kwargs):  # pylint: disable=unused-argument
    if (
        hasattr(settings, 'PAYMENT_BACKEND') and
        settings.PAYMENT_BACKEND == 'core.payments.sci_backend'
    ):
        if hasattr(settings, 'GETH_CONTAINER_ADDRESS'):
            url_validator = URLValidator(schemes = ['http', 'https'])
            try:
                url_validator(settings.GETH_CONTAINER_ADDRESS)
            except ValidationError:
                return [create_error_17_if_geth_container_address_has_wrong_value()]
        else:
            return [create_error_17_if_geth_container_address_has_wrong_value()]
    return []


@register
def check_atomic_requests(app_configs = None, **kwargs):  # pylint: disable=unused-argument
    errors = []
    if hasattr(settings, 'DATABASES') and isinstance(settings.DATABASES, dict):
        for database_name, database_config in settings.DATABASES.items():
            if 'ATOMIC_REQUESTS' not in database_config or database_config['ATOMIC_REQUESTS'] is not True:
                errors.append(create_error_18_atomic_requests_not_set_for_database(database_name))
    return errors
