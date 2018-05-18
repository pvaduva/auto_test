###############################################################
# Intended for check functions for test result verifications
# assert is used to fail the check
# LOG.tc_step is used log the info
# Should be called by test function directly
###############################################################
import re
import time
import copy
from pytest import skip

from utils.tis_log import LOG
from consts.cgcs import MELLANOX_DEVICE, GuestImages, EventLogID
from consts.reasons import SkipStorageSpace
from testfixtures.fixture_resources import ResourceCleanup
from keywords import host_helper, system_helper, vm_helper, nova_helper, network_helper, common, cinder_helper, \
    glance_helper, storage_helper

SEP = '\n------------------------------------ '


def check_host_vswitch_port_engine_map(host, con_ssh=None):

    with host_helper.ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        expt_vswitch_map = host_helper.get_expected_vswitch_port_engine_map(host_ssh)
        actual_vswitch_map = host_helper.get_vswitch_port_engine_map(host_ssh)

    data_ports = system_helper.get_host_ports_for_net_type(host, net_type='data', rtn_list=True)
    all_ports_used = system_helper.get_host_ports_for_net_type(host, net_type=None, rtn_list=True)

    ports_dict = system_helper.get_host_ports_values(host, ['device type', 'name'], if_name=data_ports, strict=True)

    extra_mt_ports = 0
    for i in range(len(ports_dict['device type'])):
        device_type = ports_dict['device type'][i]
        if re.search(MELLANOX_DEVICE, device_type):
            # Only +1 if the other port of MX-4 is not used. CGTS-8303
            port_name = ports_dict['name'][i]
            dev = port_name[-1]
            other_dev = '0' if dev == '1' else '1'
            other_port = port_name[:-1] + other_dev
            if other_port not in all_ports_used:
                extra_mt_ports += 1

    if extra_mt_ports > 0:
        LOG.info("{}Mellanox devices are used on {} data interfaces. Perform loose check on port-engine map.".
                 format(SEP, host))
        # check actual mapping has x more items than expected mapping. x is the number of MT pci device
        assert len(expt_vswitch_map) + extra_mt_ports == len(actual_vswitch_map)

        # check expected mapping is a subset of actual mapping
        for port, engines in expt_vswitch_map.items():
            assert port in actual_vswitch_map, "port {} is not included in vswitch.ini on {}. Actual vSwitch map: {}".\
                format(port, host, actual_vswitch_map)
            assert engines == actual_vswitch_map[port], 'engine list for port {} on {} is not as expected. ' \
                'Expected engines: {}; Actual engines: {}'.format(host, port, engines, actual_vswitch_map[port])

    else:
        LOG.info("{}No extra Mellanox device used on {} data interfaces. Perform strict check on port-engine map.".
                 format(SEP, host))

        assert expt_vswitch_map == actual_vswitch_map, "vSwitch mapping unexpected. Expect: {}; Actual: {}".format(
                expt_vswitch_map, actual_vswitch_map)


def check_topology_of_vm(vm_id, vcpus, prev_total_cpus, numa_num=None, vm_host=None, cpu_pol=None, cpu_thr_pol=None,
                         expt_increase=None, min_vcpus=None, current_vcpus=None, prev_siblings=None, con_ssh=None,
                         guest=None):
    """
    Check vm has the correct topology based on the number of vcpus, cpu policy, cpu threads policy, number of numa nodes

    Check is done via vm-topology, nova host-describe, virsh vcpupin (on vm host), nova-compute.log (on vm host),
    /sys/devices/system/cpu/<cpu#>/topology/thread_siblings_list (on vm)

    Args:
        vm_id (str):
        vcpus (int): number of vcpus specified in flavor
        prev_total_cpus (float): such as 37.0000,  37.0625
        numa_num (int): number of numa nodes vm vcpus are on. Default is 1 if unset in flavor.
        vm_host (str):
        cpu_pol (str): dedicated or shared
        cpu_thr_pol (str): isolate, require, or prefer
        expt_increase (int): expected total vcpu increase on vm host compared to prev_total_cpus
        prev_siblings (list): list of siblings total. Usually used when checking vm topology after live migration
        con_ssh (SSHClient)

    """
    cpu_pol = cpu_pol if cpu_pol else 'shared'
    min_vcpus = vcpus if min_vcpus is None else min_vcpus
    current_vcpus = vcpus if current_vcpus is None else current_vcpus
    max_vcpus = vcpus

    actual_vcpus = eval(nova_helper.get_vm_nova_show_value(vm_id=vm_id, field='wrs-res:vcpus', con_ssh=con_ssh))
    expt_vcpus_all = [min_vcpus, current_vcpus, max_vcpus]
    assert expt_vcpus_all == actual_vcpus, "Actual min/current/max vcpus in nova show: {}; Expected: {}".\
        format(actual_vcpus, expt_vcpus_all)

    if vm_host is None:
        vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

    log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host, con_ssh=con_ssh)

    if numa_num is None:
        numa_num = 1

    is_ht_host = system_helper.is_hyperthreading_enabled(vm_host)

    if expt_increase is None:
        if cpu_pol == 'dedicated':
            expt_increase = vcpus * 2 if (cpu_thr_pol == 'isolate' and is_ht_host) else vcpus
        else:
            expt_increase = vcpus / 16

    LOG.info("{}Check total vcpus for vm host is increased by {} via nova host-describe".format(SEP, expt_increase))
    expt_used_cpus = round(prev_total_cpus + expt_increase, 4)
    end_time = time.time() + 60
    while time.time() < end_time:
        post_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')
        if expt_used_cpus == post_hosts_cpus[vm_host]:
            break

    else:
        post_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')
        assert expt_used_cpus == post_hosts_cpus[vm_host], "Used vcpus on host {} is not as expected. " \
            "Expected: {}; Actual: {}".format(vm_host, expt_used_cpus, post_hosts_cpus[vm_host])

    LOG.tc_step('Check vm topology, vcpus, pcpus, siblings, cpu policy, cpu threads policy, via vm-topology and nova '
                'show')
    pcpus_total, siblings_total = _check_vm_topology_via_vm_topology(
            vm_id, vcpus=vcpus, cpu_pol=cpu_pol, cpu_thr_pol=cpu_thr_pol, vm_host=vm_host,
            numa_num=numa_num, con_ssh=con_ssh, host_log_core_siblings=log_cores_siblings, is_ht=is_ht_host,
            current_vcpus=current_vcpus)

    LOG.info("{}Check vm vcpus, pcpus on vm host via nova-compute.log and virsh vcpupin".format(SEP))
    # Note: floating vm pcpus will not be checked via virsh vcpupin
    _check_vm_topology_on_host(vm_id, vcpus=vcpus, vm_pcpus=pcpus_total, prev_total_cpus=prev_total_cpus,
                               expt_increase=expt_increase, vm_host=vm_host, cpu_pol=cpu_pol, cpu_thr_pol=cpu_thr_pol,
                               host_log_core_siblings=log_cores_siblings)

    LOG.info("{}Check vm vcpus, siblings on vm via /sys/devices/system/cpu/<cpu>/topology/thread_siblings_list".
             format(SEP))
    _check_vm_topology_on_vm(vm_id, vcpus=vcpus, siblings_total=siblings_total, current_vcpus=current_vcpus,
                             prev_siblings=prev_siblings, guest=guest)

    return pcpus_total, siblings_total


