import time
from pytest import mark, fixture, skip

from utils.tis_log import LOG
from consts.cli_errs import CpuAssignment
from keywords import host_helper, system_helper, vm_helper, nova_helper
from testfixtures.resource_mgmt import ResourceCleanup


@fixture(scope='module')
def host_to_config(request):
    is_small_system = system_helper.is_small_footprint()
    if is_small_system:
        host = system_helper.get_standby_controller_name()
    else:
        host = host_helper.get_nova_host_with_min_or_max_vms(rtn_max=False)

    if not host:
        skip("No nova host available in the system.")

    vswitch_proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function='vSwitch', core_type='log_core')
    pform_proc_core_dict = host_helper.get_host_cpu_cores_for_function(host, function='platform', core_type='log_core')

    vswitch_original_num_p0 = len(vswitch_proc_core_dict[0])
    vswitch_original_num_p1 = len(vswitch_proc_core_dict[1]) if 1 in vswitch_proc_core_dict.keys() else 0
    platform_ogigin_num_p0 = len(pform_proc_core_dict[0])
    platform_original_num_p1 = len(pform_proc_core_dict[1]) if 1 in pform_proc_core_dict.keys() else 0

    def revert():
        host_helper.lock_host(host)
        host_helper.modify_host_cpu(host, 'vswitch', p0=vswitch_original_num_p0, p1=vswitch_original_num_p1)
        host_helper.modify_host_cpu(host, 'platform', p0=platform_ogigin_num_p0, p1=platform_original_num_p1)
        host_helper.unlock_host(host)
    request.addfinalizer(revert)

    ht_enabled = system_helper.is_hyperthreading_enabled(host)
    return host, ht_enabled, is_small_system


@mark.parametrize(('platform', 'vswitch', 'ht_required', 'cpe_required'), [
    # (None, None, None, None),           # Test without reconfig
    ((1, 0), (1, 1), None, False),      # Standard lab only
    ((2, 0), (1, 1), None, True),       # CPE only
    ((1, 2), (3, 2), None, None),
    ((1, 2), (2, 2), None, None),
    ((1, 0), (1, 0), False, False),     # Standard lab only
    ((2, 0), (1, 0), False, True),      # CPE only
    ((2, 0), (2, 0), None, True),       # CPE only
    ((1, 0), (2, 0), None, False),      # Standard lab only
])
def test_vswitch_cpu_reconfig(host_to_config, platform, vswitch, ht_required, cpe_required):
    """
    Test valid vswitch cpu reconfigurations, and verify vm can still be hosted on the modified host

    Args:
        host_to_config: hostname of the host to reconfig
        platform: cpu cores to config for platform
        vswitch: cpu cores to config for vswitch
        ht_required: whether hyperthreading is required for the testcase. skip test if requirement is not met
        cpe_required: whether cpe lab is required for the testcase. skip test if requirement is not met.

    Setups (module):
        - Find a nova host with minimum number of vms (or standby controller if small footprint lab) for testing
        - Record the cpu configs for vswitch and platform

    Test Steps:
        - Lock host
        - Reconfigure host platform and vswitch cpus to give numbers
        - Unlock host
        - Check ports and vswitch cores mapping in vswitch.ini are correct
        - Check host is still eligible to schedule instance via in nova host-list
        - Boot a vm
        - Live migrate to host if it's not originally booted on host

    Teardown:
        - Revert host platform and vswitch cpu configs

    """
    host, ht_enabled, is_cpe = host_to_config
    if ht_required is not None and ht_required is not ht_enabled:
        skip("Hyper-threading for {} is not {}".format(host, ht_required))

    if cpe_required is not None and cpe_required is not is_cpe:
        skip("Small footprint is not {}".format(cpe_required))

    if platform is not None or vswitch is not None:
        LOG.tc_step("Reconfigure host cpus. Platform: {}, vSwitch: {}".format(platform, vswitch))
        platform_args = {}
        for i in range(len(platform)):
            if i is not None:
                platform_args['p'+str(i)] = platform[i]

        vswitch_args = {}
        for j in range(len(vswitch)):
            if j is not None:
                vswitch_args['p'+str(j)] = vswitch[j]

        host_helper.lock_host(host)
        if platform is not None:
            host_helper.modify_host_cpu(host, 'platform', **platform_args)
        if vswitch is not None:
            host_helper.modify_host_cpu(host, 'vswitch', **vswitch_args)
        host_helper.unlock_host(host)

    LOG.tc_step("Check ports and vswitch cores mapping are correct.")
    with host_helper.ssh_to_host(host) as host_ssh:
        expt_vswitch_map = host_helper.get_expected_vswitch_port_engine_map(host_ssh)
        actual_vswitch_map = host_helper.get_vswitch_port_engine_map(host_ssh)
        assert expt_vswitch_map == actual_vswitch_map

    LOG.tc_step("Check {} is still a valid nova host.".format(host))
    host_helper.wait_for_hosts_in_nova(host, timeout=60, fail_ok=False)

    LOG.tc_step("Check vm can be launched on or live migrated to {}.".format(host))
    vm_id = vm_helper.boot_vm()[1]
    ResourceCleanup.add('vm', vm_id)
    if not nova_helper.get_vm_host(vm_id) == host:
        vm_helper.live_migrate_vm(vm_id, host)


