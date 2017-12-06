from django.core.checks     import Error
from django.core.checks     import Warning  # pylint: disable=redefined-builtin
from django.core.checks     import register
from django.conf            import settings


@register()
def check_settings_concent_features(app_configs, **kwargs):  # pylint: disable=unused-argument

    if not isinstance(settings.CONCENT_FEATURES, list):
        return [Error('The value of CONCENT_FEATURES setting is not a list', id = 'concent.E001')]

    uknown_features = set(settings.CONCENT_FEATURES) - {"concent-api", "gatekeeper", "admin-panel"}
    if len(uknown_features) > 0:
        return [Error('Unknown features specified CONCENT_FEATURES setting',               hint = 'Did you make a typo in the name?', id = 'concent.E002')]

    if len(set(settings.CONCENT_FEATURES)) != len(settings.CONCENT_FEATURES):
        return [Warning('Some features appear multiple times in CONCENT_FEATURES setting', hint = 'Remove the duplicate names.',      id = 'concent.W001')]

    if "concent-api" in settings.CONCENT_FEATURES and "core"                 not in settings.INSTALLED_APPS:
        return [Error("App 'core' required by 'concent-api' feature is not defined in INSTALLED_APPS",                 hint = "Add the missing app to INSTALLED_APPS.", id = 'concent.E004')]

    if "gatekeeper"  in settings.CONCENT_FEATURES  and "gatekeeper"           not in settings.INSTALLED_APPS:
        return [Error("App 'gatekeeper' required by 'gatekeeper' feature is not defined in INSTALLED_APPS",            hint = "Add the missing app to INSTALLED_APPS.", id = 'concent.E005')]

    if "admin-panel" in settings.CONCENT_FEATURES and "django.contrib.admin" not in settings.INSTALLED_APPS:
        return [Error("App 'django.contrib.admin' required by 'admin-panel' feature is not defined in INSTALLED_APPS", hint = "Add the missing app to INSTALLED_APPS.", id = 'concent.E006')]

    return []
