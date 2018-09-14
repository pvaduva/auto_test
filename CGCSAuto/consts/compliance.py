
VM_ROUTE_VIA = '10.10.10.50'


class RefStack:
    TEST_SUITES_DIR = '/folk/cgts/compliance/RefStack'      # Unused
    CLIENT_DIR = '/home/cumulus/refstack/refstack-client'
    TEMPEST_CONF = '{}/etc/tempest.conf'.format(CLIENT_DIR)
    TEST_HISTORY_DIR = '{}/.tempest/.testrepository/'.format(CLIENT_DIR)
    LOG_FILES = ('failing', 'test_run.log', '[0-9]*', 'summary.txt', 'test-list.txt')
    USER_PASSWORD = 'Test1234@'


class Dovetail:
    __OS_AUTH_URL = None
    TEST_NODE = 'tis-dovetail-test-node.cumulus.wrs.com'
    USERNAME = 'dovetail'
    PASSWORD = 'dovetail'
    HOME_DIR = '/home/dovetail'
    TEMPEST_YAML = '{}/pre_config/tempest_conf.yaml'.format(HOME_DIR)
    ENV_SH = '{}/pre_config/env_config.sh'.format(HOME_DIR)
    POD_YAML = '{}/pre_config/pod.yaml'.format(HOME_DIR)
    RESULTS_DIR = '{}/results'.format(HOME_DIR)

    @classmethod
    def set_auth_url(cls, auth_url):
        cls.__OS_AUTH_URL = auth_url

    @classmethod
    def get_auth_url(cls):
        return cls.__OS_AUTH_URL
