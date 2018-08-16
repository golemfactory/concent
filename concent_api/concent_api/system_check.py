from typing import Any
import importlib
import os

from django.core.checks     import Error
from django.core.checks     import Warning  # pylint: disable=redefined-builtin
from django.core.checks     import register
from django.conf            import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from golem_messages import constants

from common.exceptions import ConcentValidationError
from concent_api.constants import AVAILABLE_CONCENT_FEATURES
from core.constants import ETHEREUM_PUBLIC_KEY_LENGTH
from core.validation import validate_bytes_public_key


def create_error_13_ssl_cert_path_is_none() -> Error:
    return Error(
        "None is not a valid value for STORAGE_CLUSTER_SSL_CERTIFICATE_PATH",
        hint    = "If no SSL certificate should be use for storage cluster STORAGE_CLUSTER_SSL_CERTIFICATE_PATH should be an empty string",
        id      = "concent.E013",
    )


def create_error_14_cert_path_does_not_exist(path: str) -> Error:
    return Error(
        f"'{path}' does not exist",
        id = "concent.E014",
    )


def create_error_15_ssl_cert_path_is_not_a_file(path: str) -> Error:
    return Error(
        f"{path} is not a file",
        hint    = "STORAGE_CLUSTER_SSL_CERTIFICATE_PATH should be an OpenSSL certificate file",
        id      = "concent.E015",
    )


def create_error_17_if_geth_container_address_has_wrong_value() -> Error:
    return Error(
        "GETH_ADDRESS should be a valid url address",
        hint    = "Set correct value for GETH_ADDRESS in your local_settings.py",
        id      = "concent.E017",
    )


def create_error_18_invalid_setting_type(setting: str, value: str) -> Error:
    return Error(
        f"Setting {setting} has incorrect value {value}",
        hint=f"Set correct value on setting {setting}",
        id="concent.E018",
    )


def create_error_19_if_minimum_upload_rate_is_not_set() -> Error:
    return Error(
        "MINIMUM_UPLOAD_RATE is not set",
        hint="MINIMUM_UPLOAD_RATE must be set to integer greater or equal to 1",
        id="concent.E019",
    )


def create_error_20_if_minimum_upload_rate_has_wrong_value() -> Error:
    return Error(
        "MINIMUM_UPLOAD_RATE has wrong value",
        hint="MINIMUM_UPLOAD_RATE must be set to integer greater or equal to 1",
        id="concent.E020",
    )


def create_error_21_if_download_leadin_time_is_not_set() -> Error:
    return Error(
        "DOWNLOAD_LEADIN_TIME is not set",
        hint="DOWNLOAD_LEADIN_TIME must be set to non-negative integer",
        id="concent.E021",
    )


def create_error_22_if_download_leadin_time_has_wrong_value() -> Error:
    return Error(
        "DOWNLOAD_LEADIN_TIME has wrong value",
        hint="DOWNLOAD_LEADIN_TIME must be set to non-negative integer",
        id="concent.E022",
    )


def create_error_23_if_concent_time_settings_is_not_defined(concent_setting_name: str) -> Error:
    return Error(
        f"{concent_setting_name} is not defined",
        hint=f"{concent_setting_name} must be set to non-negative integer",
        id="concent.E023",
    )


def create_error_24_if_concent_time_settings_have_wrong_value(concent_setting_name: str) -> Error:
    return Error(
        f"{concent_setting_name} has wrong value",
        hint=f"{concent_setting_name} must be set to non-negative integer",
        id="concent.E024",
    )


def create_error_25_atomic_requests_not_set_for_database(database_name: str) -> Error:
    return Error(
        f"ATOMIC_REQUESTS for database {database_name} is not set to True",
        hint="ATOMIC_REQUESTS must be set to True for all databases because our views rely on the fact that on errors "
             "all database changes are rolled back",
        id="concent.E025",
    )


