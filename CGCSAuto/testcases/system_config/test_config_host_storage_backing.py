
from pytest import mark, fixture

from utils.tis_log import LOG
from testfixtures.recover_hosts import HostsToRecover
from keywords import host_helper, system_helper


@fixture(autouse=True)
def check_alarms():
    pass


@mark.parametrize(('instance_backing', 'number_of_hosts'), [
    ('image', 'two'),
    ('image', 'one'),
    ('image', 'all'),
    ('lvm', 'two'),
    ('lvm', 'one'),
    ('lvm', 'all'),
    ('remote', 'two'),
    ('remote', 'one'),
    ('remote', 'all'),
])
def test_set_hosts_storage_backing_min(instance_backing, number_of_hosts):
    """
    Modify hosts storage backing if needed so that system has minimal number of hosts in given instance backing

    Args:
        instance_backing:
        number_of_hosts:

    Test Steps:
        - Calculate the hosts to be configured based on test params
        - Configure hosts to meet given criteria
        - Check number of hosts in given instance backing is as specified

    """
    if instance_backing == 'remote' and not system_helper.is_storage_system():
        # Need to fail instead of skip here because pytest returns 0 exit code when test skipped,
        # which would be considered as a pass by Jenkins
        assert False, "Not storage system. Skip configure remote backing"

    hosts = host_helper.get_nova_hosts()
    hosts_len = len(hosts)
    host_num_mapping = {
        'all': hosts_len,
        'two': 2,
        'one': 1
    }
    number_of_hosts = host_num_mapping[number_of_hosts]

    assert hosts_len >= number_of_hosts, "Not enough nova hosts available for configuration."

    hosts_with_backing = host_helper.get_hosts_by_storage_aggregate(instance_backing)
    if len(hosts_with_backing) >= number_of_hosts:
        LOG.info("Already have {} hosts in {} backing. Do nothing".format(len(hosts_with_backing), instance_backing))
        return

    number_to_config = number_of_hosts - len(hosts_with_backing)
    hosts_to_config = list(set(hosts) - set(hosts_with_backing))[0:number_to_config]
    LOG.tc_step("Configure following hosts to {} backing: {}".format(hosts_to_config, instance_backing))

    for host in hosts_to_config:
        HostsToRecover.add(host)
        host_helper.set_host_storage_backing(host=host, inst_backing=instance_backing, unlock=False,
                                             wait_for_host_aggregate=False)

    host_helper.unlock_hosts(hosts_to_config, check_hypervisor_up=True, fail_ok=False)

    LOG.tc_step("Waiting for hosts in {} aggregate".format(instance_backing))
    for host in hosts_to_config:
        host_helper.wait_for_host_in_aggregate(host, storage_backing=instance_backing)


@mark.parametrize(('instance_backing', 'number_of_hosts'), [
    ('image', 'two'),
    ('image', 'one'),
    ('image', 'zero'),
    ('lvm', 'two'),
    ('lvm', 'one'),
    ('lvm', 'zero'),
    ('remote', 'zero'),
    ('remote', 'one'),
    ('remote', 'two')
])
def test_set_hosts_storage_backing_equal(instance_backing, number_of_hosts):
    """
    Modify hosts storage backing if needed so that system has exact number of hosts in given instance backing

    Args:
        instance_backing:
        number_of_hosts:

    Test Steps:
        - Calculate the hosts to be configured based on test params
        - Configure hosts to meet given criteria
        - Check number of hosts in given instance backing is as specified

    """
    host_num_mapping = {
        'zero': 0,
        'one': 1,
        'two': 2
    }
    number_of_hosts = host_num_mapping[number_of_hosts]

    if instance_backing == 'remote' and number_of_hosts != 0 and not system_helper.is_storage_system():
        # Need to fail instead of skip here because pytest returns 0 exit code when test skipped,
        # which would be considered as a pass by Jenkins
        assert False, "Not storage system. Skip configure remote backing"

    LOG.tc_step("Calculate the hosts to be configured based on test params")
    hosts = host_helper.get_nova_hosts()

    assert len(hosts) >= number_of_hosts, "Not enough nova hosts available for configuration."

    hosts_with_backing = host_helper.get_hosts_by_storage_aggregate(instance_backing)
    if len(hosts_with_backing) == number_of_hosts:
        LOG.info("Already have {} hosts in {} backing. Do nothing".format(number_of_hosts, instance_backing))
        return

    elif len(hosts_with_backing) < number_of_hosts:
        backing_to_config = instance_backing
        number_to_config = number_of_hosts - len(hosts_with_backing)
        hosts_pool = list(set(hosts) - set(hosts_with_backing))
    else:
        backing_to_config = 'lvm' if instance_backing == 'image' else 'image'
        number_to_config = len(hosts_with_backing) - number_of_hosts
        hosts_pool = hosts_with_backing

    hosts_to_config = hosts_pool[0:number_to_config]
    LOG.tc_step("Configure following hosts to {} backing: {}".format(hosts_to_config, backing_to_config))

    for host in hosts_to_config:
        host_helper.set_host_storage_backing(host=host, inst_backing=backing_to_config, unlock=False,
                                             wait_for_host_aggregate=False)
        HostsToRecover.add(host)

    host_helper.unlock_hosts(hosts_to_config, check_hypervisor_up=True, fail_ok=False)

    LOG.tc_step("Waiting for hosts in {} aggregate".format(backing_to_config))
    for host in hosts_to_config:
        host_helper.wait_for_host_in_aggregate(host, storage_backing=backing_to_config)

    LOG.tc_step("Check number of {} hosts is {}".format(instance_backing, number_of_hosts))
    assert number_of_hosts == len(host_helper.get_hosts_by_storage_aggregate(instance_backing)), \
        "Number of {} hosts is not {} after configuration".format(instance_backing, number_of_hosts)
