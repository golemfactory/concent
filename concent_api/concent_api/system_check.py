import importlib
import os

from django.core.checks     import Error
from django.core.checks     import Warning  # pylint: disable=redefined-builtin
from django.core.checks     import register
from django.conf            import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from golem_messages import constants

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
        "MINIMUM_UPLOAD_RATE is not set",
        hint="MINIMUM_UPLOAD_RATE must be set to integer greater or equal to 1",
        id="concent.E019",
    )


def create_error_20_if_minimum_upload_rate_has_wrong_value():
    return Error(
        "MINIMUM_UPLOAD_RATE has wrong value",
        hint="MINIMUM_UPLOAD_RATE must be set to integer greater or equal to 1",
        id="concent.E020",
    )


def create_error_21_if_download_leadin_time_is_not_set():
    return Error(
        "DOWNLOAD_LEADIN_TIME is not set",
        hint="DOWNLOAD_LEADIN_TIME must be set to non-negative integer",
        id="concent.E021",
    )


def create_error_22_if_download_leadin_time_has_wrong_value():
    return Error(
        "DOWNLOAD_LEADIN_TIME has wrong value",
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
        id="concent.E025",
    )


def create_error_26_storage_server_internal_address_is_not_set():
    return Error(
        'STORAGE_SERVER_INTERNAL_ADDRESS setting is not defined',
        hint='Set STORAGE_SERVER_INTERNAL_ADDRESS in your local_settings.py to the address of a Concent storage cluster that offers the /upload/ and /download/ endpoints.',
        id='concent.E026',
    )


def create_error_27_storage_server_internal_address_is_not_valid_url(error):
    return Error(
        'STORAGE_SERVER_INTERNAL_ADDRESS is not a valid URL',
        hint='{}'.format(error),
        id='concent.E027',
    )


def create_error_28_verifier_storage_path_is_not_set():
    return Error(
        'VERIFIER_STORAGE_PATH setting is not defined',
        hint='Set VERIFIER_STORAGE_PATH in your local_settings.py to the path to a directory where verifier can store files downloaded from the storage server, rendering results and any intermediate files.',
        id='concent.E028',
    )


def create_error_29_verifier_storage_path_is_does_not_exists():
    return Error(
        'VERIFIER_STORAGE_PATH directory does not exists',
        hint='Create directory {} or change VERIFIER_STORAGE_PATH setting'.format(settings.VERIFIER_STORAGE_PATH),
        id='concent.E029',
    )


def create_error_30_verifier_storage_path_is_not_accessible():
    return Error(
        'Cannot write to VERIFIER_STORAGE_PATH',
        hint='Current user does not have write permissions to directory {}'.format(settings.VERIFIER_STORAGE_PATH),
        id='concent.E030',
    )


def create_error_31_custom_protocol_times_is_not_set():
    return Error(
        'CUSTOM_PROTOCOL_TIMES setting is not set',
        hint='Set CUSTOM_PROTOCOL_TIMES in your local_settings.py to the boolean value.',
        id='concent.E031',
    )


def create_error_32_custom_protocol_times_has_wrong_value():
    return Error(
        'CUSTOM_PROTOCOL_TIMES setting has wrong value',
        hint='Set CUSTOM_PROTOCOL_TIMES in your local_settings.py to the boolean value.',
        id='concent.E032',
    )


def create_error_33_custom_protocol_times_is_false_and_settings_does_not_match_golem_messages_constants(
    concent_setting_name,
):
    return Error(
        f'CUSTOM_PROTOCOL_TIMES setting is False and Concent setting {concent_setting_name} does not match golem '
        'messages constant',
        hint='If CUSTOM_PROTOCOL_TIMES is False, Concent time settings must match golem messages constants.',
        id='concent.E033',
    )


def create_error_19_max_rendering_time_is_not_defined():
    return Error(
        'BLENDER_MAX_RENDERING_TIME setting is not defined',
        hint='Set BLENDER_MAX_RENDERING_TIME in your local_settings.py to a positive integer.',
        id='concent.E019',
    )


def create_error_20_max_rendering_time_is_not_positive_integer():
    return Error(
        'BLENDER_MAX_RENDERING_TIME is not a positive integer',
        hint='Set BLENDER_MAX_RENDERING_TIME in your local_settings.py to a positive integer.',
        id='concent.E020',
    )


def create_error_31_verifier_min_ssim_is_not_set():
    return Error(
        'VERIFIER_MIN_SSIM setting is not defined but `verifier` Concent feature is on',
        hint='Set VERIFIER_MIN_SSIM in your local settings when `verifier` Concent feature is on.',
        id='concent.E031',
    )


def create_error_32_verifier_min_ssim_is_set():
    return Error(
        'VERIFIER_MIN_SSIM setting is defined but `verifier` Concent feature is off',
        hint='Unset or set to None VERIFIER_MIN_SSIM in your local settings when `verifier` Concent feature is off.',
        id='concent.E032',
    )


def create_error_31_verifier_min_ssim_has_wrong_type():
    return Error(
        "VERIFIER_MIN_SSIM has wrong type",
        hint=f"VERIFIER_MIN_SSIM must be set to float.",
        id="concent.E033",
    )


def create_error_32_verifier_min_ssim_has_wrong_value(verifier_min_ssim):
    return Error(
        "VERIFIER_MIN_SSIM has wrong value",
        hint=f"VERIFIER_MIN_SSIM must be have value between -1 and 1. Currently it has {verifier_min_ssim}.",
        id="concent.E034",
    )