def create_error_26_storage_server_internal_address_is_not_set() -> Error:
    return Error(
        'STORAGE_SERVER_INTERNAL_ADDRESS setting is not defined',
        hint='Set STORAGE_SERVER_INTERNAL_ADDRESS in your local_settings.py to the address of a Concent storage cluster that offers the /upload/ and /download/ endpoints.',
        id='concent.E026',
    )


def create_error_27_storage_server_internal_address_is_not_valid_url(error: str) -> Error:
    return Error(
        'STORAGE_SERVER_INTERNAL_ADDRESS is not a valid URL',
        hint='{}'.format(error),
        id='concent.E027',
    )


def create_error_28_verifier_storage_path_is_not_set() -> Error:
    return Error(
        'VERIFIER_STORAGE_PATH setting is not defined',
        hint='Set VERIFIER_STORAGE_PATH in your local_settings.py to the path to a directory where verifier can store files downloaded from the storage server, rendering results and any intermediate files.',
        id='concent.E028',
    )


def create_error_29_verifier_storage_path_is_does_not_exists() -> Error:
    return Error(
        'VERIFIER_STORAGE_PATH directory does not exists',
        hint='Create directory {} or change VERIFIER_STORAGE_PATH setting'.format(settings.VERIFIER_STORAGE_PATH),
        id='concent.E029',
    )


def create_error_30_verifier_storage_path_is_not_accessible() -> Error:
    return Error(
        'Cannot write to VERIFIER_STORAGE_PATH',
        hint='Current user does not have write permissions to directory {}'.format(settings.VERIFIER_STORAGE_PATH),
        id='concent.E030',
    )


def create_error_31_custom_protocol_times_is_not_set() -> Error:
    return Error(
        'CUSTOM_PROTOCOL_TIMES setting is not set',
        hint='Set CUSTOM_PROTOCOL_TIMES in your local_settings.py to the boolean value.',
        id='concent.E031',
    )


def create_error_32_custom_protocol_times_has_wrong_value() -> Error:
    return Error(
        'CUSTOM_PROTOCOL_TIMES setting has wrong value',
        hint='Set CUSTOM_PROTOCOL_TIMES in your local_settings.py to the boolean value.',
        id='concent.E032',
    )


def create_error_33_custom_protocol_times_is_false_and_settings_does_not_match_golem_messages_constants(
    concent_setting_name: str,
) -> Error:
    return Error(
        f'CUSTOM_PROTOCOL_TIMES setting is False and Concent setting {concent_setting_name} does not match golem '
        'messages constant',
        hint='If CUSTOM_PROTOCOL_TIMES is False, Concent time settings must match golem messages constants.',
        id='concent.E033',
    )


def create_error_31_verifier_min_ssim_is_not_set() -> Error:
    return Error(
        'VERIFIER_MIN_SSIM setting is not defined but `verifier` Concent feature is on',
        hint='Set VERIFIER_MIN_SSIM in your local settings when `verifier` Concent feature is on.',
        id='concent.E031',
    )


def create_error_32_verifier_min_ssim_is_set() -> Error:
    return Error(
        'VERIFIER_MIN_SSIM setting is defined but `verifier` Concent feature is off',
        hint='Unset or set to None VERIFIER_MIN_SSIM in your local settings when `verifier` Concent feature is off.',
        id='concent.E032',
    )


def create_error_31_verifier_min_ssim_has_wrong_type() -> Error:
    return Error(
        "VERIFIER_MIN_SSIM has wrong type",
        hint=f"VERIFIER_MIN_SSIM must be set to float.",
        id="concent.E033",
    )


def create_error_32_verifier_min_ssim_has_wrong_value(verifier_min_ssim: float) -> Error:
    return Error(
        "VERIFIER_MIN_SSIM has wrong value",
        hint=f"VERIFIER_MIN_SSIM must be have value between -1 and 1. Currently it has {verifier_min_ssim}.",
        id="concent.E034",
    )


