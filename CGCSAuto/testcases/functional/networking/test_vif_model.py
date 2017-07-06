import copy
from pytest import fixture, mark

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec
from keywords import vm_helper, nova_helper, network_helper

from testfixtures.fixture_resources import ResourceCleanup

def id_params(val):
    if not isinstance(val, str):
        new_val = []
        for val_1 in val:
            if isinstance(val_1, (tuple, list)):
                val_1 = '_'.join([str(val_2).lower() for val_2 in val_1])
            new_val.append(val_1)
    else:
        new_val = val

    return '_'.join(new_val)


@fixture(scope='module')
def mgmt_port_and_tenant_net():
    LOG.fixture_step("(module) Create a port for mgmt-net without specifying vif model")
    net_id = network_helper.get_mgmt_net_id()
    port_id = network_helper.create_port(net_id, wrs_vif=None)[1]
    ResourceCleanup.add('port', port_id, scope='module')

    tenant_net_id = network_helper.get_tenant_net_id()
    return port_id, tenant_net_id


@mark.parametrize('vif_models', [
    ['virtio'],
    ['avp'],
    ['e1000'],
    ['virtio', 'avp', 'e1000'],
    # ['pci-sriov'],
    # ['pci-passthrough'],
    # ['pci-passthrough', 'pci-sriov', 'avp', 'e1000', 'virtio']
], ids=id_params)
def test_vif_model_via_port(vif_models, mgmt_port_and_tenant_net):
    mgmt_port, tenant_net_id = mgmt_port_and_tenant_net

    LOG.tc_step("Create ports with vif_model specified: {}".format(vif_models))
    nics = [{'port-id': mgmt_port}]

    expt_ports = {mgmt_port: 'virtio'}
    for vif in vif_models:
        port = network_helper.create_port(tenant_net_id, wrs_vif=vif)[1]
        ResourceCleanup.add('port', port)
        expt_ports[port] = vif
        nics.append({'port-id': port})

    LOG.tc_step("Boot a vm with created ports")
    vm_id = vm_helper.boot_vm(name='vif_via_port', nics=nics, cleanup='function')[1]

    LOG.tc_step("Check vif models specified when creating ports are applied to vm nics")
    nova_show_nics = nova_helper.get_vm_interfaces_info(vm_id=vm_id)
    nics_to_check = copy.deepcopy(nova_show_nics)
    err = ''
    for expt_port, expt_vif in expt_ports.items():
        for nova_show_nic in nics_to_check:
            if expt_port == nova_show_nic['port_id']:
                nova_show_vif = nova_show_nic['vif_model']
                if not expt_vif == nova_show_vif:
                    err += '\nExpect {} for port {}; Actual: {}'.format(expt_vif, expt_port, nova_show_vif)

                nics_to_check.remove(nova_show_nic)
                break
        else:
            err += '\nPort {} is not found in nova show'.format(expt_port)

    assert not err, err

#
# @fixture(scope='module')
# def base_setup():
#
#     flavor_id = nova_helper.create_flavor(name='dedicated')[1]
#     ResourceCleanup.add('flavor', flavor_id, scope='module')
#
#     nova_helper.set_flavor_extra_specs(flavor_id, **{FlavorSpec.CPU_POLICY: 'dedicated'})
#
#     mgmt_net_id = network_helper.get_mgmt_net_id()
#     tenant_net_id = network_helper.get_tenant_net_id()
#     internal_net_id = network_helper.get_internal_net_id()
#
#     nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
#             {'net-id': tenant_net_id, 'vif-model': 'virtio'},
#             {'net-id': internal_net_id, 'vif-model': 'virtio'}
#     ]
#     base_vm = vm_helper.boot_vm(name='vif', flavor=flavor_id, nics=nics, cleanup='module', reuse_vol=False)[1]
#     # ResourceCleanup.add('vm', base_vm, scope='module')
#
#     return base_vm, mgmt_net_id, tenant_net_id, internal_net_id

# # Remove following testcase as it has been covered in other tests
# # @mark.sanity
# @mark.parametrize('vif_model', [
#     'avp',
#     'e1000',
#     'virtio'
# ])
# def _test_vif_models(vif_model, base_setup):
#     """
#     boot avp,e100 and virtio instance
#     KNI is same as avp
#
#     Test Steps:
#         - boot up a vm with given vif model
#         - Ping VM from Natbox(external network)
#         - Ping from VM to itself over data network
#         - Live-migrate the VM and verify ping over management and data networks
#         - Cold-migrate the VM and verify ping over management and data networks
#         - Pause and un-pause the VM and verify ping over management and data networks
#         - Suspend and resume the VM and verify ping over management and data networks
#         - Stop and start the VM and verify ping over management and data networks
#         - Reboot the VM and verify ping over management and data networks
#
#     Test Teardown:
#         - Delete vm created
#         - Delete flavor created
#
#     """
#     base_vm, mgmt_net_id, tenant_net_id, internal_net_id = base_setup
#
#     nics = [{'net-id': mgmt_net_id, 'vif-model': 'virtio'},
#             {'net-id': tenant_net_id, 'vif-model': vif_model},
#             {'net-id': internal_net_id, 'vif-model': 'avp'}]
#
#     LOG.tc_step("Boot vm with vif_model {} for tenant-net".format(vif_model))
#     vm_under_test = vm_helper.boot_vm(name=vif_model, nics=nics, cleanup='function', reuse_vol=False)[1]
#     # ResourceCleanup.add('vm', vm_under_test)
#
#     LOG.tc_step("Ping VM {} from NatBox(external network)".format(vm_under_test))
#     vm_helper.wait_for_vm_pingable_from_natbox(vm_under_test, fail_ok=False)
#
#     LOG.info("Ping vm under test from base vm over data network")
#     vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=vm_under_test, net_types='data')
#
#     # Following steps are moved to test_nova_actions.py
#
#     # LOG.tc_step("Live-migrate the VM and verify ping over management and data networks")
#     # vm_helper.live_migrate_vm(vm_under_test)
#     # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
#     #
#     # LOG.tc_step("Cold-migrate the VM and verify ping over management and data networks")
#     # vm_helper.cold_migrate_vm(vm_under_test)
#     # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
#     #
#     # LOG.tc_step("Pause and un-pause the VM and verify ping over management and data networks")
#     # vm_helper.pause_vm(vm_under_test)
#     # vm_helper.unpause_vm(vm_under_test)
#     # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
#     #
#     # LOG.tc_step("Suspend and resume the VM and verify ping over management and data networks")
#     # vm_helper.suspend_vm(vm_under_test)
#     # vm_helper.resume_vm(vm_under_test)
#     # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
#     #
#     # LOG.tc_step("Stop and start the VM and verify ping over management and data networks")
#     # vm_helper.stop_vms(vm_under_test)
#     # vm_helper.start_vms(vm_under_test)
#     # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
#     #
#     # LOG.tc_step("Reboot the VM and verify ping over management and data networks")
#     # vm_helper.reboot_vm(vm_under_test)
#     # vm_helper.ping_vms_from_vm(to_vms=vm_under_test, from_vm=base_vm, net_types=['mgmt', 'data'])
