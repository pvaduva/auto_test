import re

from pytest import mark

from utils import table_parser, exceptions
from utils.ssh import NATBoxClient
from utils.tis_log import LOG
from consts.feature_marks import Features
from consts.timeout import VMTimeout, EventLogTimeout
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus, EventLogID
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper, system_helper
from testfixtures.resource_mgmt import ResourceCleanup


@mark.features(Features.AUTO_RECOV)
@mark.parametrize(('auto_recovery', 'disk_format', 'container_format'), [
    mark.p1(('true', 'qcow2', 'bare')),
    mark.p1(('False', 'raw', 'bare')),
])
def test_image_metadata_in_volume(auto_recovery, disk_format, container_format):
    """
    Create image with given metadata/property.

    Args:
        auto_recovery (str): value for sw_wrs_auto_recovery to set in image
        disk_format (str): such as 'raw', 'qcow2'
        container_format (str): such as bare

    Test Steps;
        - Create image with given disk format, container format, property key and value pair
        - Verify property value is correctly set via glance image-show

    Teardown:
        - Delete created images

    """
    property_key = ImageMetadata.AUTO_RECOVERRY

    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(auto_recovery, disk_format, container_format))
    image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                          **{property_key: auto_recovery})[1]
    ResourceCleanup.add('image', resource_id=image_id)

    LOG.tc_step("Create a volume from the image")
    vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Verify image properties are shown in cinder list")
    field = 'volume_image_metadata'
    vol_image_metadata_dict = eval(cinder_helper.get_volume_states(vol_id=vol_id, fields=field)[field])
    LOG.info("vol_image_metadata dict: {}".format(vol_image_metadata_dict))

    assert auto_recovery.lower() == vol_image_metadata_dict[property_key].lower(), \
        "Actual volume image property {} value - {} is different than value set in image - {}".format(
                property_key, vol_image_metadata_dict[property_key], auto_recovery)

    assert disk_format == vol_image_metadata_dict['disk_format']
    assert container_format == vol_image_metadata_dict['container_format']


