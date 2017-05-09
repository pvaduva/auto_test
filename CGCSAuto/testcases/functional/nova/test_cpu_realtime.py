import re
import time
from pytest import mark, fixture, skip

from utils.tis_log import LOG

from consts.cgcs import FlavorSpec, ImageMetadata
from consts.cli_errs import CpuRtErr        # Do not remove this import. Used in eval()
from keywords import nova_helper, vm_helper, host_helper, common, glance_helper, cinder_helper
from testfixtures.fixture_resources import ResourceCleanup


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

    flv_id, code, output = create_rt_flavor(vcpus, cpu_pol, cpu_rt, rt_mask, shared_vcpu, True, False)

    LOG.tc_step("Check extra specs is rejected and proper error message displayed")
    assert 1 == code
    assert re.search(eval(expt_err), output), "Actual: {}".format(output)


def create_rt_flavor(vcpus, cpu_pol, cpu_rt, rt_mask, shared_vcpu, fail_ok=False, check_storage_backing=True,
                     storage_backing=None, numa_nodes=None):
    LOG.tc_step("Create a flavor with {} vcpus".format(vcpus))
    flv_id = nova_helper.create_flavor(name='cpu_rt_{}'.format(vcpus), vcpus=vcpus,
                                       check_storage_backing=check_storage_backing, storage_backing=storage_backing)[1]
    ResourceCleanup.add('flavor', flv_id)

    args = {
        FlavorSpec.CPU_POLICY: cpu_pol,
        FlavorSpec.CPU_REALTIME: cpu_rt,
        FlavorSpec.CPU_REALTIME_MASK: rt_mask,
        FlavorSpec.SHARED_VCPU: shared_vcpu,
        FlavorSpec.NUMA_NODES: numa_nodes
    }

    extra_specs = {}
    for key, val in args.items():
        if val is not None:
            extra_specs[key] = val

    LOG.tc_step("Set flavor extra specs: {}".format(extra_specs))
    code, output = nova_helper.set_flavor_extra_specs(flv_id, fail_ok=fail_ok, **extra_specs)
    return flv_id, code, output


def check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus):
    inst_name, vm_host = nova_helper.get_vm_nova_show_values(vm_id, fields=[":instance_name", ":host"], strict=False)

    with host_helper.ssh_to_host(hostname=vm_host) as host_ssh:

        LOG.tc_step("Check vcpusched, emulatorpin, and vcpupin in virsh dumpxml")
        vcpupins, emulatorpins, vcpuscheds = host_helper.get_values_virsh_xmldump(
                instance_name=inst_name, host_ssh=host_ssh, target_type='dict',
                tag_path=('cputune/vcpupin', 'cputune/emulatorpin', 'cputune/vcpusched'))

        # Each vcpu should have its own vcpupin entry in vish dumpxml
        assert vcpus == len(vcpupins), "vcpupin entries count in virsh dumpxml is not the same as vm vcpus count"

        LOG.tc_step("Check realtime cpu count is same as specified in flavor and with fifo 1 policy")

        if not expt_rt_cpus:
            assert not vcpuscheds, "vcpushed exists in virsh dumpxml when realtime_cpu != yes"

        else:
            LOG.tc_step("Check vcpusched for realtime cpus")
            vcpusched = vcpuscheds[0]
            virsh_scheduler = vcpusched['scheduler']
            virsh_priority = vcpusched['priority']
            assert 'fifo' == virsh_scheduler, "Actual shed policy in virsh dumpxml: {}".format(virsh_scheduler)
            assert '1' == virsh_priority, "Actual priority in virsh dumpxml: {}".format(virsh_scheduler)

            virsh_rt_cpus = common._parse_cpus_list(vcpusched['vcpus'])
            assert sorted(expt_rt_cpus) == sorted(virsh_rt_cpus), \
                "Expected rt cpus: {}; Actual in virsh vcpusched: {}".format(expt_rt_cpus, virsh_rt_cpus)

        LOG.tc_step("Check emulator cpus is a subset of ordinary cpus")
        emulator_cpusets_str = emulatorpins[0]['cpuset']
        emulater_cpusets = common._parse_cpus_list(emulator_cpusets_str)
        cpuset_dict = {}
        virsh_ord_cpus = []
        ord_cpusets = []
        rt_cpusets = []
        emulator_cpus = []
        for vcpupin in vcpupins:
            cpuset = vcpupin['cpuset']
            vcpu_id = int(vcpupin['vcpu'])
            cpuset_dict[vcpu_id] = cpuset
            if cpuset in emulater_cpusets:
                emulator_cpus.append(vcpu_id)

            if vcpu_id in expt_rt_cpus:
                rt_cpusets.append(cpuset)
            else:
                virsh_ord_cpus.append(vcpu_id)
                ord_cpusets.append(cpuset)

        LOG.info("cpuset dict: {}".format(cpuset_dict))
        assert sorted(expt_ord_cpus) == sorted(virsh_ord_cpus), \
            "expected ordinary cpus: {}; Actual in virsh vcpupin: {}".format(expt_ord_cpus, virsh_ord_cpus)
        assert set(emulator_cpus) < set(expt_ord_cpus), "Emulator cpus is not a subset of ordinary cpus"

        LOG.tc_step("Check actual vm realtime cpu scheduler via ps")
        vm_pid = vm_helper.get_vm_pid(instance_name=inst_name, host_ssh=host_ssh)
        ps_rt_scheds = vm_helper.get_sched_policy_and_priority_for_vcpus(vm_pid, host_ssh, cpusets=rt_cpusets)
        assert len(expt_rt_cpus) == len(ps_rt_scheds)

        for ps_rt_sched in ps_rt_scheds:
            ps_rt_pol, ps_rt_prio = ps_rt_sched
            assert ps_rt_pol == 'FF', "Actual sched policy: {}. ps_rt_sheds parsed: {}".format(ps_rt_pol, ps_rt_scheds)
            assert ps_rt_prio == '1', "Actual priority: {}. ps_rt_sheds parsed: {}".format(ps_rt_pol, ps_rt_scheds)

        LOG.tc_step("Check actual vm ordinary cpu scheduler via ps")
        ps_ord_scheds = vm_helper.get_sched_policy_and_priority_for_vcpus(vm_pid, host_ssh, cpusets=ord_cpusets,
                                                                          comm='CPU.*KVM|qemu-kvm')
        for ps_ord_sched in ps_ord_scheds:
            ps_ord_pol, ps_ord_prio = ps_ord_sched
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
    storage_backing, hosts = nova_helper.get_storage_backing_with_max_hosts(rtn_down_hosts=False)
    hosts_with_shared_cpu = []
    for host in hosts:
        shared_cores_for_host = host_helper.get_host_cpu_cores_for_function(hostname=host, function='shared')
        if shared_cores_for_host[0] or shared_cores_for_host[1]:
            hosts_with_shared_cpu.append(host)

    return storage_backing, hosts_with_shared_cpu