def create_error_34_additional_verification_time_multiplier_is_not_defined() -> Error:
    return Error(
        "ADDITIONAL_VERIFICATION_TIME_MULTIPLIER is not defined",
        hint="Set ADDITIONAL_VERIFICATION_TIME_MULTIPLIER in your base.py to a float.",
        id="concent.E034",
    )


def create_error_35_additional_verification_time_multiplier_has_wrong_type(
    additional_verification_time_multiplier_type: Any
) -> Error:
    return Error(
        "ADDITIONAL_VERIFICATION_TIME_MULTIPLIER has wrong type",
        hint=f"ADDITIONAL_VERIFICATION_TIME_MULTIPLIER must be float instead of {additional_verification_time_multiplier_type}.",
        id="concent.E035",
    )


def create_error_36_storage_cluster_address_does_not_end_with_slash() -> Error:
    return Error(
        "STORAGE_CLUSTER_ADDRESS must end with '/'",
        hint=f"STORAGE_CLUSTER_ADDRESS must end with '/'.",
        id="concent.E036",
    )


def create_error_37_storage_server_internal_address_does_not_end_with_slash() -> Error:
    return Error(
        "STORAGE_SERVER_INTERNAL_ADDRESS must end with '/'",
        hint=f"STORAGE_SERVER_INTERNAL_ADDRESS must end with '/'.",
        id="concent.E037",
    )


def create_error_38_storage_cluster_address_is_not_valid_url(error: str) -> Error:
    return Error(
        'STORAGE_CLUSTER_ADDRESS is not a valid URL',
        hint=f'{error}',
        id='concent.E038',
    )


def create_error_39_storage_server_internal_address_is_not_set() -> Error:
    return Error(
        'STORAGE_CLUSTER_ADDRESS setting is not defined',
        hint='Set STORAGE_CLUSTER_ADDRESS in your local_settings.py to the address of a Concent storage cluster that offers the /upload/ and /download/ endpoints.',
        id='concent.E039',
    )


def create_error_40_verifier_download_chunk_size_is_not_defined() -> Error:
    return Error(
        'VERIFIER_DOWNLOAD_CHUNK_SIZE setting is not defined',
        hint='Set VERIFIER_DOWNLOAD_CHUNK_SIZE in your local_settings.py.',
        id='concent.E040',
    )


def create_error_41_verifier_download_chunk_size_has_wrong_type(verifier_download_chunk_size_type: Any) -> Error:
    return Error(
        'VERIFIER_DOWNLOAD_CHUNK_SIZE has wrong type',
        hint=f"VERIFIER_DOWNLOAD_CHUNK_SIZE must be integer instead of {verifier_download_chunk_size_type}.",
        id='concent.E041',
    )


def create_error_42_verifier_download_chunk_size_has_wrong_value(verifier_download_chunk_size_value: int) -> Error:
    return Error(
        'VERIFIER_DOWNLOAD_CHUNK_SIZE setting has wrong value',
        hint=f"VERIFIER_DOWNLOAD_CHUNK_SIZE must be greater or equal than 1. Currently it has {verifier_download_chunk_size_value}.",
        id='concent.E042',
    )


def create_error_43_signing_service_public_key_is_missing() -> Error:
    return Error(
        'SIGNING_SERVICE_PUBLIC_KEY is not defined',
        hint='SIGNING_SERVICE_PUBLIC_KEY should be defined in settings if "middleman" feature is enabled.',
        id='concent.E043',
    )


def create_error_44_signing_service_public_key_is_invalid() -> Error:
    return Error(
        'SIGNING_SERVICE_PUBLIC_KEY is not valid',
        hint='SIGNING_SERVICE_PUBLIC_KEY should be a valid public key.',
        id='concent.E044',
    )


def create_error_45_concent_ethereum_public_key_is_not_set() -> Error:
    return Error(
        'CONCENT_ETHEREUM_PUBLIC_KEY setting is not defined',
        hint='Set CONCENT_ETHEREUM_PUBLIC_KEY in your local_settings.py to the one matching SigningService Ethereum private key.',
        id='concent.E045',
    )