@mark.features(Features.AUTO_RECOV)
@mark.parametrize(('cpu_policy', 'flavor_auto_recovery', 'image_auto_recovery', 'disk_format', 'container_format', 'expt_result'), [
    mark.p1((None, None, None, 'raw', 'bare', True)),
    mark.p1((None, 'false', 'true', 'qcow2', 'bare', False)),
    mark.p1((None, 'true', 'false', 'raw', 'bare', True)),
    mark.p1(('dedicated', 'false', None, 'raw', 'bare', False)),
    mark.p1(('dedicated', None, 'false', 'qcow2', 'bare', False)),
    mark.p1(('shared', None, 'true', 'raw', 'bare', True)),
    mark.p1(('shared', 'false', None, 'raw', 'bare', False)),
])
def test_vm_autorecovery_without_heartbeat(cpu_policy, flavor_auto_recovery, image_auto_recovery, disk_format,
                                           container_format, expt_result):
    """
    Test auto recovery setting in vm with various auto recovery settings in flavor and image.

    Args:
        cpu_policy (str|None): cpu policy to set in flavor
        flavor_auto_recovery (str|None): None (unset) or true or false
        image_auto_recovery (str|None): None (unset) or true or false
        disk_format (str):
        container_format (str):
        expt_result (bool): Expected vm auto recovery behavior. False > disabled, True > enabled.

    Test Steps:
        - Create a flavor with auto recovery and cpu policy set to given values in extra spec
        - Create an image with auto recovery set to given value in metadata
        - Create a volume from above image
        - Boot a vm with the flavor and from the volume
        - Set vm state to error via nova reset-state
        - Verify vm auto recovery behavior is as expected

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Create a flavor with cpu_policy set to {} and auto_recovery set to {} in extra spec".format(
            cpu_policy, flavor_auto_recovery))
    flavor_id = nova_helper.create_flavor(name='auto_recover_'+str(flavor_auto_recovery))[1]
    ResourceCleanup.add('flavor', flavor_id)

    # Add extra specs as specified
    extra_specs = {}
    if cpu_policy is not None:
        extra_specs[FlavorSpec.CPU_POLICY] = cpu_policy
    if flavor_auto_recovery is not None:
        extra_specs[FlavorSpec.AUTO_RECOVERY] = flavor_auto_recovery

    if extra_specs:
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **{FlavorSpec.AUTO_RECOVERY: flavor_auto_recovery})

    property_key = ImageMetadata.AUTO_RECOVERRY
    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(image_auto_recovery, disk_format, container_format))
    if image_auto_recovery is None:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format)[1]
    else:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              **{property_key: image_auto_recovery})[1]
    ResourceCleanup.add('image', resource_id=image_id)

    LOG.tc_step("Create a volume from the image")
    vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from volume with auto recovery - {} and using the flavor with auto recovery - {}".format(
            image_auto_recovery, flavor_auto_recovery))
    vm_id = vm_helper.boot_vm(name='auto_recov', flavor=flavor_id, source='volume', source_id=vol_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=False)

    LOG.tc_step("Verify vm auto recovery is {} by setting vm to error state.".format(expt_result))
    vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
    res_bool, actual_val = vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True,
                                                        timeout=600)

    assert expt_result == res_bool, "Expected auto_recovery: {}. Actual vm status: {}".format(
            expt_result, actual_val)


@mark.features(Features.AUTO_RECOV, Features.HEARTBEAT)
@mark.parametrize(('cpu_policy', 'auto_recovery', 'expt_autorecovery'), [
    mark.p1((None, 'true', True)),
    mark.p1(('dedicated', None, True)),
    mark.p1((None, 'false', False)),
    mark.p1(('shared', None, True)),
    mark.p1(('shared', 'false', False)),
])
def test_vm_autorecovery_with_heartbeat(cpu_policy, auto_recovery, expt_autorecovery):
    """
    Test auto recovery with guest heartbeat enabled

    Args:
        cpu_policy (str|None): shared, dedicated or None (unset)
        auto_recovery (str|None): None (unset) or true or false. Auto recovery setting in flavor
        expt_autorecovery (bool): Expected vm auto recovery behavior. False > disabled, True > enabled.

    Test Steps:
        - Create a flavor with heartbeat set to true, and auto recovery set to given value in extra spec
        - Create a volume from cgcs-guest image
        - Boot a vm with the flavor and the volume
        - Verify guest heartbeat is established via system event-logs
        - Set vm to unhealthy state via touch /tmp/unhealthy
        - Verify vm auto recovery behavior is as expected based on auto recovery setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Create a flavor with guest_heartbeart set to true, and auto_recovery set to {} in extra spec".
                format(auto_recovery))
    flavor_id = nova_helper.create_flavor(name='auto_recover_' + str(auto_recovery))[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: 'True'}
    if cpu_policy is not None:
        extra_specs[FlavorSpec.CPU_POLICY] = cpu_policy
    if auto_recovery is not None:
        extra_specs[FlavorSpec.AUTO_RECOVERY] = auto_recovery

    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Boot a vm using the flavor with guest heartbeat - true and auto recovery - {}".format(auto_recovery))
    vm_id = vm_helper.boot_vm(name='test_ar_with_hb', flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)

    LOG.tc_step("Verify vm heartbeat is on via event logs")
    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id, 'Event Log ID': EventLogID.HEARTBEAT_ENABLED})

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    LOG.tc_step("Login to vm via NatBox")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Run touch /tmp/unhealthy to put vm into unhealthy state.")
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

        step_str = "is rebooted automatically" if expt_autorecovery else "is not rebooted"
        LOG.tc_step("Verify vm {} with auto recovery set to {}".format(step_str, expt_autorecovery))
        natbox_ssh = NATBoxClient.get_natbox_client()
        index = natbox_ssh.expect("Power button pressed", timeout=60, fail_ok=True)

        if not expt_autorecovery:
            assert 0 > index, "VM is rebooted automatically even though Auto Recovery is set to false."

        else:
            assert 0 == index, "Auto recovery to reboot the vm is not kicked off within timeout."

            LOG.tc_step("Verify instance rebooting active alarm is on")
            alarms_tab = system_helper.get_alarms()
            reasons = table_parser.get_values(alarms_tab, 'Reason Text', strict=False, **{'Entity ID': vm_id})
            assert re.search('Instance .* is rebooting on host', '\n'.join(reasons)), \
                "Instance rebooting active alarm is not listed"