def _check_vm_topology_via_vm_topology(vm_id, vcpus, cpu_pol, cpu_thr_pol, numa_num, vm_host,
                                       host_log_core_siblings=None, is_ht=None, current_vcpus=None,
                                       vcpus_on_numa=None, con_ssh=None):
    """

    Args:
        vm_id:
        vcpus (int):
        cpu_pol (str|None):
        cpu_thr_pol (str|None):
        numa_num (int|None):
        vcpus_on_numa (dict): number of vcpus on each numa node. e.g., {0: 1, 1: 2}

    Returns (tuple): ([pcpus for vm], [siblings for vm])
        e.g., ([7,8,9,10,18,19], [[0,1,2], [3,4,5]])

    Examples (vm-topology servers nova view table):
        # require-4     | 4,4,4 |    512 | node:0,   512MB, pgsize:2M, 1s,2c,2t, vcpus:0-3, pcpus:25,5,8,28, siblings:{0,1},{2,3}, pol:ded, thr:req
        # isolate-5     | 5,5,5 |    512 | node:0,   512MB, pgsize:2M, 1s,5c,1t, vcpus:0-4, pcpus:9,24,27,3,26, pol:ded, thr:iso
        # dedicated-3   | 3,3,3 |    512 | node:1,   512MB, pgsize:2M, 1s,1c,3t, vcpus:0-2, pcpus:35,15,10, siblings:{0-2}, pol:ded, thr:no
        # float-5       | 5,5,5 |    512 | node:0,   512MB, pgsize:2M, vcpus:0-4, pol:sha
        # ded-2numa-6   | 6,6,6 |    512 | node:0,   256MB, pgsize:2M, 1s,1c,3t, vcpus:0-2, pcpus:3-5, siblings:{0-2}, pol:ded, thr:no |
        #                                  node:1,   256MB, pgsize:2M, 1s,1c,3t, vcpus:3-5, pcpus:10-12, siblings:{3-5}, pol:ded, thr:no
        # float-2numa-4 | 4,4,4 |    512 | node:0,   256MB, pgsize:2M, vcpus:0,1, pol:sha
        #                                  node:1,   256MB, pgsize:2M, vcpus:2,3, pol:sha
    """
    current_vcpus = vcpus if current_vcpus is None else current_vcpus
    max_vcpus = vcpus

    if is_ht is None:
        is_ht = system_helper.is_hyperthreading_enabled(vm_host)

    if not host_log_core_siblings:
        host_log_core_siblings = host_helper.get_logcore_siblings(host=vm_host, con_ssh=con_ssh)

    expt_cpu_pol = 'sha' if cpu_pol is None or 'sha' in cpu_pol else 'ded'
    instance_topology = vm_helper.get_instance_topology(vm_id, con_ssh=con_ssh)
    instance_topology_nova_show = vm_helper.get_instance_topology(vm_id, con_ssh=con_ssh, source='nova show')

    LOG.info("\n---------------------------------------- "
             "Check instance topology in vm-topology and nova show are identical")
    for i in range(len(instance_topology)):
        for key in instance_topology[i]:
            assert instance_topology[i][key] == instance_topology_nova_show[i][key], "vm {} {} on numa node {} is " \
                "different in vm-topology than nova show".format(vm_id, key, i)

    pcpus_total = []
    siblings_total = []
    shared_pcpu_total = 0

    if not vcpus_on_numa:
        vcpus_on_numa = {}
        vcpus_per_numa_const = int(vcpus / numa_num)
        for topology_on_numa_node_ in instance_topology:
            node = topology_on_numa_node_['node']
            vcpus_on_numa[node] = vcpus_per_numa_const

    # numa_nodes = []
    for topology_on_numa_node in instance_topology:  # Cannot be on two numa nodes for dedicated vm unless specified
        # numa_nodes.append(topology_on_numa_node['node'])
        actual_vcpus = topology_on_numa_node['vcpus']
        node_id = topology_on_numa_node['node']
        vcpus_per_numa = vcpus_on_numa[node_id]

        shared_pcpu = topology_on_numa_node['shared_pcpu']
        shared_pcpu_num = 0 if shared_pcpu is None else 1
        shared_pcpu_total += shared_pcpu_num

        assert expt_cpu_pol == topology_on_numa_node['pol'], "CPU policy is {} instead of {} in vm-topology".\
            format(topology_on_numa_node['pol'], expt_cpu_pol)
        assert vcpus_per_numa == len(actual_vcpus) + shared_pcpu_num, 'vm vcpus number on numa node {} is {} ' \
            'instead of {}'.format(node_id, len(actual_vcpus), vcpus_per_numa)

        actual_siblings = topology_on_numa_node['siblings']
        actual_topology = topology_on_numa_node['topology']
        actual_pcpus = topology_on_numa_node['pcpus']
        if actual_pcpus:
            actual_pcpus = sorted(actual_pcpus)
        actual_thread_policy = topology_on_numa_node['thr']

        if expt_cpu_pol == 'sha':
            # node:0,   512MB, pgsize:2M, vcpus:0-4, pol:sha
            assert topology_on_numa_node['thr'] is None, "cpu thread policy should not be included for floating vm"
            assert actual_siblings is None, 'siblings should not be included for floating vm'
            assert actual_topology is None, 'topology should not be included for floating vm'
            assert actual_pcpus is None, "pcpu should not be included in vm-topology for floating vm"
            assert actual_thread_policy is None, "cpu thread pol should not be included in vm-topology for floating vm"

        else:
            assert actual_pcpus, "pcpus is not included in vm-topology for dedicated vm"
            # comment out topology and sibling checks until Jim Gauld decides on a consistent vm topology
            # TODO assert actual_topology, "vm topology is not included in vm-topology for dedicated vm"
            if not cpu_thr_pol:
                cpu_thr_pol = 'prefer'

            # if cpu_thr_pol:
            #     # FIXME: assumption invalid. isolate will not require ht_host
                # Assumption: hyper-threading must be enabled if vm launched successfully. And thread number is 2.
            assert actual_thread_policy in cpu_thr_pol, 'cpu thread policy in vm topology is {} while expected ' \
                                                        'spec is {}'.format(actual_thread_policy, cpu_thr_pol)

            if cpu_thr_pol == 'isolate':
                # isolate-5: node:0, 512MB, pgsize:2M, 1s,5c,1t, vcpus:0-4, pcpus:9,24,27,3,26, pol:ded, thr:iso
                assert not actual_siblings, "siblings should not be included for isolate thread policy"
                assert '{}c,1t'.format(vcpus_per_numa) in actual_topology
                expt_core_len_in_pair = 1

            elif cpu_thr_pol == 'require':
                # require-4: node:0, 512MB, pgsize:2M, 1s,2c,2t, vcpus:0-3, pcpus:25,5,8,28, siblings:{0,1},{2,3}, pol:ded, thr:req
                if len(actual_pcpus) % 2 == 0:
                    assert actual_siblings, "siblings should be included for dedicated vm"
                    # 2 is the host thread number
                    assert '{}c,2t'.format(int(vcpus_per_numa / 2)) in actual_topology, \
                        "Expected topology: {}c,2t; Actual: {}".format(int(vcpus_per_numa / 2), actual_topology)
                else:
                    assert not actual_siblings, "siblings should not be included for require vm with odd number vcpus"
                    assert '{}c,1t'.format(len(actual_pcpus)) in actual_topology, \
                        "Expected topology: {}c,1t; Actual: {}".format(len(actual_pcpus), actual_topology)

                expt_core_len_in_pair = 2
                # siblings_total += actual_siblings

            elif cpu_thr_pol == 'prefer':
                assert vcpus_per_numa == len(actual_pcpus) + shared_pcpu_num, \
                    "vm pcpus number per numa node is {} instead of {}".format(
                        len(actual_pcpus), vcpus_per_numa)
                if is_ht:
                    # Those checks are not guaranteed if vm is migrated from non-HT host to HT host
                    expt_core_len_in_pair = 2
                    if len(actual_pcpus) % 2 == 0:
                        assert '{}c,2t'.format(int(vcpus_per_numa / 2)) in actual_topology, \
                            "Expected topology: {}c,2t; Actual: {}".format(int(vcpus_per_numa / 2), actual_topology)
                        assert actual_siblings, "siblings should be included for prefer vm with even number vcpus " \
                                                "on HT host"
                    else:
                        assert not actual_siblings, "siblings should not be included for prefer vm with odd number vcpu"
                        assert '{}c,1t'.format(len(actual_pcpus)) in actual_topology, \
                            "Expected topology: {}c,1t; Actual: {}".format(len(actual_pcpus), actual_topology)
                else:
                    expt_core_len_in_pair = 1
                    # Live migrate between ht host and non-ht host would not change vm siblings, so don't check siblings
                    # TODO assert not actual_siblings, "siblings should not be included for prefer vm with non-HT host"

            else:
                raise NotImplemented("New cpu threads policy added? Update automation code.")

            # Don't check siblings for prefer as it changes after vcpu scaling
            if cpu_thr_pol == 'require' and len(actual_pcpus) % 2 == 1:

                count = 0
                for pair in host_log_core_siblings:
                    num_cpu_in_pair = len(set(pair) & set(actual_pcpus))
                    if num_cpu_in_pair == 1:
                        count += 1

                assert count <= 1, "More than 1 pcpu for {} vm does not have sibling vcpu assigned. " \
                                   "VM pcpus: {}. Host sibling pairs: {}".format(cpu_thr_pol, actual_pcpus,
                                                                                 host_log_core_siblings)
            elif cpu_thr_pol in ['require', 'isolate']:
                for pair in host_log_core_siblings:
                    assert len(set(pair) & set(actual_pcpus)) in [0, expt_core_len_in_pair], \
                        "Host sibling pair: {}, VM pcpus:{}. Expected cores per pair: {}".format(
                        pair, actual_pcpus, expt_core_len_in_pair)

            pcpus_total += actual_pcpus

            if actual_siblings:
                siblings_total += actual_siblings

    if pcpus_total:
        assert max_vcpus == len(pcpus_total) + shared_pcpu_total, \
            "Max vcpus: {}, pcpus list: {}".format(max_vcpus, pcpus_total)

        # if it can scale (current!= max), then shared_pcpu must be 0
        assert current_vcpus == len(set(pcpus_total)) + shared_pcpu_total, \
            "Current vcpus: {}, pcpus: {}".format(max_vcpus, pcpus_total)

    if not siblings_total:
        siblings_total = [[vcpu_] for vcpu_ in range(current_vcpus)]

    LOG.info("vm {} on {} - pcpus total: {}; siblings total: {}".format(vm_id, vm_host, pcpus_total, siblings_total))
    return pcpus_total, siblings_total