def create_error_34_additional_verification_time_multiplier_is_not_defined():
    return Error(
        "ADDITIONAL_VERIFICATION_TIME_MULTIPLIER is not defined",
        hint="Set ADDITIONAL_VERIFICATION_TIME_MULTIPLIER in your base.py to a float.",
        id="concent.E034",
    )


def create_error_35_additional_verification_time_multiplier_has_wrong_type(additional_verification_time_multiplier_type):
    return Error(
        "ADDITIONAL_VERIFICATION_TIME_MULTIPLIER has wrong type",
        hint=f"ADDITIONAL_VERIFICATION_TIME_MULTIPLIER must be float instead of {additional_verification_time_multiplier_type}.",
        id="concent.E035",
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
def check_settings_storage_server_internal_address(app_configs = None, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'STORAGE_SERVER_INTERNAL_ADDRESS') and 'verifier' in settings.CONCENT_FEATURES:
        return [create_error_26_storage_server_internal_address_is_not_set()]

    if hasattr(settings, 'STORAGE_SERVER_INTERNAL_ADDRESS'):
        url_validator = URLValidator(schemes = ['http', 'https'])
        try:
            url_validator(settings.STORAGE_SERVER_INTERNAL_ADDRESS)
        except ValidationError as error:
            return [create_error_27_storage_server_internal_address_is_not_valid_url(error)]

    return []


@register()
def check_settings_verifier_storage_path(app_configs = None, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'VERIFIER_STORAGE_PATH') and 'verifier' in settings.CONCENT_FEATURES:
        return [create_error_28_verifier_storage_path_is_not_set()]

    if hasattr(settings, 'VERIFIER_STORAGE_PATH'):
        if not os.path.exists(settings.VERIFIER_STORAGE_PATH):
            return [create_error_29_verifier_storage_path_is_does_not_exists()]
        if not os.access(settings.VERIFIER_STORAGE_PATH, os.W_OK):
            return [create_error_30_verifier_storage_path_is_not_accessible()]

    return []


@register()
def check_settings_blender_max_rendering_time(app_configs, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'BLENDER_MAX_RENDERING_TIME') and 'verifier' in settings.CONCENT_FEATURES:
        return create_error_19_max_rendering_time_is_not_defined()

    if (
        hasattr(settings, 'BLENDER_MAX_RENDERING_TIME') and (
            not isinstance(settings.BLENDER_MAX_RENDERING_TIME, int) or settings.BLENDER_MAX_RENDERING_TIME <= 0
        )
    ):
        return create_error_20_max_rendering_time_is_not_positive_integer()

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
            id   = 'concent.E019',
        )]

    try:
        importlib.import_module(settings.PAYMENT_BACKEND)
    except ImportError as error:
        return [Error(
            'PAYMENT_BACKEND settings is not a valid python module',
            hint = '{}'.format(error),
            id   = 'concent.E020',
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


@register()
def check_custom_protocol_times(app_configs=None, **kwargs):  # pylint: disable=unused-argument
    errors = []
    if not hasattr(settings, 'CUSTOM_PROTOCOL_TIMES'):
        return [create_error_31_custom_protocol_times_is_not_set()]
    if not isinstance(settings.CUSTOM_PROTOCOL_TIMES, bool):
        return [create_error_32_custom_protocol_times_has_wrong_value()]
    if settings.CUSTOM_PROTOCOL_TIMES is False:
        for concent_setting_name, is_equal in {
            'CONCENT_MESSAGING_TIME':   settings.CONCENT_MESSAGING_TIME == int(constants.CMT.total_seconds()),
            'FORCE_ACCEPTANCE_TIME':    settings.FORCE_ACCEPTANCE_TIME  == int(constants.FAT.total_seconds()),
            'PAYMENT_DUE_TIME':         settings.PAYMENT_DUE_TIME       == int(constants.PDT.total_seconds()),
            'DOWNLOAD_LEADIN_TIME':     settings.DOWNLOAD_LEADIN_TIME   == int(constants.DOWNLOAD_LEADIN_TIME.total_seconds()),
            'MINIMUM_UPLOAD_RATE':      settings.MINIMUM_UPLOAD_RATE    == constants.DEFAULT_UPLOAD_RATE,
        }.items():
            if not is_equal:
                errors.append(
                    create_error_33_custom_protocol_times_is_false_and_settings_does_not_match_golem_messages_constants(
                        concent_setting_name
                    )
                )
    return errors


@register()
def check_verifier_min_ssim(app_configs=None, **kwargs):  # pylint: disable=unused-argument
    if hasattr(settings, 'VERIFIER_MIN_SSIM') and settings.VERIFIER_MIN_SSIM is not None:
        if not isinstance(settings.VERIFIER_MIN_SSIM, float):
            return [create_error_31_verifier_min_ssim_has_wrong_type()]
        if not -1 <= settings.VERIFIER_MIN_SSIM <= 1:
            return [create_error_32_verifier_min_ssim_has_wrong_value(settings.VERIFIER_MIN_SSIM)]

    return []


@register()
def check_additional_verification_time_multiplier(app_configs=None, **kwargs):  # pylint: disable=unused-argument
    if not hasattr(settings, 'ADDITIONAL_VERIFICATION_TIME_MULTIPLIER'):
        return [create_error_34_additional_verification_time_multiplier_is_not_defined()]
    if not isinstance(settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER, float):
        return [create_error_35_additional_verification_time_multiplier_has_wrong_type(
            type(settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER)
        )]

    return []
