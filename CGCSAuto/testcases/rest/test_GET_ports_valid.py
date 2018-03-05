import pytest
from utils.tis_log import LOG
from utils.rest import Rest
from keywords import system_helper, host_helper

# @pytest.mark.parametrize(
#     'authorize_valid,resource_valid,expected_status', [
#         (True, True, 200),
#         (True, False,400),
#         (False, True, 401)
#     ]
# )
# def test_GET_ports_valid(authorize_valid, resource_valid, expected_status):
#     """
#     Test GET of <resource> with valid authentication.

#     Args:
#         n/a

#     Prerequisites: system is running
#     Test Setups:
#         n/a
#     Test Steps:
#         - Using requests GET <resource> with proper authentication
#         - Determine if expected status_code of 200 is received
#     Test Teardown:
#         n/a
#     """
#     r = Rest('sysinv')
#     path = "/ports/{}"
#     LOG.info(path)
#     if resource_valid:
#         port_list = system_helper.get_host_ports_values('controller-0', header = 'uuid')
#     else:
#         port_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']
#     LOG.info(port_list)
#     for port in port_list:
#         message = "Using requests GET {} with proper authentication"
#         LOG.tc_step(message.format(path))
#         res = path.format(port)
#         status_code, text = r.get(resource=res, auth=authorize_valid)
#         message = "Retrieved: status_code: {} message: {}"
#         LOG.info(message.format(status_code, text))
#         if status_code == 404:
#             pytest.skip("Unsupported resource in this configuration.")
#         else:
#             message = "Determine if expected code of {} is received"
#             LOG.tc_step(message.format(expected_status))
#             message = "Expected code of {} - received {} and message {}"
#             assert status_code == expected_status, message.format(expected_status, status_code, text)


@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_networks_valid(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/networks/{}"
    LOG.info(path)
    if resource_valid:
        network_list = system_helper.get_network_values()
    else:
        network_list = ['ffffffffffff-ffff-ffff-ffff-ffffffffffff']
    LOG.info(network_list)
    for network in network_list:
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(path))
        res = path.format(network)
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)

@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_clusters_valid(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/clusters/{}"
    LOG.info(path)
    if resource_valid: 
        cluster_list = system_helper.get_cluster_values()
    else:
        cluster_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']
    LOG.info(cluster_list)
    for cluster in cluster_list:
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(path))
        res = path.format(cluster)
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)


@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_ialarms_valid(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/ialarms/{}"
    LOG.info(path)
    if resource_valid:
        alarm_list = system_helper.get_alarms_table()
    else:
        alarm_list = {'values':[['ffffffff-ffff-ffff-ffff-ffffffffffff']]}
    LOG.info(alarm_list['values'])
    for alarm in alarm_list['values']:
        alarm_uuid = alarm
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(path))
        res = path.format(alarm_uuid)
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of expected_status - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)


def test_CGTS_7608_confirm_token_expiration_default():
    """
    test_CGTS_7608_confirm_token_expiration_default
    https://jira.wrs.com:8443/browse/CGTS-7608

    Args:
        n/a

    Prerequisites: system is running

    Test Setups:
        n/a
    Test Steps:
        - perform system service-parameter-list
        - search for token-expiration in table
          - should be 3600 - if not, we fail!
    Test Teardown:
        n/a
    """
    expected_default_value = "3600"
    result_list = system_helper.\
                  get_service_parameter_values(name='token_expiration')

    for default_value in result_list:
        LOG.info("Checking {} from {}".format(default_value, result_list))
        message = "Expected {} received {}"
        assert default_value == expected_default_value, \
            message.format(expected_default_value, default_value)
            

# @pytest.mark.parametrize(
#     'authorize_valid,resource_valid,expected_status', [
#         (True, True, 200),
#         (True, False, 400),
#         (False, True, 401)
#     ]
# )
# def test_GET_event_valid(authorize_valid, resource_valid, expected_status):
#     """
#     Test GET of <resource> with valid authentication.