def _check_vm_topology_on_host(vm_id, vcpus, vm_pcpus, expt_increase, prev_total_cpus, vm_host, cpu_pol, cpu_thr_pol,
                               host_log_core_siblings):

    # Check host side info such as nova-compute.log and virsh pcpupin
    LOG.tc_step('Check vm topology from vm_host via: nova-compute.log, virsh vcpupin, taskset')
    instance_name = nova_helper.get_vm_instance_name(vm_id)
    procs = host_helper.get_host_procs(hostname=vm_host)
    # numa_nodes = list(range(len(procs)))
    vm_host_, numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
    assert vm_host == vm_host_, "VM is on {} instead of {}".format(vm_host_, vm_host)
    with host_helper.ssh_to_host(vm_host) as host_ssh:

        LOG.info("{}Check total allocated vcpus increased by {} from nova-compute.log on host".
                 format(SEP, expt_increase))
        post_total_log = host_helper.wait_for_total_allocated_vcpus_update_in_log(host_ssh, prev_cpus=prev_total_cpus,
                                                                                  fail_ok=True)
        expt_total = round(prev_total_cpus + expt_increase, 4)
        assert expt_total == post_total_log, 'vcpus increase in nova-compute.log is not as expected. ' \
                                             'Expected: {}. Actual: {}'.format(expt_total, post_total_log)

        LOG.info("{}Check vcpus for vm via sudo virsh vcpupin".format(SEP))
        vcpus_for_vm = host_helper.get_vcpus_for_instance_via_virsh(host_ssh, instance_name=instance_name)
        assert vcpus == len(vcpus_for_vm), 'Actual vm cpus number - {} is not as expected - {} in sudo virsh vcpupin'\
            .format(len(vcpus_for_vm), vcpus)

        if vm_pcpus:
            all_cpus = []
            for cpus in vcpus_for_vm.values():
                all_cpus += cpus
            assert sorted(vm_pcpus) == sorted(all_cpus), 'pcpus from vm-topology - {} is different than ' \
                                                         'virsh vcpupin - {}'.format(sorted(vm_pcpus), sorted(all_cpus))
        else:
            LOG.warning('Skip pcpus check in virsh vcpupin for floating vm')

        LOG.info("{}Get cpu affinity list for vm via taskset -pc".format(SEP))
        affined_cpus = vm_helper.get_affined_cpus_for_vm(vm_id, host_ssh=host_ssh, vm_host=vm_host,
                                                         instance_name=instance_name)

        if 'ded' in cpu_pol:

            LOG.info("{}Check affined cpus for dedicated vm is the same as its pcpus shown in vm-topology".format(SEP))
            expt_affined_cpus = vm_pcpus

            assert len(affined_cpus) <= len(expt_affined_cpus) + 2
            # affined cpus was a single core. expected a core and its sibling
            assert set(expt_affined_cpus) <= set(affined_cpus)

        else:
            LOG.info("{}Check affined cpus for floating vm is the same as unpinned cpus on vm host".format(SEP))
            cpus_info = host_helper.get_vcpus_info_in_log(host_ssh=host_ssh, rtn_list=True, numa_nodes=numa_nodes)
            unpinned_cpus = []

            for item in cpus_info:
                unpinned_cpus_for_numa = item['unpinned_cpulist']
                unpinned_cpus += unpinned_cpus_for_numa
            unpinned_cpus = sorted(unpinned_cpus)

            err_msg = "Affined cpus for vm: {}, Unpinned cpus on vm host: {}".format(affined_cpus, unpinned_cpus)
            assert affined_cpus == unpinned_cpus, 'Affined cpus for floating vm are different than unpinned cpus ' \
                                                  'on vm host {} numa {}\n{}'.format(vm_host, numa_nodes, err_msg)


