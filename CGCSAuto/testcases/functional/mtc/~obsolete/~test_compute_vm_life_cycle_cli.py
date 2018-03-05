# Copyright (c) 2013-2014 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.

import time
from pytest import fixture, mark, skip, raises, fail
from utils.tis_log import LOG
from utils import cli, exceptions
from utils import table_parser
from consts.auth import Tenant
from consts.cgcs import HostAvailState
from keywords import vm_helper, nova_helper, system_helper, host_helper, cinder_helper
from testfixtures.fixture_resources import ResourceCleanup
from testfixtures.recover_hosts import HostsToRecover


@fixture(scope='function', autouse=True)
def check_alarms():
    pass


def _lock_unlock_computes_except_one(host_name, action='lock'):
    """"""
    compute_list = host_helper.get_hypervisors()

    if action == 'unlock':
        host_helper.unlock_hosts(compute_list)
    elif action == 'lock':
        for comp_name in compute_list:
            if comp_name != host_name:
                HostsToRecover.add(comp_name, scope='module')
                host_helper.lock_host(comp_name)


def launch_instance_on_compute(network_name=None,
                               flavor=None,
                               host_name=None,
                               image_name=None,
                               **instance_names):
    """
    Function for launching VM instance on specific compute node and
    check VM host value

    :network_name param: name of network (public or private)
    :flavor param:  flavour id
    :host_name param: name of required  host (compute-0 or compute-1)
    :image_name param: name launching image
    :instance_names param: names of instances that should be created

    instance_helpers.launch_instance_on_compute(self, network_name='private',
                flavor=1, host_name='compute-0', image_name='wrk5-avp',
                instance_name1='wrl5-test', instance_name2='wrl5-test-1')
    """

    LOG.tc_step('Locking unused computes and making sure {} is unlocked'.format(host_name))
    host_helper.unlock_host(host_name)
    _lock_unlock_computes_except_one(host_name, action='lock')

    assert host_name in host_helper.get_hosts(availability=[HostAvailState.AVAILABLE,
                                                            HostAvailState.DEGRADED])

    lvm_hosts = host_helper.get_hosts_in_storage_aggregate('local_lvm')
    remote_hosts = host_helper.get_hosts_in_storage_aggregate('remote')
    backing = 'local_image'
    if host_name in lvm_hosts:
        backing = 'local_lvm'
    elif host_name in remote_hosts:
        backing = 'remote'
    flavor_id = nova_helper.create_flavor(host_name, storage_backing=backing,
                                          check_storage_backing=False, guest_os=image_name)[1]
    ResourceCleanup.add('flavor', flavor_id)

    LOG.tc_step('Booting instances on {}'.format(host_name))
    vm_ids = []
    for name in instance_names:

        vm_id = vm_helper.boot_vm(name=instance_names[name], flavor=flavor_id, guest_os=image_name,
                                  cleanup='function')[1]
        vm_ids.append(vm_id)

    LOG.tc_step('Verify instances are running')
    time.sleep(10)
    for vm_id in vm_ids:
        show_instance_table = table_parser.table(cli.nova('show {}'.format(vm_id),
                                                          ssh_client=None, auth_info=Tenant.ADMIN))

        search_name = table_parser.get_values(show_instance_table,
                                              'Value',
                                              Property='OS-EXT-SRV-ATTR:host')[0]
        assert host_name == search_name
        search_name = table_parser.get_values(show_instance_table,
                                              'Value',
                                              Property='OS-EXT-SRV-ATTR:hypervisor_hostname')[0]
        assert host_name == search_name
        LOG.tc_step("Ssh into {} guest".format(image_name))
        with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id, vm_image_name=image_name) as vm_ssh:
            vm_ssh.exec_cmd('pwd')


@fixture(scope='module')
def _is_cpe():
    return system_helper.is_small_footprint()


# Remove this test as launching vms on specific host are already covered in various other testcases
@mark.usefixtures('ubuntu14_image')
@mark.parametrize(('host', 'guest'), [
    ('compute-0', 'ubuntu_14'),
    ('compute-0', None),
    ('compute-1', 'ubuntu_14'),
    ('compute-1', None),
    ])
def _test_launch_guest_instances_on_specific_compute(host, guest, _is_cpe):
    """
    Test launching Guest instances on specified compute

    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-0
              --nic net-id=<private_net_id> --nic net-id=<internal_net_id>
              --image=ubuntu-precise-amd64 ubuntu-test
    nova boot --key_name=controller-0 --flavor=1
              --availability-zone=nova-compute:compute-0
              --nic net-id=<private_net_id> --nic net-id=<internal_net_id>
              --image=ubuntu-precise-amd64 ubuntu-test-1
    Verification Steps
    1. lock all computes except first one
    2. boot 2 ubuntu VMs
    """

    if _is_cpe:
        skip("Skip for CPE lab")

    vm_name1 = 'vm-on-{}-test-1'.format(host)
    vm_name2 = 'vm-on-{}-test-2'.format(host)
    compute_name = host

    LOG.info('Booting ubuntu image on first compute')
    launch_instance_on_compute(host_name=compute_name,
                               image_name=guest,
                               instance_name1=vm_name1,
                               instance_name2=vm_name2)

