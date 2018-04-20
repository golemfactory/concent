from concent_api.constants import APP_LABEL_TO_DATABASE


class DatabaseRouter:
    """ A router to control all database operations on models in Concent. """

    def db_for_read(self, model, **hints):  # pylint: disable=unused-argument,no-self-use
        """ Returns database name which should be used to read given models data. """
        assert model._meta.app_label in APP_LABEL_TO_DATABASE

        return APP_LABEL_TO_DATABASE[model._meta.app_label]

    def db_for_write(self, model, **hints):  # pylint: disable=unused-argument,no-self-use
        """ Returns database name which should be used to write given models data. """
        assert model._meta.app_label in APP_LABEL_TO_DATABASE

        return APP_LABEL_TO_DATABASE[model._meta.app_label]

    def allow_relation(self, obj1, obj2, **hints):  # pylint: disable=unused-argument,no-self-use
        """ Returns True if relation between two objects can be created only if they are from the same app. """
        assert obj1._meta.app_label in APP_LABEL_TO_DATABASE
        assert obj2._meta.app_label in APP_LABEL_TO_DATABASE

        return obj1._meta.app_label == obj2._meta.app_label

    def allow_migrate(self, db, app_label, model_name = None, **hints):  # pylint: disable=unused-argument,no-self-use
        """
        Returns True if migration for given app_label should be created.
        Migration for given app_label should be created if its assigned database is equal to currently migrated.
        """
        assert app_label in APP_LABEL_TO_DATABASE

        return db == APP_LABEL_TO_DATABASE[app_label]
