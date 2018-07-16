VM_ROUTE_VIA = '10.10.10.50'

# Refstack consts:
class RefStack:
    TEST_SUITES_DIR = '/folk/cgts/compliance/RefStack'      # Unused
    CLIENT_DIR = '/home/cumulus/refstack/refstack-client'
    TEMPEST_CONF = '{}/etc/tempest.conf'.format(CLIENT_DIR)
    TEST_HISTORY_DIR = '{}/.tempest/.testrepository/'.format(CLIENT_DIR)
    LOG_FILES = ['failing', 'test_run.log', '[0-9]*', 'summary.txt']
    USER_PASSWORD = 'Test1234@'