#     Args:
#         n/a

#     Prerequisites: system is running
#     Test Setups:
#         n/a
#     Test Steps:
#         - Using requests GET <resource> with proper authentication
#         - Determine if expected status_code of 200 is received
#     Test Teardown:
#         n/a
#     """
#     r = Rest('sysinv')
#     path = "/event_log/{}"
#     LOG.info(path)
#     if resource_valid:
#         event_list = system_helper.get_events_table(uuid=True)
#     else:
#         event_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']
#     LOG.info(event_list['values'])
#     for event in event_list['values']:
#         event_uuid = event[0]
#         message = "Using requests GET {} with proper authentication"
#         LOG.tc_step(message.format(path))
#         res = path.format(event_uuid)
#         status_code, text = r.get(resource=res, auth=authorize_valid)
#         message = "Retrieved: status_code: {} message: {}"
#         LOG.info(message.format(status_code, text))
#         if status_code == 404:
#             pytest.skip("Unsupported resource in this configuration.")
#         else:
#             message = "Determine if expected code of {} is received"
#             LOG.tc_step(message.format(expected_status))
#             message = "Expected code of {} - received {} and message {}"
#             assert status_code == expected_status, message.format(expected_status, status_code, text)

@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_devices(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/devices/{}"
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        res = path.format(host)
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(res))
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)

# @pytest.mark.parametrize(
#     'authorize_valid,resource_valid,expected_status', [
#         (True, True, 200),
#         (True, False,400),
#         (False, True, 401)
#     ]
# )
# def test_GET_cpus(authorize_valid, resource_valid, expected_status):
#     """
#     Test GET of <resource> with valid authentication.

#     Args:
#         n/a

#     Prerequisites: system is running
#     Test Setups:
#         n/a
#     Test Steps:
#         - Using requests GET <resource> with proper authentication
#         - Determine if expected status_code of 200 is received
#     Test Teardown:
#         n/a
#     """
#     r = Rest('sysinv')
#     path = "/icpus/{}"
#     LOG.info(path)
#     LOG.info(system_helper.get_hostnames())
#     for host in system_helper.get_hostnames():
#         LOG.info(host)
#         if resource_valid:
#             cpu_table = system_helper.get_host_cpu_list_table(host)
#         else:
#             cpu_table =  ['ffffffff-ffff-ffff-ffff-ffffffffffff']
#         LOG.info(cpu_table)
#         for cpu in cpu_table['values']:
#             res = path.format(cpu[0])
#             message = "Using requests GET {} with proper authentication"
#             LOG.tc_step(message.format(res))
#             status_code, text = r.get(resource=res, auth=authorize_valid)
#             message = "Retrieved: status_code: {} message: {}"
#             LOG.info(message.format(status_code, text))
#             if status_code == 404:
#                 pytest.skip("Unsupported resource in this configuration.")
#             else:
#                 message = "Determine if expected code of {} is received"
#                 LOG.tc_step(message.format(expected_status))
#                 message = "Expected code of {} - received {} and message {}"
#                 assert status_code == expected_status, message.format(expected_status, status_code, text)

def test_GET_idisks():
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/idisks/{}"
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        LOG.info(host)
        disk_table = system_helper.get_disk_values(host)
        for disk_uuid in disk_table:
            res = path.format(disk_uuid)
            message = "Using requests GET {} with proper authentication"
            LOG.tc_step(message.format(res))
            status_code, text = r.get(resource=res, auth=True)
            message = "Retrieved: status_code: {} message: {}"
            LOG.info(message.format(status_code, text))
            if status_code == 404:
                pytest.skip("Unsupported resource in this configuration.")
            else:
                message = "Determine if expected code of 200 is received"
                LOG.tc_step(message)
                message = "Expected code of 200 - received {} and message {}"
                assert status_code == 200, message.format(status_code, text)


