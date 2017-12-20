from django.apps import AppConfig


class ConcentApiConfig(AppConfig):
    name = 'concent_api'

    def ready(self):
        from concent_api import system_check  # noqa, flake8 F401 issue  # pylint: disable=unused-variable
