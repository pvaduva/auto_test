import pytest
from utils.tis_log import LOG
from utils.rest import Rest
import sys

def attempt(operation, resource):
    print("Testing {} with {}".format(operation, resource))
    if operation == operation:
        return(True)
    else:
        return(False)

def get(resource):
    """
    Test GET of <resource> with invalid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests GET <resource> without proper authentication
        - Determine if expected status_code of 401 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    message = "Using requests GET {} without proper authentication"
    LOG.tc_step(message.format(resource))

    status_code, text = r.get(resource=resource, auth=False)
    message = "Retrieved: status_code: {} message: {}"
    LOG.info(message.format(status_code, text))

    LOG.tc_step("Determine if expected status_code of 401 is received")
    message = "Expected status_code of 401 - received {} and message {}"
    assert status_code == 401, message.format(status_code, text)

def delete(resource):
    """
    Test DELETE of <resource> with invalid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests DELETE <resource> without proper authentication
        - Determine if expected status_code of 401 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    LOG.tc_step("DELETE <resource> without proper authentication")
    status_code, text = r.delete(resource=resource, auth=False)
    LOG.info("Retrieved: status_code: {} message: {}".format(status_code, text))
    LOG.tc_step("Determine if expected status_code of 401 is received")

    message = "Expected status_code of 401 - received {} and message {}"
    assert status_code == 401, message.format(status_code, text)


def post(resource):
    """
    Test POST of <resource> with invalid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests POST <resource>
        - Determine if expected status_code of 401 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    LOG.tc_step("POST {}".format(resource))
    status_code, text = r.post(resource=resource, 
                               json_data={}, auth=False)
    message = "Retrieved: status_code: {} message: {}"
    LOG.info(message.format(status_code, text))
    LOG.tc_step("Determine if expected_code of 401 is received")
    message = "Expected code of 401 - received {} and message {}"
    assert status_code == 401, \
        message.format(status_code, text)


def patch(resource):
    """
    Test PATCH of <resource>  with invalid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests PATCH <resource> without proper authentication
        - Determine if expected status_code of 401 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    LOG.tc_step("PATCH {} with bad authentication".format(resource))
    status_code, text = r.patch(resource=resource, 
                                json_data={}, auth=False)

    message = "Retrieved: status_code: {} message: {}"
    LOG.info(message.format(status_code, text))
    LOG.tc_step("Determine if expected status_code of 401 is received")
    message = "Expected code of 401 - received {} and message {}"
    assert status_code == 401, message.format(status_code, text)


def put(resource):
    """
    Test PUT of <resource> with invalid authentication.

    Args:
        n/a

    Prerequisites: system is running
    Test Setups:
        n/a
    Test Steps:
        - Using requests PUT <resource> without proper authentication
        - Determine if expected status_code of 401 is received
    Test Teardown:
        n/a
    """
    r = Rest('sysinv')
    LOG.tc_step("PUT {} with bad authentication".format(resource))
    status_code, text = r.put(resource=resource, 
                              json_data={}, auth=False)
    message = "Retrieved: status_code: {} message: {}" 
    LOG.info(message.format(status_code, text))

    LOG.tc_step("Determine if expected status_code of 401 is received")
    message = "Expected code of 401 - received {} and message {}"
    assert status_code == 401, message.format(status_code, text)

