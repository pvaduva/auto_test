import re
from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ImageMetadata
from consts.cli_errs import CpuRtErr        # Do not remove this import. Used in eval()
from keywords import nova_helper, vm_helper, host_helper, common, glance_helper, cinder_helper, system_helper, \
    check_helper
from testfixtures.fixture_resources import ResourceCleanup, GuestLogs


@mark.parametrize(('vcpus', 'cpu_pol', 'cpu_rt', 'rt_mask', 'shared_vcpu', 'expt_err'), [
    (2, 'dedicated', 'yes', None, None, 'CpuRtErr.RT_AND_ORD_REQUIRED'),
    (2, 'shared', 'yes', '^0', None, 'CpuRtErr.DED_CPU_POL_REQUIRED'),
    (3, None, 'yes', '^1', None, 'CpuRtErr.DED_CPU_POL_REQUIRED'),
    # (4, 'dedicated', 'no', '^0', None, 'TBD'),
    # (3, 'dedicated', None, '^0-1', '0', 'TBD'),
    (4, 'dedicated', 'yes', '^2-3', '1', 'CpuRtErr.RT_MASK_SHARED_VCPU_CONFLICT'),
    (1, 'dedicated', 'yes', '^0', None, 'CpuRtErr.RT_AND_ORD_REQUIRED'),
    (4, 'dedicated', 'yes', '^0-3', '2', 'CpuRtErr.RT_AND_ORD_REQUIRED'),
    # (4, 'dedicated', 'yes', '^1-4', None, 'CpuRtErr.RT_AND_ORD_REQUIRED')     # Invalid range is not checked
])
def test_flavor_cpu_realtime_negative(vcpus, cpu_pol, cpu_rt, rt_mask, shared_vcpu, expt_err):
    """

    Args:
        vcpus:
        cpu_pol:
        cpu_rt:
        rt_mask:
        shared_vcpu:
        expt_err:

    Test Steps:
        - Create a flavor with given number of vcpus
        - Attempt to set conflicting/invalid realtime specs and ensure it's rejected

    """

    flv_id, code, output = create_rt_flavor(vcpus, cpu_pol=cpu_pol, cpu_rt=cpu_rt, rt_mask=rt_mask,
                                            shared_vcpu=shared_vcpu, fail_ok=True)

    LOG.tc_step("Check extra specs is rejected and proper error message displayed")
    assert 1 == code
    assert re.search(eval(expt_err), output), "Actual: {}".format(output)


def create_rt_flavor(vcpus, cpu_pol, cpu_rt, rt_mask, shared_vcpu, fail_ok=False,
                     storage_backing=None, numa_nodes=None, cpu_thread=None, min_vcpus=None):
    LOG.tc_step("Create a flavor with {} vcpus".format(vcpus))
    flv_id = nova_helper.create_flavor(name='cpu_rt_{}'.format(vcpus), vcpus=vcpus, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flv_id)

    args = {
        FlavorSpec.CPU_POLICY: cpu_pol,
        FlavorSpec.CPU_REALTIME: cpu_rt,
        FlavorSpec.CPU_REALTIME_MASK: rt_mask,
        FlavorSpec.SHARED_VCPU: shared_vcpu,
        # FlavorSpec.NUMA_NODES: numa_nodes,
        FlavorSpec.CPU_THREAD_POLICY: cpu_thread,
        # FlavorSpec.MIN_VCPUS: min_vcpus
    }

    extra_specs = {}
    for key, val in args.items():
        if val is not None:
            extra_specs[key] = val

    LOG.tc_step("Set flavor extra specs: {}".format(extra_specs))
    code, output = nova_helper.set_flavor_extra_specs(flv_id, fail_ok=fail_ok, **extra_specs)
    return flv_id, code, output