@mark.features(Features.HEARTBEAT)
@mark.parametrize(('guest_heartbeat', 'heartbeat_enabled'), [
    mark.p1((None, False)),
    mark.p1(('true', True)),
    mark.p1(('false', False)),
    mark.p1(('True', True)),
])
def test_vm_heartbeat_without_autorecovery(guest_heartbeat, heartbeat_enabled):
    """
    Test guest heartbeat without autorecovery

    Args:
        guest_heartbeat (str|None): None (unset) or true or false
        heartbeat_enabled (bool): expected heartbeat availability

    Test Steps:
        - Create a flavor with auto recovery set to False and Guest Heartbeat set to given value in extra specs
        - Create a volume from cgcs-guest image
        - Boot a vm with the flavor and the volume
        - Verify vm heartbeat is (not) established based on the heartbeat setting in flavor
        - Set vm to unhealthy state using touch /tmp/unhealthy
        - Verify heartbeat failure is (not) logged based on heartbeat setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Create a flavor with auto_recovery set to false, and guest_heartbeat set to {} in extra spec".
                format(guest_heartbeat))
    flavor_id = nova_helper.create_flavor(name='guest_hb_' + str(guest_heartbeat))[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.AUTO_RECOVERY: 'False'}
    if guest_heartbeat is not None:
        extra_specs[FlavorSpec.GUEST_HEARTBEAT] = guest_heartbeat

    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Boot a vm using flavor with auto recovery - False and guest heartbeat - {}".format(guest_heartbeat))
    vm_id = vm_helper.boot_vm(name='test_hb_no_ar', flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id, del_vm_vols=True)

    if heartbeat_enabled:
        step_str = ''
    else:
        step_str = 'not '

    LOG.tc_step("Verify vm heartbeat is {}established via event logs".format(step_str))
    hb_tmout = EventLogTimeout.HEARTBEAT_ESTABLISH
    events_1 = system_helper.wait_for_events(hb_tmout, strict=False, fail_ok=True,
                                             **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                                EventLogID.HEARTBEAT_DISABLED, EventLogID.HEARTBEAT_ENABLED]})

    if heartbeat_enabled:
        assert events_1, "Heartbeat establish event is not displayed within {} seconds".format(hb_tmout)
        assert EventLogID.HEARTBEAT_ENABLED == events_1[0], "VM {} heartbeat failed to establish".format(vm_id)
    else:
        assert not events_1, "Heartbeat event generated unexpectedly: {}".format(events_1)

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)

    LOG.tc_step("Login to vm via NatBox and run touch /tmp/unhealthy")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

    LOG.tc_step("Verify vm heartbeat failure event is {}logged".format(step_str))

    events_2 = system_helper.wait_for_events(timeout=EventLogTimeout.HEALTH_CHECK_FAIL, fail_ok=True,
                                             **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                                EventLogID.SOFT_REBOOT_BY_VM, EventLogID.HEARTBEAT_CHECK_FAILED]})

    assert EventLogID.SOFT_REBOOT_BY_VM not in events_2, "Auto recovery is triggered even if it's set to false."

    if heartbeat_enabled:
        assert EventLogID.HEARTBEAT_CHECK_FAILED in events_2, "VM heartbeat failure is not logged."
    else:
        assert not events_2, "VM heartbeat failure is logged while heartbeat is set to False."


@mark.features(Features.AUTO_RECOV, Features.HEARTBEAT)
@mark.parametrize('heartbeat', [
    mark.p1(True),
    mark.sanity(False)
])
def test_vm_autorecovery_kill_host_kvm(heartbeat):
    """
    Test vm auto recovery by killing the host kvm.

    Args:
        heartbeat (bool): Weather or not to have heartbeat enabled in extra spec

    Test Steps:
        - Create a default flavor (auto recovery should be enabled by default)
        - Set guest-heartbeat extra spec to specified value
        - Boot a vm with above flavor
        - Kill the kvm processes on vm host
        - Verify auto recovery is triggered to reboot vm
        - Verify vm reaches Active state

    Teardown:
        - Delete created vm and flavor

    """
    LOG.tc_step("Create a flavor and set guest-heartbeat to {} in extra spec.".format(heartbeat))
    flavor_id = nova_helper.create_flavor(name='ar_default_hb_{}'.format(heartbeat))[1]
    ResourceCleanup.add('flavor', flavor_id)

    extra_specs = {FlavorSpec.GUEST_HEARTBEAT: str(heartbeat)}
    nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    LOG.tc_step("Boot a vm with above flavor")
    vm_id = vm_helper.boot_vm(flavor=flavor_id)[1]
    ResourceCleanup.add('vm', vm_id)

    target_host = nova_helper.get_vm_host(vm_id)

    LOG.tc_step("Kill the kvm processes on vm host: {}".format(target_host))
    with host_helper.ssh_to_host(target_host) as host_ssh:
        exit_code, output = host_ssh.exec_sudo_cmd('killall -s KILL qemu-kvm')
        if not exit_code == 0:
            raise exceptions.SSHExecCommandFailed("Failed to kill host kvm processes. Details: {}".format(output))

    LOG.tc_step("Verify vm failed via event log")
    system_helper.wait_for_events(30, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id, 'Event Log ID': EventLogID.VM_FAILED})

    LOG.tc_step("Verify vm auto rebooted to recover via event log, and reached Active state")
    system_helper.wait_for_events(VMTimeout.AUTO_RECOVERY, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id, 'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})

    vm_helper.wait_for_vm_values(vm_id, timeout=30, status=VMStatus.ACTIVE)