def _check_vm_topology_on_vm(vm_id, vcpus, siblings_total, current_vcpus, prev_siblings=None, guest=None):
    siblings_total_ = copy.deepcopy(siblings_total)
    # Check from vm in /proc/cpuinfo and /sys/devices/.../cpu#/topology/thread_siblings_list
    if not guest:
        guest = ''
    LOG.tc_step('Check vm topology from within the vm via: /sys/devices/system/cpu')
    actual_sibs = []
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:

        if 'win' in guest:
            LOG.info("{}Check windows guest cores via wmic cpu get cmds".format(SEP))
            offline_cores_count = 0
            log_cores_count, log_count_per_sibling = get_procs_and_siblings_on_windows(vm_ssh)
            online_cores_count = present_cores_count = log_cores_count
        else:
            LOG.info("{}Check vm present|online|offline cores from inside vm via /sys/devices/system/cpu/".format(SEP))
            present_cores, online_cores, offline_cores = vm_helper.get_proc_nums_from_vm(vm_ssh)
            present_cores_count = len(present_cores)
            online_cores_count = len(online_cores)
            offline_cores_count = len(offline_cores)

        assert vcpus == present_cores_count, "Number of vcpus: {}, present cores: {}".format(vcpus,
                                                                                             present_cores_count)
        assert current_vcpus == online_cores_count, \
            "Current vcpus for vm: {}, online cores: {}".format(current_vcpus, online_cores_count)

        expt_total_cores = online_cores_count + offline_cores_count
        assert expt_total_cores in [present_cores_count, 512], \
            "Number of present cores: {}. online+offline cores: {}".format(vcpus, expt_total_cores)

        if online_cores_count == present_cores_count:
            expt_sibs_list = [[vcpu] for vcpu in range(present_cores_count)] if not siblings_total_ \
                else siblings_total_

            expt_sibs_list = [sorted(expt_sibs_list)]
            if prev_siblings:
                # siblings_total may get modified here
                expt_sibs_list.append(sorted(prev_siblings))

            if 'win' in guest:
                LOG.info("{}Check windows guest siblings via wmic cpu get cmds".format(SEP))
                expt_cores_list = []
                for sib_list in expt_sibs_list:
                    expt_cores_per_sib = [len(vcpus) for vcpus in sib_list]
                    expt_cores_list.append(expt_cores_per_sib)
                assert log_count_per_sibling in expt_cores_list, \
                    "Expected log cores count per sibling: {}, actual: {}".\
                    format(expt_cores_per_sib, log_count_per_sibling)

            else:
                LOG.info("{}Check vm /sys/devices/system/cpu/[cpu#]/topology/thread_siblings_list".format(SEP))
                for cpu in ['cpu{}'.format(i) for i in range(online_cores_count)]:
                    actual_sibs_for_cpu = \
                    vm_ssh.exec_cmd('cat /sys/devices/system/cpu/{}/topology/thread_siblings_list'.
                                    format(cpu), fail_ok=False)[1]

                    sib_for_cpu = common.parse_cpus_list(actual_sibs_for_cpu)
                    if sib_for_cpu not in actual_sibs:
                        actual_sibs.append(sib_for_cpu)

                assert sorted(actual_sibs) in expt_sibs_list, "Expt sib lists: {}, actual sib list: {}".\
                    format(expt_sibs_list, sorted(actual_sibs))