def check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus, shared_vcpu=None,
                                           offline_cpus=None, check_virsh_vcpusched=True):
    LOG.tc_step("Check realtime and ordinary cpu info via virsh and ps")
    inst_name, vm_host = nova_helper.get_vm_nova_show_values(vm_id, fields=[":instance_name", ":host"], strict=False)

    with host_helper.ssh_to_host(hostname=vm_host) as host_ssh:

        LOG.info("------ Check vcpusched, emulatorpin, and vcpupin in virsh dumpxml")
        vcpupins, emulatorpins, vcpuscheds = host_helper.get_values_virsh_xmldump(
                instance_name=inst_name, host_ssh=host_ssh, target_type='dict',
                tag_paths=('cputune/vcpupin', 'cputune/emulatorpin', 'cputune/vcpusched'))

        # Each vcpu should have its own vcpupin entry in virsh dumpxml
        assert vcpus == len(vcpupins), "vcpupin entries count in virsh dumpxml is not the same as vm vcpus count"

        LOG.info("------ Check realtime cpu count is same as specified in flavor and with fifo 1 policy")

        if check_virsh_vcpusched:
            if not expt_rt_cpus:
                assert not vcpuscheds, "vcpushed exists in virsh dumpxml when realtime_cpu != yes"

            else:
                LOG.info("------ Check vcpusched for realtime cpus")
                virsh_rt_cpus = []
                for vcpusched in vcpuscheds:
                    virsh_scheduler = vcpusched['scheduler']
                    virsh_priority = vcpusched['priority']
                    assert 'fifo' == virsh_scheduler, "Actual shed policy in virsh dumpxml: {}".format(virsh_scheduler)
                    assert '1' == virsh_priority, "Actual priority in virsh dumpxml: {}".format(virsh_scheduler)

                    virsh_rt_cpu = int(vcpusched['vcpus'])
                    virsh_rt_cpus.append(virsh_rt_cpu)

                assert sorted(expt_rt_cpus) == sorted(virsh_rt_cpus), \
                    "Expected rt cpus: {}; Actual in virsh vcpusched: {}".format(expt_rt_cpus, virsh_rt_cpus)

        LOG.info("------ Check emulator cpus is a subset of ordinary cpus")
        emulator_cpusets_str = emulatorpins[0]['cpuset']
        emulator_cpusets = common.parse_cpus_list(emulator_cpusets_str)
        cpuset_dict = {}
        virsh_ord_cpus = []
        ord_cpusets = []
        rt_cpusets = []
        emulator_cpus = []
        for vcpupin in vcpupins:
            cpuset = int(vcpupin['cpuset'])
            vcpu_id = int(vcpupin['vcpu'])
            if cpuset in emulator_cpusets:
                # Don't include vcpu_id in case of scaled-down vm. Example:
                # <cputune>
                #   <shares>3072</shares>
                #   <vcpupin vcpu='0' cpuset='25'/>
                #   <vcpupin vcpu='1' cpuset='5'/>
                #   <vcpupin vcpu='2' cpuset='25'/>
                #   <emulatorpin cpuset='5,25'/>
                #   <vcpusched vcpus='2' scheduler='fifo' priority='1'/>
                # </cputune>
                if cpuset not in list(cpuset_dict.values()):
                    emulator_cpus.append(vcpu_id)
            cpuset_dict[vcpu_id] = cpuset

            if vcpu_id in expt_rt_cpus:
                rt_cpusets.append(cpuset)
            else:
                virsh_ord_cpus.append(vcpu_id)
                ord_cpusets.append(cpuset)

        LOG.info("cpuset dict: {}".format(cpuset_dict))
        assert sorted(expt_ord_cpus) == sorted(virsh_ord_cpus), \
            "expected ordinary cpus: {}; Actual in virsh vcpupin: {}".format(expt_ord_cpus, virsh_ord_cpus)

        if shared_vcpu is not None:
            assert emulator_cpus == [shared_vcpu], "Emulator cpu is not the shared vcpu"
        else:
            if expt_rt_cpus:
                assert sorted(emulator_cpus) == sorted(expt_ord_cpus), "Emulator cpus is not a subset of ordinary cpus"
            else:
                assert emulator_cpus == sorted(expt_ord_cpus)[:1], "Emulator cpu is not the first vcpu when " \
                                                                   "no realtime cpu or shared cpu set"

        comm_pattern = 'CPU [{}]/KVM'
        LOG.info("------ Check actual vm realtime cpu scheduler via ps")
        rt_comm = comm_pattern.format(','.join([str(vcpu) for vcpu in expt_rt_cpus]))
        vm_pid = vm_helper.get_vm_pid(instance_name=inst_name, host_ssh=host_ssh)
        ps_rt_scheds = vm_helper.get_sched_policy_and_priority_for_vcpus(vm_pid, host_ssh, cpusets=rt_cpusets,
                                                                         comm=rt_comm)
        assert len(expt_rt_cpus) == len(ps_rt_scheds)

        for ps_rt_sched in ps_rt_scheds:
            ps_rt_pol, ps_rt_prio, ps_rt_comm = ps_rt_sched
            expt_pol = 'FF'
            expt_prio = '1'
            if offline_cpus:
                if isinstance(offline_cpus, int):
                    offline_cpus = [offline_cpus]
                cpu = int(re.findall('(\d+)/KVM', ps_rt_comm)[0])
                if cpu in offline_cpus:
                    expt_pol = 'TS'
                    expt_prio = '-'

            assert ps_rt_pol == expt_pol, \
                "Actual sched policy: {}. ps_rt_sheds parsed: {}".format(ps_rt_pol, ps_rt_scheds)
            assert ps_rt_prio == expt_prio, \
                "Actual priority: {}. ps_rt_sheds parsed: {}".format(ps_rt_pol, ps_rt_scheds)

        LOG.info("------ Check actual vm ordinary cpu scheduler via ps")
        ord_comm = comm_pattern.format(','.join([str(vcpu) for vcpu in expt_ord_cpus]))
        ps_ord_scheds = vm_helper.get_sched_policy_and_priority_for_vcpus(vm_pid, host_ssh, cpusets=ord_cpusets,
                                                                          comm=ord_comm)
        for ps_ord_sched in ps_ord_scheds:
            ps_ord_pol, ps_ord_prio, ps_ord_comm = ps_ord_sched
            assert ps_ord_pol == 'TS' and ps_ord_prio == '-', "ps_ord_scheds parsed: {}".format(ps_ord_scheds)


