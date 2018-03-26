from assertpy                   import assert_that
from django.test                import override_settings
from django.conf                import settings
from django.test                import TestCase
from mock                       import patch

from concent_api.system_check   import create_error_13_ssl_cert_path_is_none
from concent_api.system_check   import create_error_14_cert_path_does_not_exist
from concent_api.system_check   import create_error_15_ssl_cert_path_is_not_a_file
from concent_api.system_check   import storage_cluster_certificate_path_check


# pylint: disable=no-self-use
class TestStorageClusterCertificatePathCheck(TestCase):
    @override_settings(
        STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = ''
    )
    def test_that_empty_string_does_not_produce_any_errors(self):
        errors = storage_cluster_certificate_path_check()

        assert_that(errors).is_instance_of(list)
        assert_that(errors).is_empty()

    @override_settings(
        STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = 'non_existing_path.crt'
    )
    def test_that_non_existing_path_produces_an_error(self):
        expected_error  = create_error_14_cert_path_does_not_exist(settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH)
        errors          = storage_cluster_certificate_path_check()

        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(expected_error)

    @override_settings(
        STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = None
    )
    def test_that_none_produces_an_error(self):
        expected_error  = create_error_13_ssl_cert_path_is_none()
        errors          = storage_cluster_certificate_path_check()

        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(expected_error)

    @override_settings(
        STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = "directory"
    )
    @patch('concent_api.system_check.os.path.exists', return_value = True)
    @patch('concent_api.system_check.os.path.isfile', return_value = False)
    def test_that_wrong_type_produces_an_error(self, _isfile_mock, _exists_mock):
        expected_error  = create_error_15_ssl_cert_path_is_not_a_file(settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH)
        errors          = storage_cluster_certificate_path_check()

        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(expected_error)

    @override_settings(
        STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = 'existing_file.crt'
    )
    @patch('concent_api.system_check.os.path.exists', return_value = True)
    @patch('concent_api.system_check.os.path.isfile', return_value = True)
    def test_that_correct_file_path_does_not_produce_any_error(self, _isfile_mock, _exists_mock):
        errors = storage_cluster_certificate_path_check()

        assert_that(errors).is_instance_of(list)
        assert_that(errors).is_empty()
