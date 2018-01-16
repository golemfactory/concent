from django.core.checks     import Error
from django.core.checks     import Warning  # pylint: disable=redefined-builtin
from django.core.checks     import register
from django.conf            import settings

from concent_api.constants  import AVAILABLE_CONCENT_FEATURES


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