# @pytest.mark.parametrize(
#     'authorize_valid,resource_valid,expected_status', [
#         (True, True, 200),
#         (True, False,400),
#         (False, True, 401)
#     ]
# )
# def test_GET_imemory(authorize_valid, resource_valid, expected_status):
#     """
#     Test GET of <resource> with valid authentication.

#     Args:
#         n/a

#     Prerequisites: system is running
#     Test Setups:
#         n/a
#     Test Steps:
#         - Using requests GET <resource> with proper authentication
#         - Determine if expected status_code of 200 is received
#     Test Teardown:
#         n/a
#     """
#     r = Rest('sysinv')
#     path = "/imemories/{}"
#     LOG.info(path)
#     LOG.info(system_helper.get_hostnames())
#     for host in system_helper.get_hostnames():
#         LOG.info(host)
#         if resource_valid:
#             memory_table = system_helper.get_host_memory_table(host,0)
#         else:
#             memory_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']
#         LOG.info(memory_table)
#         for memory_uuid in memory_table:
#             res = path.format("aa12ecd7-d15c-4c78-bfcc-6b25eabf422b")
#             message = "Using requests GET {} with proper authentication"
#             LOG.tc_step(message.format(res))
#             status_code, text = r.get(resource=res, auth=authorize_valid)
#             message = "Retrieved: status_code: {} message: {}"
#             LOG.info(message.format(status_code, text))
#             if status_code == 404:
#                 pytest.skip("Unsupported resource in this configuration.")
#             else:
#                 message = "Determine if expected code of {} is received"
#                 LOG.tc_step(messagel.format(expected_status))
#                 message = "Expected code of {} - received {} and message {}"
#                 assert status_code == expected_status, message.format(expected_status,status_code, text)


@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_lldp_agents(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/lldp_agents/{}"
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        LOG.info(host)
        if resource_valid:
            lldp_table = system_helper.get_host_lldp_agent_table(host)
        else:
            lldp_table =  ['ffffffff-ffff-ffff-ffff-ffffffffffff']
        LOG.info(lldp_table)
        for lldp_uuid in lldp_table:
            res = path.format(lldp_uuid)
            message = "Using requests GET {} with proper authentication"
            LOG.tc_step(message.format(res))
            status_code, text = r.get(resource=res, auth=authorize_valid)
            message = "Retrieved: status_code: {} message: {}"
            LOG.info(message.format(status_code, text))
            if status_code == 404:
                pytest.skip("Unsupported resource in this configuration.")
            else:
                message = "Determine if expected code of {} is received"
                LOG.tc_step(message.format(expected_status))
                message = "Expected code of {} - received {} and message {}"
                assert status_code == expected_status, message.format(expected_status, status_code, text)

@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_lldp_neighbors(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/lldp_neighbors/{}"
    LOG.info(path)
    LOG.info(system_helper.get_hostnames())
    for host in system_helper.get_hostnames():
        LOG.info(host)
        if resource_valid:
            lldp_table = system_helper.get_host_lldp_neighbor_table(host)
        else:
            lldp_table = ['ffffffff-ffff-ffff-ffff-ffffffffffff']
        LOG.info(lldp_table)
        for lldp_uuid in lldp_table:
            res = path.format(lldp_uuid)
            message = "Using requests GET {} with proper authentication"
            LOG.tc_step(message.format(res))
            status_code, text = r.get(resource=res, auth=authorize_valid)
            message = "Retrieved: status_code: {} message: {}"
            LOG.info(message.format(status_code, text))
            if status_code == 404:
                pytest.skip("Unsupported resource in this configuration.")
            else:
                message = "Determine if expected code of {} is received"
                LOG.tc_step(message.format(expected_status))
                message = "Expected code of {} - received {} and message {}"
                assert status_code == expected_status, message.format(expected_status, status_code, text)

# @pytest.mark.parametrize(
#     'authorize_valid,resource_valid,expected_status', [
#         (True, True, 200),
#         (True, False,400),
#         (False, True, 401)
#     ]
# )
# def test_GET_loads(authorize_valid, resource_valid, expected_status):
#     """
#     Test GET of <resource> with valid authentication.

#     Args:
#         n/a

#     Prerequisites: system is running
#     Test Setups:
#         n/a
#     Test Steps:
#         - Using requests GET <resource> with proper authentication
#         - Determine if expected status_code of 200 is received
#     Test Teardown:
#         n/a
#     """
#     r = Rest('sysinv')
#     path = "/loads/{}"
#     LOG.info(path)
#     if resource_valid:
#         # was expecting a list but it's returning a string
#         load_list = system_helper.get_software_loads()
#         LOG.info(load_list)
#         load_list = load_list[0].split(" ")
#     else:
#         load_list = ["sql magic stuff leaks out"]
#     for load in load_list:
#         LOG.info(load)
#         res = path.format(load)
#         message = "Using requests GET {} with proper authentication"
#         LOG.tc_step(message.format(res))
#         status_code, text = r.get(resource=res, auth=authorize_valid)
#         message = "Retrieved: status_code: {} message: {}"
#         LOG.info(message.format(status_code, text))
#         if status_code == 404:
#             pytest.skip("Unsupported resource in this configuration.")
#         else:
#             message = "Determine if expected code of {} is received"
#             LOG.tc_step(message.format(expected_status))
#             message = "Expected code of {} - received {} and message {}"
#             assert status_code == expected_status, message.format(expected_status, status_code, text)

@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_services(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/services/{}"
    LOG.info(path)
    if resource_valid:
        service_list = system_helper.get_service_list_table()
    else:
        service_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']        
    for service in service_list:
        LOG.info(service)
        res = path.format(service)
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(res))
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)

@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_servicenodes(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/servicenodes/{}"
    LOG.info(path)
    if resource_valid:
        service_list = system_helper.get_servicenodes_list_table()
    else:
        service_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']        
    for service in service_list:
        LOG.info(service)
        res = path.format(service)
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(res))
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)

