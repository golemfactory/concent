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
def check_settings_storage_server_internal_address(app_configs, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'STORAGE_SERVER_INTERNAL_ADDRESS') and 'verifier' in settings.CONCENT_FEATURES:
        return [Error(
            'STORAGE_SERVER_INTERNAL_ADDRESS setting is not defined',
            hint = 'Set STORAGE_SERVER_INTERNAL_ADDRESS in your local_settings.py to the address of a Concent storage cluster that offers the /upload/ and /download/ endpoints.',
            id   = 'concent.E010',
        )]

    if hasattr(settings, 'STORAGE_SERVER_INTERNAL_ADDRESS'):
        url_validator = URLValidator(schemes = ['http', 'https'])
        try:
            url_validator(settings.STORAGE_CLUSTER_ADDRESS)
        except ValidationError as error:
            return [Error(
                'STORAGE_SERVER_INTERNAL_ADDRESS is not a valid URL',
                hint = '{}'.format(error),
                id   = 'concent.E011',
            )]

    return []


@register()
def check_settings_verifier_storage_path(app_configs, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'VERIFIER_STORAGE_PATH') and 'verifier' in settings.CONCENT_FEATURES:
        return [Error(
            'VERIFIER_STORAGE_PATH setting is not defined',
            hint = 'Set VERIFIER_STORAGE_PATH in your local_settings.py to the path to a directory where verifier can store files downloaded from the storage server, rendering results and any intermediate files.',
            id   = 'concent.E010',
        )]

    if hasattr(settings, 'VERIFIER_STORAGE_PATH'):
        if not os.path.exists(settings.VERIFIER_STORAGE_PATH):
            return [Error(
                'VERIFIER_STORAGE_PATH directory does not exists',
                hint = 'Create directory {} or change VERIFIER_STORAGE_PATH setting'.format(settings.VERIFIER_STORAGE_PATH),
                id   = 'concent.E016',
            )]
        if not os.access(settings.VERIFIER_STORAGE_PATH, os.W_OK):
            return [Error(
                'Cannot write to VERIFIER_STORAGE_PATH',
                hint = 'Current user does not have write permissions to directory {}'.format(settings.VERIFIER_STORAGE_PATH),
                id   = 'concent.E017',
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