def create_error_46_concent_ethereum_public_key_has_wrong_type(concent_ethereum_public_key: Any) -> Error:
    return Error(
        'CONCENT_ETHEREUM_PUBLIC_KEY has wrong type',
        hint=f"CONCENT_ETHEREUM_PUBLIC_KEY must be string instead of {type(concent_ethereum_public_key)}.",
        id='concent.E046',
    )


def create_error_47_concent_ethereum_public_key_has_wrong_length(concent_ethereum_public_key: str) -> Error:
    return Error(
        'CONCENT_ETHEREUM_PUBLIC_KEY has wrong length',
        hint=f"CONCENT_ETHEREUM_PUBLIC_KEY must have length {ETHEREUM_PUBLIC_KEY_LENGTH} instead of {len(concent_ethereum_public_key)}.",
        id='concent.E047',
    )


def create_error_48_middleman_address_has_wrong_type(value: Any) -> Error:
    return Error(
        f"Setting MIDDLEMAN_ADDRESS has incorrect type `{type(value)}` instead of `str`.",
        hint=f"Set setting MIDDLEMAN_ADDRESS to be a string.",
        id="concent.E048",
    )


def create_error_49_middleman_address_is_not_set() -> Error:
    return Error(
        'MIDDLEMAN_ADDRESS setting is not defined.',
        hint='Set MIDDLEMAN_ADDRESS to host which MiddleMan instance is working on.',
        id='concent.E049',
    )


def create_error_50_middleman_port_is_not_set() -> Error:
    return Error(
        'MIDDLEMAN_PORT setting is not defined',
        hint='Set MIDDLEMAN_PORT to port on which MiddleMan instance is accepting connections.',
        id='concent.E050',
    )


def create_error_51_middleman_port_has_wrong_type(value: Any) -> Error:
    return Error(
        f"Setting MIDDLEMAN_PORT has incorrect type `{type(value)}` instead of `int`.",
        hint=f"Set setting MIDDLEMAN_PORT to be an integer.",
        id="concent.E051",
    )


def create_error_52_middleman_port_has_wrong_value(value: int) -> Error:
    return Error(
        f"Setting MIDDLEMAN_PORT has incorrect value `{value}`.",
        hint="Set setting MIDDLEMAN_PORT to be integer value between 0 and 65535 (exclusive).",
        id="concent.E052",
    )


def create_error_53_use_signing_service_not_set() -> Error:
    return Error(
        'USE_SIGNING_SERVICE setting is not defined',
        hint='Set USE_SIGNING_SERVICE to True if you want to use SigningService, otherwise to False.',
        id='concent.E053',
    )


def create_error_54_use_signing_service_has_wrong_type(value: Any) -> Error:
    return Error(
        f"Setting USE_SIGNING_SERVICE has incorrect type `{type(value)}` instead of `bool`.",
        hint=f"Set setting USE_SIGNING_SERVICE to be a boolean.",
        id="concent.E054",
    )


def create_error_55_use_signing_service_is_true_but_middleman_is_missing() -> Error:
    return Error(
        'USE_SIGNING_SERVICE is set to True but MiddleMan is not available.',
        hint='Add `middleman` to CONCENT_FEATURES.',
        id='concent.E055',
    )


