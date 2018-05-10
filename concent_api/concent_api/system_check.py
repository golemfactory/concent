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


def create_error_17_if_geth_container_address_has_wrong_value():
    return Error(
        "GETH_ADDRESS should be a valid url address",
        hint    = "Set correct value for GETH_ADDRESS in your local_settings.py",
        id      = "concent.E017",
    )


def create_error_18_invalid_setting_type(setting, value):
    return Error(
        f"Setting {setting} has incorrect value {value}",
        hint=f"Set correct value on setting {setting}",
        id="concent.E018",
    )


def create_error_19_if_minimum_upload_rate_is_not_set():
    return Error(
        f"MINIMUM_UPLOAD_RATE is not set",
        hint="MINIMUM_UPLOAD_RATE must be set to integer greater or equal to 1",
        id="concent.E019",
    )


def create_error_20_if_minimum_upload_rate_has_wrong_value():
    return Error(
        f"MINIMUM_UPLOAD_RATE has wrong value",
        hint="MINIMUM_UPLOAD_RATE must be set to integer greater or equal to 1",
        id="concent.E020",
    )


def create_error_21_if_download_leadin_time_is_not_set():
    return Error(
        f"DOWNLOAD_LEADIN_TIME is not set",
        hint="DOWNLOAD_LEADIN_TIME must be set to non-negative integer",
        id="concent.E021",
    )


def create_error_22_if_download_leadin_time_has_wrong_value():
    return Error(
        f"DOWNLOAD_LEADIN_TIME has wrong value",
        hint="DOWNLOAD_LEADIN_TIME must be set to non-negative integer",
        id="concent.E022",
    )


def create_error_23_if_concent_time_settings_is_not_defined(concent_setting_name):
    return Error(
        f"{concent_setting_name} is not defined",
        hint=f"{concent_setting_name} must be set to non-negative integer",
        id="concent.E023",
    )


def create_error_24_if_concent_time_settings_have_wrong_value(concent_setting_name):
    return Error(
        f"{concent_setting_name} has wrong value",
        hint=f"{concent_setting_name} must be set to non-negative integer",
        id="concent.E024",
    )


def create_error_25_atomic_requests_not_set_for_database(database_name):
    return Error(
        f"ATOMIC_REQUESTS for database {database_name} is not set to True",
        hint="ATOMIC_REQUESTS must be set to True for all databases because our views rely on the fact that on errors "
             "all database changes are rolled back",
        id="concent.E019",
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


@register
def geth_container_address_check(app_configs, **kwargs):  # pylint: disable=unused-argument
    if (
        hasattr(settings, 'PAYMENT_BACKEND') and
        settings.PAYMENT_BACKEND == 'core.payments.sci_backend'
    ):
        if hasattr(settings, 'GETH_ADDRESS'):
            url_validator = URLValidator(schemes = ['http', 'https'])
            try:
                url_validator(settings.GETH_ADDRESS)
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

            if database_config.get('ENGINE') != 'django.db.backends.dummy':
                atomic_requests = database_config.get('ATOMIC_REQUESTS', False)

                if not isinstance(atomic_requests, bool):
                    errors.append(create_error_18_invalid_setting_type(
                        f"DATABASES[{database_name}]['ATOMIC_REQUESTS']",
                        atomic_requests)
                    )

                if not atomic_requests:
                    errors.append(create_error_25_atomic_requests_not_set_for_database(database_name))
    return errors


@register()
def check_minimum_upload_rate(app_configs=None, **kwargs):  # pylint: disable=unused-argument
    errors = []
    if not hasattr(settings, 'MINIMUM_UPLOAD_RATE'):
        return [create_error_19_if_minimum_upload_rate_is_not_set()]
    if not isinstance(settings.MINIMUM_UPLOAD_RATE, int) or settings.MINIMUM_UPLOAD_RATE < 1:
        return [create_error_20_if_minimum_upload_rate_has_wrong_value()]
    return errors


@register()
def check_download_leadin_time(app_configs=None, **kwargs):  # pylint: disable=unused-argument
    errors = []
    if not hasattr(settings, 'DOWNLOAD_LEADIN_TIME'):
        return [create_error_21_if_download_leadin_time_is_not_set()]
    if not isinstance(settings.DOWNLOAD_LEADIN_TIME, int) or settings.DOWNLOAD_LEADIN_TIME < 0:
        return [create_error_22_if_download_leadin_time_has_wrong_value()]
    return errors


@register()
def check_concents_time_settings(app_configs=None, **kwargs):  # pylint: disable=unused-argument
    CONCENT_TIME_SETTINGS = [
        'CONCENT_MESSAGING_TIME',
        'FORCE_ACCEPTANCE_TIME',
        'PAYMENT_DUE_TIME',
    ]
    settings_not_defined = []
    settings_wrong_value = []
    for concent_setting in CONCENT_TIME_SETTINGS:
        if not hasattr(settings, concent_setting):
            settings_not_defined.append(create_error_23_if_concent_time_settings_is_not_defined(concent_setting))
        else:
            if not isinstance(getattr(settings, concent_setting), int) or getattr(settings, concent_setting) < 0:
                settings_wrong_value.append(create_error_24_if_concent_time_settings_have_wrong_value(concent_setting))
    return settings_not_defined + settings_wrong_value
