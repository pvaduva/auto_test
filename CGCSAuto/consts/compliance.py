
VM_ROUTE_VIA = '10.10.10.50'

# Refstack consts:
class RefStack:
    TEST_SUITES_DIR = '/folk/cgts/compliance/RefStack'      # Unused
    CLIENT_DIR = '/home/cumulus/refstack/refstack-client'
    TEMPEST_CONF = '{}/etc/tempest.conf'.format(CLIENT_DIR)
    TEST_HISTORY_DIR = '{}/.tempest/.testrepository/'.format(CLIENT_DIR)
    LOG_FILES = ('failing', 'test_run.log', '[0-9]*', 'summary.txt', 'test-list.txt')
    USER_PASSWORD = 'Test1234@'


# Dovetial consts
class Dovetail:
    DOVETAIL_HOST = 'tis-dovetail-test-node.cumulus.wrs.com'
    DOVETAIL_USER = 'dovetail'
    DOVETAIL_HOME = '/home/dovetail'
    DOVETAIL_PASSWORD = 'dovetail'
    OS_AUTH_URL = None
    TEMPEST_CONF = '{}/pre_config/tempest_conf.yaml'.format(DOVETAIL_HOME)
    POD = '{}/pre_config/pod.yaml'.format(DOVETAIL_HOME)

    @classmethod
    def set_os_auth_url(cls, auth_url):
        cls.OS_AUTH_URL = auth_url