def get_procs_and_siblings_on_windows(vm_ssh):
    cmd = 'wmic cpu get {}'

    procs = []
    for param in ['NumberOfCores', 'NumberOfLogicalProcessors']:
        output = vm_ssh.exec_cmd(cmd.format(param), fail_ok=False)[1].strip()
        num_per_proc = [int(line.strip()) for line in output.splitlines() if line.strip()
                        and not re.search('{}|x'.format(param), line)]
        procs.append(num_per_proc)
    procs = zip(procs[0], procs[1])
    log_procs_per_phy = [nums[0] * nums[1] for nums in procs]
    total_log_procs = sum(log_procs_per_phy)

    LOG.info("Windows guest total logical cores: {}, logical_cores_per_phy_core: {}".
             format(total_log_procs, log_procs_per_phy))
    return total_log_procs, log_procs_per_phy


def check_vm_vcpus_via_nova_show(vm_id, min_cpu, current_cpu, max_cpu, con_ssh=None):
    actual_vcpus = eval(nova_helper.get_vm_nova_show_value(vm_id=vm_id, field='wrs-res:vcpus', con_ssh=con_ssh))
    assert [min_cpu, current_cpu, max_cpu] == actual_vcpus, "vcpus in nova show {} is not as expected".format(vm_id)