@mark.parametrize(('platform', 'vswitch', 'ht_required', 'expt_err'), [
    mark.p1(((1, 1), (5, 5), False, "CpuAssignment.VSWITCH_TOO_MANY_CORES")),
    ((7, 9), (2, 2), None, "CpuAssignment.TOTAL_TOO_MANY_CORES"),   # Assume total<=10 cores/per proc & thread
    mark.p1((('cores-2', 'cores-2'), (2, 2), None, "CpuAssignment.NO_VM_CORE")),
    ((1, 1), (9, 8), None, "CpuAssignment.VSWITCH_TOO_MANY_CORES"),    # Assume total <= 10 cores/per proc & thread
    ((5, 5), (5, 4), None, "CpuAssignment.VSWITCH_TOO_MANY_CORES"),
    mark.p1(((5, 5), (6, 5), None, "CpuAssignment.TOTAL_TOO_MANY_CORES")),  # Assume total<=10core/proc&thread
    ((1, 1), (8, 10), None, "CpuAssignment.TOTAL_TOO_MANY_CORES"),  # Assume total <= 10 cores/per proc&thread
])
def test_vswitch_cpu_reconfig_negative(host_to_config, platform, vswitch, ht_required, expt_err):
    host, ht_enabled, is_cpe = host_to_config
    if ht_required is not None and ht_required is not ht_enabled:
        skip("Hyper-threading for {} is not {}".format(host, ht_required))

    if platform[0] == 'cores-2':
        p0, p1 = host_helper.get_logcores_counts(host, proc_ids=(0, 1))
        platform = int(p0) - 2, int(p1) - 2

    platform_args = {}
    for i in range(len(platform)):
        if i is not None:
            platform_args['p' + str(i)] = platform[i]

    vswitch_args = {}
    for j in range(len(vswitch)):
        if j is not None:
            vswitch_args['p' + str(j)] = vswitch[j]

    LOG.tc_step("Lock {}".format(host))
    host_helper.lock_host(host)

    LOG.tc_step("Attempt to reconfigure host cpus. Platform: {}, vSwitch: {}".format(platform, vswitch))
    # host_helper.modify_host_cpu(host, 'vswitch', **{'p0': 1, 'p1': 0})
    host_helper.modify_host_cpu(host, 'platform', **platform_args)
    code, output = host_helper.modify_host_cpu(host, 'vswitch', fail_ok=True, **vswitch_args)

    LOG.tc_step("Verify modify host cpu request is rejected.")
    assert 1 == code, "Modify host cpu request is not rejected."

    if "TOTAL_TOO_MANY_CORES" in expt_err:
        proc_id = 0 if platform[0] + vswitch[0] > 10 else 1
        expt_err = eval(expt_err).format(proc_id)
    else:
        expt_err = eval(expt_err)
    assert expt_err in output, "Expected error string is not in output"