def parse_rt_and_ord_cpus(vcpus, cpu_rt, cpu_rt_mask):

    total_cpus = list(range(vcpus))
    if cpu_rt != 'yes':
        ord_cpus = total_cpus
        rt_cpus = []

    else:
        tmp_cpus = cpu_rt_mask.split(',')
        ord_cpus = []
        for ord_cpus_str in tmp_cpus:
            if ord_cpus_str.startswith('^'):
                ord_cpus_str = ord_cpus_str.split('^')[1]
                ords = ord_cpus_str.split('-')
                if len(ords) == 1:
                    start = stop = int(ords[0])
                else:
                    start = int(ords[0])
                    stop = int(ords[1])
                for i in range(start, stop+1):
                    ord_cpus.append(i)

        rt_cpus = list(set(total_cpus) - set(ord_cpus))

    return rt_cpus, ord_cpus


@fixture(scope='module')
def check_hosts():
    LOG.info("Get system storage backing, shared cpu, and HT configs.")
    storage_backing, hosts, up_hypervisors = nova_helper.get_storage_backing_with_max_hosts()
    hosts_with_shared_cpu = []
    ht_hosts = []
    for host in hosts:
        shared_cores_for_host = host_helper.get_host_cpu_cores_for_function(hostname=host, func='shared')
        if shared_cores_for_host[0] or shared_cores_for_host.get(1):
            hosts_with_shared_cpu.append(host)
        if system_helper.is_hyperthreading_enabled(host):
            ht_hosts.append(host)
    return storage_backing, hosts_with_shared_cpu, ht_hosts