def check_vm_numa_nodes(vm_id, on_vswitch_nodes=True):
    vm_host, vm_numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
    vswitch_cores_dict = host_helper.get_host_cpu_cores_for_function(vm_host, function='vSwitch')
    vswitch_procs = [proc for proc in vswitch_cores_dict if vswitch_cores_dict[proc]]

    if on_vswitch_nodes:
        assert set(vm_numa_nodes) <= set(vswitch_procs), "VM {} is on numa nodes {} instead of vswitch numa nodes {}" \
                                                         "".format(vm_id, vm_numa_nodes, vswitch_procs)
    else:
        assert not (set(vm_numa_nodes) & set(vswitch_procs)), "VM {} is on vswitch numa node(s). VM numa nodes: {}, " \
                                                              "vSwitch numa nodes: {}" .format(vm_id, vm_numa_nodes,
                                                                                               vswitch_procs)


def check_vm_pci_addr(vm_id, vm_nics):
    """
    Check vm pci addresses are as configured via nova show and from vm
    Args:
        vm_id (str):
        vm_nics (list): nics passed to nova boot cli

    Returns:

    """
    nova_show_nics = _check_vm_pci_addr_via_nova_show(vm_id, vm_nics)
    _check_vm_pci_addr_on_vm(vm_id, nova_show_nics)


def _check_vm_pci_addr_via_nova_show(vm_id, vm_nics):
    """
    Check vm pci address via nova show
    Args:
        vm_id (str):
        vm_nics (list): nics passed to nova boot cli

    Returns (list): nova show nics

    """
    LOG.info("Check vm pci address in nova show is as configured in nova boot")
    nova_show_nics = nova_helper.get_vm_interfaces_info(vm_id)
    for i in range(len(vm_nics)):
        boot_vm_nic = vm_nics[i]
        nova_show_nic = nova_show_nics[i]
        expt_pci_addr = boot_vm_nic.get('vif-pci-address', '')
        actual_pci_addr = nova_show_nic.get('vif_pci_address', '')
        assert expt_pci_addr == actual_pci_addr, "Assigned pci address {} is not in nova show nic: {}".\
            format(expt_pci_addr, actual_pci_addr)

    return nova_show_nics


def _check_vm_pci_addr_on_vm(vm_id, nova_show_nics=None):
    LOG.info("Check vm PCI address is as configured from vm via ethtool")
    if not nova_show_nics:
        nova_show_nics = nova_helper.get_vm_interfaces_info(vm_id)

    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        for nic_ in nova_show_nics:
            pci_addr = nic_.get('vif_pci_address')
            if pci_addr:
                mac_addr = nic_['mac_address']
                eth_name = network_helper.get_eth_for_mac(mac_addr=mac_addr, ssh_client=vm_ssh)
                code, output = vm_ssh.exec_cmd('ethtool -i {} | grep bus-info'.
                                               format(eth_name), fail_ok=False)
                assert pci_addr in output, "Assigned pci address does not match pci info for vm {}. Assigned: {}; " \
                                           "Actual: {}".format(eth_name, pci_addr, output)


def check_fs_sufficient(guest_os, boot_source='volume'):
    """
    Check if volume pool, image storage, and/or image conversion space is sufficient to launch vm
    Args:
        guest_os (str): e.g., tis-centos-guest, win_2016
        boot_source (str): volume or image

    Returns (str): image id

    """
    LOG.info("Check if storage fs is sufficient to launch boot-from-{} vm with {}".format(boot_source, guest_os))
    if guest_os in ['opensuse_12', 'win_2016'] and boot_source == 'volume':
        if not cinder_helper.is_volumes_pool_sufficient(min_size=35):
            skip(SkipStorageSpace.SMALL_CINDER_VOLUMES_POOL)

    if guest_os == 'win_2016' and boot_source == 'volume':
        if not glance_helper.is_image_conversion_sufficient(guest_os=guest_os):
            skip(SkipStorageSpace.INSUFFICIENT_IMG_CONV.format(guest_os))

    LOG.tc_step("Get/Create {} image".format(guest_os))
    check_disk = True if 'win' in guest_os else False
    img_id = glance_helper.get_guest_image(guest_os, check_disk=check_disk)
    if not re.search('ubuntu_14|{}'.format(GuestImages.TIS_GUEST_PATTERN), guest_os):
        ResourceCleanup.add('image', img_id)


