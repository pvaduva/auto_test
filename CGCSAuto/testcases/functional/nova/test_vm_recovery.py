import time

from pytest import mark

from consts.auth import Tenant
from consts.proj_vars import ProjVar
from consts.cgcs import FlavorSpec, ImageMetadata, VMStatus, EventLogID
from consts.feature_marks import Features
from consts.kpi_vars import VMRecoveryNova, VMRecoveryNetworking
from consts.timeout import VMTimeout, EventLogTimeout
from keywords import nova_helper, vm_helper, host_helper, cinder_helper, glance_helper, system_helper, common, \
    network_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs
from utils.clients.ssh import NATBoxClient
from utils.kpi import kpi_log_parser
from utils.tis_log import LOG


# Note auto recovery metadata in image will not passed to vm if vm is booted from Volume
@mark.features(Features.AUTO_RECOV)
@mark.parametrize(('auto_recovery', 'disk_format', 'container_format'), [
    # mark.p3(('true', 'qcow2', 'bare')),   # default guest image is in raw format. This test now fails in pike.
    mark.p3(('False', 'raw', 'bare')),
])
def test_autorecovery_image_metadata_in_volume(auto_recovery, disk_format, container_format):
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
    property_key = ImageMetadata.AUTO_RECOVERY

    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(auto_recovery, disk_format, container_format))
    image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                          cleanup='function', **{property_key: auto_recovery})[1]

    LOG.tc_step("Create a volume from the image")
    vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Verify image properties are shown in cinder list")
    field = 'volume_image_metadata'
    vol_image_metadata_dict = cinder_helper.get_volume_states(vol_id=vol_id, fields=field)[field]
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
    mark.domain_sanity(('dedicated', None, 'false', 'qcow2', 'bare', False)),
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
        - Boot a vm with the flavor and from the image
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
        nova_helper.set_flavor_extra_specs(flavor=flavor_id, **extra_specs)

    property_key = ImageMetadata.AUTO_RECOVERY
    LOG.tc_step("Create an image with property auto_recovery={}, disk_format={}, container_format={}".
                format(image_auto_recovery, disk_format, container_format))
    if image_auto_recovery is None:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              cleanup='function')[1]
    else:
        image_id = glance_helper.create_image(disk_format=disk_format, container_format=container_format,
                                              cleanup='function', **{property_key: image_auto_recovery})[1]

    # auto recovery in image metadata will not work if vm booted from volume
    # LOG.tc_step("Create a volume from the image")
    # vol_id = cinder_helper.create_volume(name='auto_recov', image_id=image_id, rtn_exist=False)[1]
    # ResourceCleanup.add('volume', vol_id)

    LOG.tc_step("Boot a vm from image with auto recovery - {} and using the flavor with auto recovery - {}".format(
                image_auto_recovery, flavor_auto_recovery))
    vm_id = vm_helper.boot_vm(name='auto_recov', flavor=flavor_id, source='image', source_id=image_id,
                              cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    LOG.tc_step("Verify vm auto recovery is {} by setting vm to error state.".format(expt_result))
    vm_helper.set_vm_state(vm_id=vm_id, error_state=True, fail_ok=False)
    res_bool, actual_val = vm_helper.wait_for_vm_values(vm_id=vm_id, status=VMStatus.ACTIVE, fail_ok=True,
                                                        timeout=600)

    assert expt_result == res_bool, "Expected auto_recovery: {}. Actual vm status: {}".format(
            expt_result, actual_val)

    LOG.tc_step("Ensure vm is pingable after auto recovery")
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)


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
        - Create a volume from tis image
        - Boot a vm with the flavor and the volume
        - Verify guest heartbeat is established via fm event-logs
        - Set vm to unhealthy state via touch /tmp/unhealthy
        - Verify vm auto recovery behavior is as expected based on auto recovery setting in flavor

    Teardown:
        - Delete created vm, volume, image, flavor

    """

    LOG.tc_step("Create a flavor with guest_heartbeart set to True, and auto_recovery set to {} in extra spec".
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
    vm_id = vm_helper.boot_vm(name='test_ar_with_hb', flavor=flavor_id, cleanup='function')[1]

    LOG.tc_step("Verify vm heartbeat is on via event logs")
    system_helper.wait_for_events(EventLogTimeout.HEARTBEAT_ESTABLISH, strict=False, fail_ok=False,
                                  **{'Entity Instance ID': vm_id, 'Event Log ID': EventLogID.HEARTBEAT_ENABLED})

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
    GuestLogs.add(vm_id)

    LOG.tc_step("Wait for 30 seconds for vm initialization before touching file in /tmp")
    time.sleep(30)

    LOG.tc_step("Login to vm via NatBox")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Run touch /tmp/unhealthy to put vm into unhealthy state.")
        start_time = common.get_date_in_format()
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

        step_str = "is rebooted automatically" if expt_autorecovery else "is not rebooted"
        LOG.tc_step("Verify vm {} with auto recovery set to {}".format(step_str, expt_autorecovery))
        events = system_helper.wait_for_events(timeout=30, num=10, entity_instance_id=vm_id, start=start_time,
                                               fail_ok=True, strict=False,
                                               **{'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})
        natbox_ssh = NATBoxClient.get_natbox_client()
        natbox_ssh.send('')
        index = natbox_ssh.expect(["Power button pressed|Broken pipe"], timeout=70, fail_ok=True)

    if not expt_autorecovery:
        assert not events, "VM reboot is logged even though auto recovery is disabled"
        assert 0 > index, "VM is rebooted automatically even though Auto Recovery is set to false."

    else:
        assert events
        assert 0 == index, "Auto recovery to reboot the vm is not kicked off within timeout."

        LOG.tc_step("Wait for VM reach active state")
        vm_helper.wait_for_vm_values(vm_id, timeout=180, status=VMStatus.ACTIVE)

        LOG.tc_step("Ensure vm is still pingable after auto recovery")
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    GuestLogs.remove(vm_id)


@mark.features(Features.HEARTBEAT)
@mark.parametrize(('guest_heartbeat', 'heartbeat_enabled'), [
    mark.p1((None, False)),
    mark.p1(('true', True)),
    mark.p1(('false', False)),
    mark.priorities('domain_sanity', 'nightly', 'sx_nightly')(('True', True)),
])
def test_vm_heartbeat_without_autorecovery(guest_heartbeat, heartbeat_enabled):
    """
    Test guest heartbeat without autorecovery

    Args:
        guest_heartbeat (str|None): None (unset) or true or false
        heartbeat_enabled (bool): expected heartbeat availability

    Test Steps:
        - Create a flavor with auto recovery set to False and Guest Heartbeat set to given value in extra specs
        - Create a volume from tis image
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
    vm_id = vm_helper.boot_vm(name='test_hb_no_ar', flavor=flavor_id, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id=vm_id)
    GuestLogs.add(vm_id)

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

    LOG.tc_step("Wait for 30 seconds for vm initialization before touching file in /tmp")
    time.sleep(30)

    LOG.tc_step("Login to vm via NatBox and run touch /tmp/unhealthy")
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        vm_ssh.exec_cmd("touch /tmp/unhealthy")

    LOG.tc_step("Verify vm heartbeat failure event is {}logged".format(step_str))

    events_2 = system_helper.wait_for_events(timeout=EventLogTimeout.HEALTH_CHECK_FAIL, strict=False, fail_ok=True,
                                             **{'Entity Instance ID': vm_id, 'Event Log ID': [
                                                EventLogID.REBOOT_VM_COMPLETE, EventLogID.HEARTBEAT_CHECK_FAILED]})

    assert EventLogID.REBOOT_VM_COMPLETE not in events_2, "Auto recovery is triggered even if it's set to false."

    if heartbeat_enabled:
        assert EventLogID.HEARTBEAT_CHECK_FAILED in events_2, "VM heartbeat failure is not logged."
    else:
        assert not events_2, "VM heartbeat failure is logged while heartbeat is set to False."
    GuestLogs.remove(vm_id)