@register()
def check_settings_concent_features(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument

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
        if not set(AVAILABLE_CONCENT_FEATURES[feature]['required_django_apps']).issubset(set(settings.INSTALLED_APPS)):  # type: ignore
            errors_and_warnings.append(Error(
                'Not all apps required by feature "{}" are enabled in INSTALLED_APPS'.format(feature),
                hint = 'Add the following apps to INSTALLED_APPS: {}'.format(AVAILABLE_CONCENT_FEATURES[feature]['required_django_apps']),  # type: ignore
                id   = 'concent.E003',
            ))

    return errors_and_warnings


@register()
def check_settings_storage_cluster_address(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if not hasattr(settings, 'STORAGE_CLUSTER_ADDRESS') and 'gatekeeper' in settings.CONCENT_FEATURES:
        return [create_error_39_storage_server_internal_address_is_not_set()]

    if hasattr(settings, 'STORAGE_CLUSTER_ADDRESS'):
        url_validator = URLValidator(schemes=['http', 'https'])
        try:
            url_validator(settings.STORAGE_CLUSTER_ADDRESS)
        except ValidationError as error:
            return [create_error_38_storage_cluster_address_is_not_valid_url(error)]
        if not settings.STORAGE_CLUSTER_ADDRESS.endswith('/'):
            return [create_error_36_storage_cluster_address_does_not_end_with_slash()]

    return []


@register()
def check_settings_storage_server_internal_address(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if not hasattr(settings, 'STORAGE_SERVER_INTERNAL_ADDRESS') and 'verifier' in settings.CONCENT_FEATURES:
        return [create_error_26_storage_server_internal_address_is_not_set()]

    if hasattr(settings, 'STORAGE_SERVER_INTERNAL_ADDRESS'):
        url_validator = URLValidator(schemes=['http', 'https'])
        try:
            url_validator(settings.STORAGE_SERVER_INTERNAL_ADDRESS)
        except ValidationError as error:
            return [create_error_27_storage_server_internal_address_is_not_valid_url(error)]
        if not settings.STORAGE_SERVER_INTERNAL_ADDRESS.endswith('/'):
            return [create_error_37_storage_server_internal_address_does_not_end_with_slash()]

    return []


@register()
def check_settings_verifier_storage_path(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if not hasattr(settings, 'VERIFIER_STORAGE_PATH') and 'verifier' in settings.CONCENT_FEATURES:
        return [create_error_28_verifier_storage_path_is_not_set()]

    if hasattr(settings, 'VERIFIER_STORAGE_PATH'):
        if not os.path.exists(settings.VERIFIER_STORAGE_PATH):
            return [create_error_29_verifier_storage_path_is_does_not_exists()]
        if not os.access(settings.VERIFIER_STORAGE_PATH, os.W_OK):
            return [create_error_30_verifier_storage_path_is_not_accessible()]

    return []


@register()
def check_payment_backend(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
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
def storage_cluster_certificate_path_check(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
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
def geth_container_address_check(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if (
        hasattr(settings, 'PAYMENT_BACKEND') and
        settings.PAYMENT_BACKEND == 'core.payments.backends.sci_backend'
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
def check_atomic_requests(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
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
def check_minimum_upload_rate(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    errors: list = []
    if not hasattr(settings, 'MINIMUM_UPLOAD_RATE'):
        return [create_error_19_if_minimum_upload_rate_is_not_set()]
    if not isinstance(settings.MINIMUM_UPLOAD_RATE, int) or settings.MINIMUM_UPLOAD_RATE < 1:
        return [create_error_20_if_minimum_upload_rate_has_wrong_value()]
    return errors


@register()
def check_download_leadin_time(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    errors: list = []
    if not hasattr(settings, 'DOWNLOAD_LEADIN_TIME'):
        return [create_error_21_if_download_leadin_time_is_not_set()]
    if not isinstance(settings.DOWNLOAD_LEADIN_TIME, int) or settings.DOWNLOAD_LEADIN_TIME < 0:
        return [create_error_22_if_download_leadin_time_has_wrong_value()]
    return errors


@register()
def check_concents_time_settings(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
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
def check_custom_protocol_times(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
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
def check_verifier_min_ssim(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if hasattr(settings, 'VERIFIER_MIN_SSIM') and settings.VERIFIER_MIN_SSIM is not None:
        if not isinstance(settings.VERIFIER_MIN_SSIM, float):
            return [create_error_31_verifier_min_ssim_has_wrong_type()]
        if not -1 <= settings.VERIFIER_MIN_SSIM <= 1:
            return [create_error_32_verifier_min_ssim_has_wrong_value(settings.VERIFIER_MIN_SSIM)]

    return []


@register()
def check_additional_verification_time_multiplier(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if not hasattr(settings, 'ADDITIONAL_VERIFICATION_TIME_MULTIPLIER'):
        return [create_error_34_additional_verification_time_multiplier_is_not_defined()]
    if not isinstance(settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER, float):
        return [create_error_35_additional_verification_time_multiplier_has_wrong_type(
            type(settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER)
        )]

    return []


@register()
def check_verifier_download_chunk_size(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if 'verifier' in settings.CONCENT_FEATURES:
        if not hasattr(settings, 'VERIFIER_DOWNLOAD_CHUNK_SIZE'):
            return [create_error_40_verifier_download_chunk_size_is_not_defined()]
        if not isinstance(settings.VERIFIER_DOWNLOAD_CHUNK_SIZE, int):
            return [create_error_41_verifier_download_chunk_size_has_wrong_type(
                type(settings.VERIFIER_DOWNLOAD_CHUNK_SIZE)
            )]
        if settings.VERIFIER_DOWNLOAD_CHUNK_SIZE < 1:
            return [create_error_42_verifier_download_chunk_size_has_wrong_value(
                settings.VERIFIER_DOWNLOAD_CHUNK_SIZE
            )]

    return []


@register()
def check_signing_service_key_availability_for_middleman(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    errors = []
    if "middleman" in settings.CONCENT_FEATURES:
        if not hasattr(settings, "SIGNING_SERVICE_PUBLIC_KEY"):
            errors.append(create_error_43_signing_service_public_key_is_missing())
        else:
            try:
                validate_bytes_public_key(settings.SIGNING_SERVICE_PUBLIC_KEY, "SIGNING_SERVICE_PUBLIC_KEY")
            except ConcentValidationError:
                errors.append(create_error_44_signing_service_public_key_is_invalid())
    return errors


@register()
def check_concent_ethereum_public_key(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if not hasattr(settings, 'CONCENT_ETHEREUM_PUBLIC_KEY') and 'core' in settings.CONCENT_FEATURES:
        return [create_error_45_concent_ethereum_public_key_is_not_set()]

    if hasattr(settings, 'CONCENT_ETHEREUM_PUBLIC_KEY'):
        if not isinstance(settings.CONCENT_ETHEREUM_PUBLIC_KEY, str):
            return [create_error_46_concent_ethereum_public_key_has_wrong_type(settings.CONCENT_ETHEREUM_PUBLIC_KEY)]
        if len(settings.CONCENT_ETHEREUM_PUBLIC_KEY) != ETHEREUM_PUBLIC_KEY_LENGTH:
            return [create_error_47_concent_ethereum_public_key_has_wrong_length(settings.CONCENT_ETHEREUM_PUBLIC_KEY)]

    return []


@register()
def check_middleman_address(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if 'middleman' in settings.CONCENT_FEATURES:
        if not hasattr(settings, 'MIDDLEMAN_ADDRESS'):
            return [create_error_49_middleman_address_is_not_set()]
        if not isinstance(settings.MIDDLEMAN_ADDRESS, str):
            return [create_error_48_middleman_address_has_wrong_type(settings.MIDDLEMAN_ADDRESS)]

    return []


@register()
def check_middleman_port(app_configs: None=None, **kwargs: Any) -> list:  # pylint: disable=unused-argument
    if 'middleman' in settings.CONCENT_FEATURES:
        if not hasattr(settings, 'MIDDLEMAN_PORT'):
            return [create_error_50_middleman_port_is_not_set()]
        if not isinstance(settings.MIDDLEMAN_PORT, int):
            return [create_error_51_middleman_port_has_wrong_type(settings.MIDDLEMAN_PORT)]
        if not 0 < settings.MIDDLEMAN_PORT < 65535:
            return [create_error_52_middleman_port_has_wrong_value(settings.MIDDLEMAN_PORT)]

    return []