@pytest.mark.parametrize(
    'operation,resource', [
        ('DELETE','/addrpools/{pool_id}'),
        ('DELETE','/ialarms/{alarm_uuid}'),
        ('DELETE','/icommunity/{community_id}'),
        ('DELETE','/ihosts/{host_id}/addresses/{address_id}'),
        ('DELETE','/ihosts/{host_id}'),
        ('DELETE','/ihosts/{host_id}/routes/{route_id}'),
        ('DELETE','/iinterfaces/{interface_id}'),
        ('DELETE','/ilvgs/{volumegroup_id}'),
        ('DELETE','/iprofiles/{profile_id}'),
        ('DELETE','/ipvs/{physicalvolume_id}'),
        ('DELETE','/istors/{stor_id}'),
        ('DELETE','/itrapdest/{trapdest_id}'),
        ('DELETE','/loads/{load_id}'),
        ('DELETE','/sdn_controller/{controller_id}'),
        ('DELETE','/service_parameter/{parameter_id}'),
        ('DELETE','/tpmconfig/{tpmconfig_id}'),
        ('DELETE','/upgrade'),
        ('GET','/addrpools'),
        ('GET','/addrpools/{pool_id}'),
        ('GET','/ceph_mon'),
        ('GET','/ceph_mon/{ceph_mon_id}'),
        ('GET','/clusters'),
        ('GET','/clusters/{uuid}'),
        ('GET','/controller_fs'),
        ('GET','/devices/{device_id}'),
        ('GET','/drbdconfig'),
        ('GET','/event_log'),
        ('GET','/event_log/{log_uuid}'),
        ('GET','/event_suppression'),
        ('GET','/health'),
        ('GET','/health/upgrade'),
        ('GET','/ialarms/{alarm_uuid}'),
        ('GET','/ialarms'),
        ('GET','/icommunity'),
        ('GET','/icommunity/{community_id}'),
        ('GET','/icpus/{cpu_id}'),
        ('GET','/idisks/{disk_id}'),
        ('GET','/idns'),
        ('GET','/iextoam'),
        ('GET','/ihosts'),
        ('GET','/ihosts/bulk_export'),
        ('GET','/ihosts/{host_id}/addresses/{address_id}'),
        ('GET','/ihosts/{host_id}/addresses'),
        ('GET','/ihosts/{host_id}'),
        ('GET','/ihosts/{host_id}/idisks'),
        ('GET','/ihosts/{host_id}/ilvgs'),
        ('GET','/ihosts/{host_id}/imemorys'),
        ('GET','/ihosts/{host_id}/ipvs'),
        ('GET','/ihosts/{host_id}/isensorgroups'),
        ('GET','/ihosts/{host_id}/isensors'),
        ('GET','/ihosts/{host_id}/istors'),
        ('GET','/ihosts/{host_id}/pci_devices'),
        ('GET','/ihosts/{host_id}/routes'),
        ('GET','/ihosts/{host_id}/routes/{route_id}'),
        ('GET','/iinfra'),
        ('GET','/iinterfaces/{interface_id}'),
        ('GET','/ilvgs/{volumegroup_id}'),
        ('GET','/imemorys/{memory_id}'),
        ('GET','/intp'),
        ('GET','/ipm'),
        ('GET','/iprofiles'),
        ('GET','/iprofiles/{profile_id}'),
        ('GET','/iprofiles/{profile_id}/icpus'),
        ('GET','/iprofiles/{profile_id}/iinterfaces'),
        ('GET','/iprofiles/{profile_id}/ports'),
        ('GET','/ipvs/{physicalvolume_id}'),
        ('GET','/isensorgroups/{sensorgroup_id}'),
        ('GET','/isensors/{sensor_id}'),
        ('GET','/istorconfig'),
        ('GET','/istors/{stor_id}'),
        ('GET','/isystems'),
        ('GET','/itrapdest'),
        ('GET','/itrapdest/{trapdest_id}'),
        ('GET','/lldp_agents'),
        ('GET','/lldp_agents/{lldp_agent_id}'),
        ('GET','/lldp_neighbors'),
        ('GET','/lldp_neighbors/{lldp_neighbor_id}'),
        ('GET','/loads'),
        ('GET','/loads/{load_id}'),
        ('GET','/networks'),
        ('GET','/networks/{network_id}'),
        ('GET','/ports/{port_id}'),
        ('GET','/remotelogging'),
        ('GET','/sdn_controller'),
        ('GET','/sdn_controller/{controller_id}'),
        ('GET','/servicegroup'),
        ('GET','/servicegroup/{servicegroup_id}'),
        ('GET','/servicenodes'),
        ('GET','/servicenodes/{node_id}'),
        ('GET','/service_parameter'),
        ('GET','/service_parameter/{parameter_id}'),
        ('GET','/services'),
        ('GET','/services/{service_id}'),
        ('GET','/storage_backend'),
        ('GET','/storage_backend/usage'),
        ('GET','/storage_ceph'),
        ('GET','/storage_lvm'),
        ('GET','/tpmconfig'),
        ('GET','/upgrade'),
        ('PATCH','/addrpools/{pool_id}'),
        ('PATCH','/ceph_mon/{ceph_mon_id}'),
        ('PATCH','/controller_fs/{controller_fs_id}'),
        ('PATCH','/devices/{device_id}'),
        ('PATCH','/drbdconfig/{drbdconfig_id}'),
        ('PATCH','/event_suppression/{event_suppression_uuid}'),
        ('PATCH','/icommunity/{community_id}'),
        ('PATCH','/idns/{dns_id}'),
        ('PATCH','/iextoam/{extoam_id}'),
        ('PATCH','/ihosts/{host_id}'),
        ('PATCH','/ihosts/{host_id}'),
        ('PATCH','/iinfra/{infra_id}'),
        ('PATCH','/iinterfaces/{interface_id}'),
        ('PATCH','/ilvgs/{volumegroup_id}'),
        ('PATCH','/imemorys/{memory_id}'),
        ('PATCH','/intp/{ntp_id}'),
        ('PATCH','/ipm/{pm_id}'),
        ('PATCH','/isensorgroups/{sensorgroup_id}'),
        ('PATCH','/isensors/{sensor_id}'),
        ('PATCH','/istors/{stor_id}'),
        ('PATCH','/isystems'),
        ('PATCH','/itrapdest/{trapdest_id}'),
        ('PATCH','/remotelogging/{remotelogging_id}'),
        ('PATCH','/sdn_controller/{controller_id}'),
        ('PATCH','/service_parameter/{parameter_id}'),
        ('PATCH','/services/{service_name}'),
        ('PATCH','/storage_ceph/{storage_ceph_id}'),
        ('PATCH','/storage_lvm/{storage_lvm_id}'),
        ('PATCH','/tpmconfig/{tpmconfig_id}'),
        ('PATCH','/upgrade'),
        ('POST','/addrpools'),
        ('POST','/firewallrules/import_firewall_rules'),
        ('POST','/icommunity'),
        ('POST','/ihosts'),
        ('POST','/ihosts/bulk_add'),
        ('POST','/ihosts/{host_id}/addresses'),
        ('POST','/ihosts/{host_id}/downgrade'),
        ('POST','/ihosts/{host_id}/iinterfaces'),
        ('POST','/ihosts/{host_id}/istors'),
        ('POST','/ihosts/{host_id}/routes'),
        ('POST','/ihosts/{host_id}/upgrade'),
        ('POST','/iinfra'),
        ('POST','/ilvgs'),
        ('POST','/iprofiles'),
        ('POST','/ipvs'),
        ('POST','/itrapdest'),
        ('POST','/loads/import_load'),
        ('POST','/sdn_controller'),
        ('POST','/service_parameter/apply'),
        ('POST','/service_parameter'),
        ('POST','/storage_ceph'),
        ('POST','/tpmconfig'),
        ('POST','/upgrade'),
        ('PUT','/ihosts/{host_id}/state/host_cpus_modify')
    ]
)
def test_bad_authentication(operation, resource):
    if operation == "GET":
        LOG.info("getting... {}".format(resource))
        get(resource)
    elif operation == "DELETE":
        LOG.info("deleting... {}".format(resource))
        delete(resource)
    elif operation == "PATCH":
        LOG.info("patching... {} {}".format(operation,resource))
        patch(resource)
    elif operation == "POST":
        LOG.info("posting... {} {}".format(operation,resource))        
        post(resource)
    elif operation == "PUT":
        LOG.info("putting... {} {}".format(operation,resource))
        put(resource)

        