@mark.features(Features.AUTO_RECOV, Features.HEARTBEAT)
@mark.parametrize('heartbeat', [
    # mark.p1(True),    # remove - covered by test_vm_with_health_check_failure
    mark.priorities('sanity', 'cpe_sanity', 'sx_sanity', 'kpi')(False)
])
def test_vm_autorecovery_kill_host_kvm(heartbeat, collect_kpi):
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
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()
    internal_net_id = network_helper.get_internal_net_id()
    nics = [{'net-id': mgmt_net_id},
            {'net-id': tenant_net_id},
            {'net-id': internal_net_id}]
    vm_id = vm_helper.boot_vm(flavor=flavor_id, nics=nics, cleanup='function')[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    target_host = nova_helper.get_vm_host(vm_id)

    if collect_kpi and 'ixia_ports' in ProjVar.get_var("LAB"):
        LOG.tc_step("Launch an observer vm")

        mgmt_net_id = network_helper.get_mgmt_net_id(auth_info=Tenant.get_secondary())
        tenant_net_id = network_helper.get_tenant_net_id(auth_info=Tenant.get_secondary())
        nics = [{'net-id': mgmt_net_id},
                {'net-id': tenant_net_id},
                {'net-id': internal_net_id}]
        vm_observer = vm_helper.boot_vm(flavor=flavor_id, nics=nics, cleanup='function', auth_info=Tenant.get_secondary())[1]

        vm_helper.setup_kernel_routing(vm_observer)
        vm_helper.setup_kernel_routing(vm_id)

        vm_helper.route_vm_pair(vm_observer, vm_id)

        LOG.tc_step("Collect KPI for vm recovery after killing kvm")

        duration = vm_helper.get_traffic_loss_duration_on_operation(vm_id, vm_observer, kill_kvm_and_recover, vm_id,
                                                                    target_host)
        assert duration > 0, "No traffic loss detected during vm recovery after killing kvm"

        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=VMRecoveryNetworking.NAME,
                                  kpi_val=duration/1000, uptime=5)

        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name='vm_recovery', host=target_host,
                                  log_path=VMRecoveryNova.LOG_PATH, end_pattern=VMRecoveryNova.END.format(vm_id),
                                  start_pattern=VMRecoveryNova.START.format(vm_id), fail_ok=False)
    else:
        kill_kvm_and_recover(vm_id, target_host_=target_host)


def kill_kvm_and_recover(vm_id_, target_host_):
    instance_name = nova_helper.get_vm_instance_name(vm_id_)
    search_value = "qemu.*" + instance_name
    LOG.info("Search parameter: {}".format(search_value))
    kill_cmd = "kill -9 $(ps ax | grep %s | grep -v grep | awk '{print $1}')" % search_value

    with host_helper.ssh_to_host(target_host_) as host_ssh:
        host_ssh.exec_sudo_cmd(kill_cmd, expect_timeout=900)

    LOG.tc_step("Verify vm failed via event log")
    system_helper.wait_for_events(30, strict=False, fail_ok=False, entity_instance_id=vm_id_,
                                  **{'Event Log ID': EventLogID.VM_FAILED})

    LOG.tc_step("Verify vm is recovered on same host and is in good state")
    system_helper.wait_for_events(VMTimeout.AUTO_RECOVERY, strict=False, fail_ok=False, entity_instance_id=vm_id_,
                                  **{'Event Log ID': EventLogID.REBOOT_VM_COMPLETE})
    vm_helper.wait_for_vm_values(vm_id_, timeout=30, status=VMStatus.ACTIVE)
    assert target_host_ == nova_helper.get_vm_host(vm_id_)
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id_)