@mark.parametrize(('vcpus', 'cpu_rt', 'rt_mask', 'rt_source', 'shared_vcpu', 'numa_nodes', 'cpu_thread', 'min_vcpus'), [
    (3, None, '^0', 'flavor', None, None, 'prefer', None),   # min_vcpu deprecated
    (4, 'yes', '^0', 'favor', None, None, 'require', None),     # numa_nodes deprecated
    #   (6, 'yes', '^2-3', 'flavor', None, 1, 'isolate', 4),
    (6, 'yes', '^2-3', 'flavor', None, None, 'isolate', None),     # tmp. numa nodes deprecated
    (2, 'yes', '^1', 'flavor', 1, None, None, None),
    (3, 'yes', '^0-1', 'image', None, None, None, None),    # Deprecated - vcpu
    # (4, 'no', '^0-2', 'image', 0, 2, None, None),     # numa_nodes deprecated
    (3, 'yes', '^1-2', 'image', None, None, 'isolate', None),
    (4, 'no', '^0-2', 'flavor', 2, None, None, None),
    (4, 'no', '^0-2', 'image', None, None, None, None),
])
def test_cpu_realtime_vm_actions(vcpus, cpu_rt, rt_mask, rt_source, shared_vcpu, numa_nodes, cpu_thread, min_vcpus,
                                 check_hosts):
    """
    Test vm with realtime cpu policy specified in flavor
    Args:
        vcpus (int):
        cpu_rt (str|None):
        rt_source (str): flavor or image
        rt_mask (str):
        shared_vcpu (int|None):min_vcpus
        numa_nodes (int|None): number of numa_nodes to boot vm on
        cpu_thread
        min_vcpus
        check_hosts (tuple): test fixture

    Setups:
        - check storage backing and whether system has shared cpu configured

    Test Steps:
        - Create a flavor with given cpu realtime, realtime mask and shared vcpu extra spec settings
        - Create a vm with above flavor
        - Verify cpu scheduler policies via virsh dumpxml and ps
        - Perform following nova actions and repeat above step after each action:
            ['suspend', 'resume'],
            ['live_migrate'],
            ['cold_migrate'],
            ['rebuild']

    """
    storage_backing, hosts_with_shared_cpu, ht_hosts = check_hosts

    if cpu_thread == 'require' and len(ht_hosts) < 2:
        skip("Less than two hyperthreaded hosts")

    if shared_vcpu is not None and len(hosts_with_shared_cpu) < 2:
        skip("Less than two up hypervisors configured with shared cpu")

    cpu_rt_flv = cpu_rt
    if rt_source == 'image':
        # rt_mask_flv = cpu_rt_flv = None
        rt_mask_flv = '^0'
        rt_mask_img = rt_mask
    else:
        rt_mask_flv = rt_mask
        rt_mask_img = None

    image_id = None
    if rt_mask_img is not None:
        image_medata = {ImageMetadata.CPU_RT_MASK: rt_mask_img}
        image_id = glance_helper.create_image(name='rt_mask', cleanup='function', **image_medata)[1]

    vol_id = cinder_helper.create_volume(image_id=image_id)[1]
    ResourceCleanup.add('volume', vol_id)

    name = 'rt-{}_mask-{}_{}vcpu'.format(cpu_rt, rt_mask_flv, vcpus)
    flv_id = create_rt_flavor(vcpus, cpu_pol='dedicated', cpu_rt=cpu_rt_flv, rt_mask=rt_mask_flv,
                              shared_vcpu=shared_vcpu, numa_nodes=numa_nodes, cpu_thread=cpu_thread,
                              min_vcpus=min_vcpus, storage_backing=storage_backing)[0]

    LOG.tc_step("Boot a vm with above flavor")
    vm_id = vm_helper.boot_vm(name=name, flavor=flv_id, cleanup='function', source='volume', source_id=vol_id)[1]
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

    expt_rt_cpus, expt_ord_cpus = parse_rt_and_ord_cpus(vcpus=vcpus, cpu_rt=cpu_rt, cpu_rt_mask=rt_mask)

    check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus, shared_vcpu=shared_vcpu)
    vm_host = nova_helper.get_vm_host(vm_id)
    if shared_vcpu:
        assert vm_host in hosts_with_shared_cpu

    numa_num = 1 if numa_nodes is None else numa_nodes
    check_helper._check_vm_topology_via_vm_topology(vm_id, vcpus, 'dedicated', cpu_thread, numa_num, vm_host)

    expt_current_cpu = vcpus
    if min_vcpus is not None:
        GuestLogs.add(vm_id)
        LOG.tc_step("Scale down cpu once")
        vm_helper.scale_vm(vm_id, direction='down', resource='cpu')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)

        LOG.tc_step("Check current vcpus in nova show is reduced after scale down")
        expt_current_cpu -= 1
        check_helper.check_vm_vcpus_via_nova_show(vm_id, min_vcpus, expt_current_cpu, vcpus)

    for actions in [['suspend', 'resume'], ['stop', 'start'], ['live_migrate'], ['cold_migrate'], ['rebuild']]:
        LOG.tc_step("Perform {} on vm and check realtime cpu policy".format(actions))
        for action in actions:
            kwargs = {}
            if action == 'rebuild':
                kwargs = {'image_id': image_id}
            vm_helper.perform_action_on_vm(vm_id, action=action, **kwargs)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        vm_host_post_action = nova_helper.get_vm_host(vm_id)
        if shared_vcpu:
            assert vm_host_post_action in hosts_with_shared_cpu

        LOG.tc_step("Check cpu thread policy in vm topology and vcpus in nova show after {}".format(actions))
        check_helper._check_vm_topology_via_vm_topology(vm_id, vcpus, 'dedicated', cpu_thread, numa_num,
                                                        vm_host_post_action, current_vcpus=expt_current_cpu)
        check_virsh = True
        offline_cpu = None
        if min_vcpus is not None:
            offline_cpu = vcpus - 1
            if offline_cpu in expt_rt_cpus:
                check_virsh = False

            LOG.tc_step("Check vm vcpus are not changed after {}".format(actions))
            check_helper.check_vm_vcpus_via_nova_show(vm_id, min_vcpus, expt_current_cpu, vcpus)

        check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus, shared_vcpu=shared_vcpu,
                                               offline_cpus=offline_cpu, check_virsh_vcpusched=check_virsh)

    if min_vcpus is not None:
        LOG.tc_step('Scale up vm and stop/start, and ensure realtime cpu config persists')
        vm_helper.scale_vm(vm_id, direction='up', resource='cpu')
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        vm_helper.stop_vms(vm_id)
        vm_helper.start_vms(vm_id)
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
        check_helper.check_vm_vcpus_via_nova_show(vm_id, min_vcpus, vcpus, vcpus)
        check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus, shared_vcpu=shared_vcpu)
        GuestLogs.remove(vm_id)