@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_servicegroup(authorize_valid, resource_valid, expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        authorize_valid - whether to use authentication or not
        resource_valid - whether the pathvariable is valid or not
        expected_status - what status is expected

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/servicegroup/{}"
    LOG.info(path)
    if resource_valid:
        service_list = system_helper.get_servicegroups_list_table()
    else:
        service_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']        
    for service in service_list:
        LOG.info(service)
        res = path.format(service)
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(res))
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)


@pytest.mark.parametrize(
    'authorize_valid,resource_valid,expected_status', [
        (True, True, 200),
        (True, False,400),
        (False, True, 401)
    ]
)
def test_GET_service_parameter(authorize_valid, 
                                   resource_valid, 
                                   expected_status):
    """
    Test GET of <resource> with valid authentication.

    Args:
        authorize_valid - whether to use authentication or not
        resource_valid - whether the pathvariable is valid or not
        expected_status - what status is expected

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> with proper authentication
        - Determine if expected status_code of 200 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    path = "/service_parameter/{}"
    LOG.info(path)
    if resource_valid:
        service_list = system_helper.get_service_parameter_values(rtn_value='uuid')
    else: 
        service_list = ['ffffffff-ffff-ffff-ffff-ffffffffffff']
    for service in service_list:
        LOG.info(service)
        res = path.format(service)
        message = "Using requests GET {} with proper authentication"
        LOG.tc_step(message.format(res))
        status_code, text = r.get(resource=res, auth=authorize_valid)
        message = "Retrieved: status_code: {} message: {}"
        LOG.info(message.format(status_code, text))
        if status_code == 404:
            pytest.skip("Unsupported resource in this configuration.")
        else:
            message = "Determine if expected code of {} is received"
            LOG.tc_step(message.format(expected_status))
            message = "Expected code of {} - received {} and message {}"
            assert status_code == expected_status, message.format(expected_status, status_code, text)