@mark.parametrize(('vcpus', 'cpu_rt', 'rt_mask', 'rt_source', 'shared_vcpu', 'numa_nodes'), [
    (3, None, '^0', 'flavor', None, None),
    (6, 'yes', '^2-3', 'flavor', None, 2),
    (3, 'yes', '^0-1', 'image', None, None),
    (4, 'no', '^0-2', 'image', 0, None),
    (3, 'yes', '^1-2', 'image', 2, 2),
    (2, 'yes', '^1', 'flavor', 1, 1)
])
def test_cpu_realtime_vm_actions(vcpus, cpu_rt, rt_mask, rt_source, shared_vcpu, numa_nodes, check_hosts):
    """
    Test vm with realtime cpu policy specified in flavor
    Args:
        vcpus (int):
        cpu_rt (str|None):
        rt_mask (str):
        shared_vcpu (int|None):
        numa_nodes (int): number of numa_nodes to boot vm on
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
    storage_backing, hosts_with_shared_cpu = check_hosts

    if shared_vcpu is not None and len(hosts_with_shared_cpu) < 2:
        skip("Less than two up hypervisors configured with shared cpu")

    if rt_source == 'image':
        # rt_mask_flv = cpu_rt_flv = None
        rt_mask_flv = '^0'
        cpu_rt_flv = 'yes'
        rt_mask_img = rt_mask
        cpu_rt_img = cpu_rt
    else:
        rt_mask_img = cpu_rt_img = None
        rt_mask_flv = rt_mask
        cpu_rt_flv = cpu_rt

    image_id = None
    if cpu_rt_img is not None:
        image_medata = {ImageMetadata.CPU_RT_MASK: rt_mask_img, ImageMetadata.CPU_RT: cpu_rt_img}
        image_id = glance_helper.create_image(name='rt_mask', **image_medata)[1]
        ResourceCleanup.add('image', image_id)

    vol_id = cinder_helper.create_volume(image_id=image_id)[1]
    ResourceCleanup.add('volume', vol_id)

    name = 'rt-{}_mask-{}_{}vcpu'.format(cpu_rt, rt_mask_flv, vcpus)
    flv_id = create_rt_flavor(vcpus, cpu_pol='dedicated', cpu_rt=cpu_rt_flv, rt_mask=rt_mask_flv,
                              shared_vcpu=shared_vcpu, numa_nodes=numa_nodes, check_storage_backing=False,
                              storage_backing=storage_backing)[0]

    LOG.tc_step("Boot a vm with above flavor")
    vm_id = vm_helper.boot_vm(name=name, flavor=flv_id, cleanup='function', source='volume', source_id=vol_id)[1]
    expt_rt_cpus, expt_ord_cpus = parse_rt_and_ord_cpus(vcpus=vcpus, cpu_rt=cpu_rt, cpu_rt_mask=rt_mask)

    check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus)
    if shared_vcpu:
        vm_host = nova_helper.get_vm_host(vm_id)
        assert vm_host in hosts_with_shared_cpu

    for actions in [['suspend', 'resume'], ['live_migrate'], ['cold_migrate'], ['rebuild']]:
        LOG.tc_step("Perform {} on vm and check realtime cpu policy".format(actions))
        for action in actions:
            kwargs = {}
            if action == 'rebuild':
                kwargs = {'image_id': image_id}
            vm_helper.perform_action_on_vm(vm_id, action=action, **kwargs)

        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, fail_ok=True)
        check_rt_and_ord_cpus_via_virsh_and_ps(vm_id, vcpus, expt_rt_cpus, expt_ord_cpus)
        if shared_vcpu:
            vm_host = nova_helper.get_vm_host(vm_id)
            assert vm_host in hosts_with_shared_cpu