def check_vm_files(vm_id, storage_backing, ephemeral, swap, vm_type, file_paths, content, root=None, vm_action=None,
                   prev_host=None, post_host=None, disks=None, post_disks=None, guest_os=None,
                   check_volume_root=False):
    """
    Check the files on vm after specified action. This is to check the disks in the basic nova matrix table.
    Args:
        vm_id (str):
        storage_backing (str): local_image, local_lvm, or remote
        root (int): root disk size in flavor. e.g., 2, 5
        ephemeral (int): e.g., 0, 1
        swap (int): e.g., 0, 512
        vm_type (str): image, volume, image_with_vol, vol_with_vol
        file_paths (list): list of file paths to check
        content (str): content of the files (assume all files have the same content)
        vm_action (str|None): live_migrate, cold_migrate, resize, evacuate, None (expect no data loss)
        prev_host (None|str): vm host prior to vm_action. This is used to check if vm host has changed when needed.
        post_host (None|str): vm host after vm_action.
        disks (dict): disks that are returned from vm_helper.get_vm_devices_via_virsh()
        post_disks (dict): only used in resize case
        guest_os (str|None): default guest assumed for None. e,g., ubuntu_16
        check_volume_root (bool): whether to check root disk size even if vm is booted from image

    Returns:

    """
    final_disks = post_disks if post_disks else disks
    final_paths = list(file_paths)
    if not disks:
        disks = vm_helper.get_vm_devices_via_virsh(vm_id=vm_id)

    eph_disk = disks.get('eph', {})
    if not eph_disk:
        if post_disks:
            eph_disk = post_disks.get('eph', {})
    swap_disk = disks.get('swap', {})
    if not swap_disk:
        if post_disks:
            swap_disk = post_disks.get('swap', {})

    disk_check = 'no_loss'
    if vm_action in [None, 'live_migrate']:
        disk_check = 'no_loss'
    elif vm_type == 'volume':
        # boot-from-vol, non-live migrate actions
        disk_check = 'no_loss'
        if storage_backing == 'local_lvm' and (eph_disk or swap_disk):
            disk_check = 'eph_swap_loss'
        elif storage_backing == 'local_image' and vm_action == 'evacuate' and (eph_disk or swap_disk):
            disk_check = 'eph_swap_loss'
    elif storage_backing == 'local_image':
        # local_image, boot-from-image, non-live migrate actions
        disk_check = 'no_loss'
        if vm_action == 'evacuate':
            disk_check = 'local_loss'
    elif storage_backing == 'local_lvm':
        # local_lvm, boot-from-image, non-live migrate actions
        disk_check = 'local_loss'
        if vm_action == 'resize':
            post_host = post_host if post_host else nova_helper.get_vm_host(vm_id)
            if post_host == prev_host:
                disk_check = 'eph_swap_loss'

    LOG.info("disk check type: {}".format(disk_check))
    loss_paths = []
    # if post_disks and post_disks != disks:
    #     post_swaps = post_disks.get('swap', {})
    #     pre_swaps = disks.get('swap', {})
    #     # Don't check swap disk if it was removed in resize
    #     for swap in pre_swaps:
    #         if swap not in post_swaps:
    #             for path in file_paths:
    #                 if swap in path:
    #                     final_paths.remove(path)

    if disk_check == 'no_loss':
        no_loss_paths = final_paths
    else:
        # If there's any loss, we must not have remote storage. And any ephemeral/swap disks will be local.
        disks_to_check = disks.get('eph', {})
        # skip swap type checking for data loss since it's not a regular filesystem
        # swap_disks = disks.get('swap', {})
        # disks_to_check.update(swap_disks)

        for path_ in final_paths:
            # For tis-centos-guest, ephemeral disk is mounted to /mnt after vm launch.
            if str(path_).rsplit('/', 1)[0] == '/mnt':
                loss_paths.append(path_)
                break

        for disk in disks_to_check:
            for path in final_paths:
                if disk in path:
                    # We mount disk vdb to /mnt/vdb, so this is looking for vdb in the mount path
                    loss_paths.append(path)
                    break

        if disk_check == 'local_loss':
            # if vm booted from image, then the root disk is also local disk
            root_img = disks.get('root_img', {})
            if root_img:
                LOG.info("Auto mount vm disks again since root disk was local with data loss expected")
                vm_helper.auto_mount_vm_disks(vm_id=vm_id, disks=final_disks)
                file_name = final_paths[0].rsplit('/')[-1]
                root_path = '/{}'.format(file_name)
                loss_paths.append(root_path)
                assert root_path in final_paths, "root_path:{}, file_paths:{}".format(root_path, final_paths)

        no_loss_paths = list(set(final_paths) - set(loss_paths))

    LOG.info("loss_paths: {}, no_loss_paths: {}, total_file_pahts: {}".format(loss_paths, no_loss_paths, final_paths))
    res_files = {}
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id, vm_image_name=guest_os) as vm_ssh:

        for file_path in loss_paths:
            vm_ssh.exec_sudo_cmd('touch {}2'.format(file_path), fail_ok=False)
            vm_ssh.exec_sudo_cmd('echo "{}" >> {}2'.format(content, file_path), fail_ok=False)

        for file_path in no_loss_paths:
            output = vm_ssh.exec_sudo_cmd('cat {}'.format(file_path), fail_ok=False)[1]
            res = '' if content in output else 'content mismatch'
            res_files[file_path] = res

        for file, error in res_files.items():
            assert not error, "Check {} failed: {}".format(file, error)

        swap_disk = final_disks.get('swap', {})
        if swap_disk:
            disk_name = list(swap_disk.keys())[0]
            partition = '/dev/{}'.format(disk_name)
            if disk_check != 'local_loss' and not disks.get('swap', {}):
                mount_on, fs_type = storage_helper.mount_partition(ssh_client=vm_ssh, disk=disk_name,
                                                                   partition=partition, fs_type='swap')
                storage_helper.auto_mount_fs(ssh_client=vm_ssh, fs=partition, mount_on=mount_on, fs_type=fs_type)

            LOG.info("Check swap disk is on")
            swap_output = vm_ssh.exec_sudo_cmd('cat /proc/swaps | grep --color=never {}'.format(partition))[1]
            assert swap_output, "Expect swapon for {}. Actual output: {}".\
                format(partition, vm_ssh.exec_sudo_cmd('cat /proc/swaps')[1])

            LOG.info("Check swap disk size")
            _check_disk_size(vm_ssh, disk_name=disk_name, expt_size=swap)

        eph_disk = final_disks.get('eph', {})
        if eph_disk:
            LOG.info("Check ephemeral disk size")
            eph_name = list(eph_disk.keys())[0]
            _check_disk_size(vm_ssh, eph_name, expt_size=ephemeral*1024)

        if root:
            image_root = final_disks.get('root_img', {})
            root_name = ''
            if image_root:
                root_name = list(image_root.keys())[0]
            elif check_volume_root:
                root_name = list(final_disks.get('root_vol').keys())[0]

            if root_name:
                LOG.info("Check root disk size")
                _check_disk_size(vm_ssh, disk_name=root_name, expt_size=root*1024)


def _check_disk_size(vm_ssh, disk_name, expt_size):
    partition = vm_ssh.exec_sudo_cmd('cat /proc/partitions | grep --color=never "{}$"'.format(disk_name))[1]
    actual_size = int(int(partition.split()[-2].strip())/1024) if partition else 0
    expt_size = int(expt_size)
    assert actual_size == expt_size, "Expected disk size: {}M. Actual: {}M".format(expt_size, actual_size)


def check_alarms(before_alarms, timeout=300):
    after_alarms = system_helper.get_alarms()
    new_alarms = []
    check_interval = 5
    schedule_conn_test = False
    for item in after_alarms:
        if item not in before_alarms:
            alarm_id, entity_id = item.split('::::')
            if alarm_id == EventLogID.PROVIDER_NETWORK_FAILURE:
                # Providernet connectivity alarm handling
                schedule_conn_test = True
            elif alarm_id == EventLogID.CPU_USAGE_HIGH:
                check_interval = 45
            elif alarm_id == EventLogID.NTP_ALARM:
                # NTP alarm handling
                LOG.info("NTP alarm found, checking ntpq stats")
                host = entity_id.split('host=')[1].split('.ntp')[0]
                host_helper.wait_for_ntp_sync(host=host, fail_ok=False)
                continue

            new_alarms.append((alarm_id, entity_id))

    if schedule_conn_test:
        LOG.info("Providernet connectivity alarm found, schedule providernet connectivity test")
        network_helper.schedule_providernet_connectivity_test()

    if new_alarms:
        LOG.info("New alarms detected. Waiting for new alarms to clear.")
        res, remaining_alarms = system_helper.wait_for_alarms_gone(new_alarms, fail_ok=True, timeout=timeout,
                                                                   check_interval=check_interval)
        assert res, "New alarm(s) found and did not clear within {} seconds. " \
                    "Alarm IDs and Entity IDs: {}".format(timeout, remaining_alarms)


def check_qat_service(vm_id, qat_devs, run_cpa=True, timeout=600):
    """
    Check qat device and service on given vm
    Args:
        vm_id (str):
        qat_devs (dict): {<qat-dev1-name>: <number1>, <qat-dev2-name>: <number2>}
            e.g., {'Intel Corporation DH895XCC Series QAT Virtual Function [8086:0443]' : 32}
        run_cpa (bool): whether to run cpa_sample_code in guest, it could take long time when there are many qat-vfs
        timeout (int): timeout value to wait for cpa_sample_code to finish

    Returns:

    """
    if qat_devs:
        LOG.tc_step("Check qat-vfs on vm {}".format(vm_id))
    else:
        LOG.tc_step("Check no qat device exist on vm {}".format(vm_id))
    with vm_helper.ssh_to_vm_from_natbox(vm_id=vm_id) as vm_ssh:
        code, output = vm_ssh.exec_sudo_cmd('lspci -nn | grep --color=never QAT', fail_ok=True)
        if not qat_devs:
            assert 1 == code
            return

        assert 0 == code, "No QAT device exists on vm {}".format(vm_id)
        for dev, expt_count in qat_devs.items():
            actual_count = 0
            for line in output.splitlines():
                if dev in line:
                    actual_count += 1
            assert expt_count == actual_count, "qat device count for {} is {} while expecting {}".format(
                    dev, actual_count, expt_count)

        check_status_cmd = "systemctl status qat_service | grep '' --color=never"
        status = vm_ssh.exec_sudo_cmd(check_status_cmd)[1]
        active_str = 'Active: active'
        if active_str not in status:
            LOG.info("Start qat service")
            vm_ssh.exec_sudo_cmd('systemctl start qat_service', fail_ok=False)
            status = vm_ssh.exec_sudo_cmd(check_status_cmd, fail_ok=False)[1]
            assert active_str in status, "qat_service is not in active state"

        if run_cpa:
            LOG.info("Run cpa_sample_code on quickAssist hardware")
            output = vm_ssh.exec_sudo_cmd('cpa_sample_code signOfLife=1', fail_ok=False, expect_timeout=timeout)[1]
            assert 'error' not in output.lower(), "cpa_sample_code test failed"
            LOG.info("cpa_sample_code test completed successfully")
