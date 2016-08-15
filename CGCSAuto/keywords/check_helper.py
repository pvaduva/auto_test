###############################################################
# Intended for check functions for test result verifications
# assert is used to fail the check
# LOG.tc_step is used log the info
# Should be called by test function directly
###############################################################

import time

from datetime import datetime
from utils.tis_log import LOG
from keywords import host_helper, system_helper, vm_helper, nova_helper, common


def check_host_vswitch_port_engine_map(host, con_ssh=None):

    with host_helper.ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        expt_vswitch_map = host_helper.get_expected_vswitch_port_engine_map(host_ssh)
        actual_vswitch_map = host_helper.get_vswitch_port_engine_map(host_ssh)

    data_ports = system_helper.get_host_ports_for_net_type(host, net_type='data', rtn_list=True)

    device_types = system_helper.get_host_ports_info(host, 'device type', if_name=data_ports, strict=True)
    extra_mt_ports = 0
    for device_type in device_types:
        if 'MT27500' in device_type:
            extra_mt_ports += 1

    if extra_mt_ports > 0:
        LOG.tc_step("Mellanox devices are used on {} data interfaces. Perform loose check on port-engine map.".
                    format(host))
        # check actual mapping has x more items than expected mapping. x is the number of MT pci device
        assert len(expt_vswitch_map) + extra_mt_ports == len(actual_vswitch_map)

        # check expected mapping is a subset of actual mapping
        for port, engines in expt_vswitch_map.items():
            assert port in actual_vswitch_map, "port {} is not included in vswitch.ini on {}. Actual vSwitch map: {}".\
                format(port, host, actual_vswitch_map)
            assert engines == actual_vswitch_map[port], 'engine list for port {} on {} is not as expected. ' \
                'Expected engines: {}; Actual engines: {}'.format(host, port, engines, actual_vswitch_map[port])

    else:
        LOG.tc_step("No Mellanox device used on {} data interfaces. Perform strict check on port-engine map.".
                    format(host))

        assert expt_vswitch_map == actual_vswitch_map, "vSwitch mapping unexpected. Expect: {}; Actual: {}".format(
                expt_vswitch_map, actual_vswitch_map)


def check_topology_of_vm(vm_id, vcpus, prev_total_cpus, numa_num=None, vm_host=None, cpu_pol=None, cpu_thr_pol=None,
                         expt_increase=None, con_ssh=None):
    """
    Check vm has the correct topology based on the number of vcpus, cpu policy, cpu threads policy, number of numa nodes

    Check is done via vm-topology, nova host-describe, virsh vcpupin (on vm host), nova-compute.log (on vm host),
    /sys/devices/system/cpu/<cpu#>/topology/core_siblings_list/core_siblings_list (on vm)

    Args:
        vm_id (str):
        vcpus (int): number of vcpus specified in flavor
        prev_total_cpus (float): such as 37.0000,  37.0625
        numa_num (int): number of numa nodes vm vcpus are on. Default is 1 if unset in flavor.
        vm_host (str):
        cpu_pol (str): dedicated or shared
        cpu_thr_pol (str): isolate or require
        expt_increase (int): expected total vcpu increase on vm host compared to prev_total_cpus
        con_ssh (SSHClient)

    """
    cpu_pol = cpu_pol if cpu_pol else 'shared'
    log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host, con_ssh=con_ssh)

    if vm_host is None:
        vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

    if numa_num is None:
        numa_num = 1

    if expt_increase is None:
        if cpu_pol == 'dedicated':
            expt_increase = vcpus * 2 if cpu_thr_pol == 'isolate' else vcpus
        else:
            expt_increase = vcpus / 16

    LOG.tc_step("Check total vcpus for vm host is increased by {} via nova host-describe".format(expt_increase))
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
            numa_num=numa_num, con_ssh=con_ssh, host_log_core_siblings=log_cores_siblings)

    LOG.tc_step("Check vm vcpus, siblings on vm via /sys/devices/system/cpu/<cpu>/topology/core_siblings_list")
    _check_vm_topology_on_vm(vm_id, vcpus=vcpus, siblings_total=siblings_total)

    LOG.tc_step('Check vm vcpus, pcpus on vm host via nova-compute.log and virsh vcpupin')
    # Note: floating vm pcpus will not be checked via virsh vcpupin
    _check_vm_topology_on_host(vm_id, vcpus=vcpus, vm_pcpus=pcpus_total, prev_total_cpus=prev_total_cpus,
                               expt_increase=expt_increase, vm_host=vm_host, cpu_pol=cpu_pol, cpu_thr_pol=cpu_thr_pol,
                               host_log_core_siblings=log_cores_siblings)

    return pcpus_total, siblings_total


def _check_vm_topology_via_vm_topology(vm_id, vcpus, cpu_pol, cpu_thr_pol, numa_num, vm_host, host_log_core_siblings=None, con_ssh=None):
    """

    Args:
        vm_id:
        vcpus (int):
        cpu_pol (str|None):
        cpu_thr_pol (str|None):
        numa_num (int|None):

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
    if not host_log_core_siblings:
        host_log_core_siblings = host_helper.get_logcore_siblings(host=vm_host, con_ssh=con_ssh)

    expt_cpu_pol = 'sha' if cpu_pol is None or 'sha' in cpu_pol else 'ded'
    instance_topology = vm_helper.get_instance_topology(vm_id, con_ssh=con_ssh)
    instance_topology_nova_show = vm_helper.get_instance_topology(vm_id, con_ssh=con_ssh, source='nova show')

    LOG.tc_step("Check instance topology in vm-topology and nova show are identical")
    for i in range(len(instance_topology)):
        for key in instance_topology[i]:
            assert instance_topology[i][key] == instance_topology_nova_show[i][key], "vm {} {} on numa node {} is " \
                "different in vm-topology than nova show".format(vm_id, key, i)

    pcpus_total = []
    siblings_total = []

    vcpus_per_numa = int(vcpus / numa_num)
    # numa_nodes = []
    for topology_on_numa_node in instance_topology:  # Cannot be on two numa nodes for dedicated vm unless specified
        # numa_nodes.append(topology_on_numa_node['node'])
        actual_vcpus = topology_on_numa_node['vcpus']

        assert expt_cpu_pol == topology_on_numa_node['pol'], "CPU policy is {} instead of {} in vm-topology".\
            format(topology_on_numa_node['pol'], expt_cpu_pol)
        assert vcpus_per_numa == len(actual_vcpus), 'vm vcpus number per numa node is {} instead of {}'.format(
            len(actual_vcpus), vcpus_per_numa)

        actual_siblings = topology_on_numa_node['siblings']
        actual_topology = topology_on_numa_node['topology']
        actual_pcpus = topology_on_numa_node['pcpus']
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
            # TODO assert actual_topology, "vm topology is not included in vm-topology for dedicated vm"

            if cpu_thr_pol:
                # Assumption: hyper-threading must be enabled if vm launched successfully. And thread number is 2.
                assert actual_thread_policy in cpu_thr_pol, 'cpu thread policy in vm topology is {} while flavor ' \
                                                            'spec is {}'.format(actual_thread_policy, cpu_thr_pol)

                if cpu_thr_pol == 'isolate':
                    # isolate-5: node:0, 512MB, pgsize:2M, 1s,5c,1t, vcpus:0-4, pcpus:9,24,27,3,26, pol:ded, thr:iso
                    assert not actual_siblings, "siblings should not be included with only 1 vcpu"
                    # TODO assert '{}c,1t'.format(vcpus_per_numa) in actual_topology
                elif cpu_thr_pol == 'require':
                    # require-4: node:0, 512MB, pgsize:2M, 1s,2c,2t, vcpus:0-3, pcpus:25,5,8,28, siblings:{0,1},{2,3}, pol:ded, thr:req
                    assert actual_siblings, "siblings should be included for dedicated vm"
                    # TODO assert '{}c,2t'.format(int(vcpus_per_numa / 2)) in actual_topology  # 2 is the host thread number

                    siblings_total += actual_siblings
                else:
                    raise NotImplemented("New cpu threads policy added? Update automation code.")

                expt_core_len_in_pair = 1 if cpu_thr_pol == 'isolate' else 2
                for pair in host_log_core_siblings:
                    assert len(set(pair) & set(actual_pcpus)) in [0, expt_core_len_in_pair], "Host sibling pair: {}, " \
                        "VM pcpus:{}. Expected cores per pair: {}".format(pair, actual_pcpus, expt_core_len_in_pair)

                pcpus_total += actual_pcpus

            else:
                # node:1,   512MB, pgsize:2M, 1s,1c,3t, vcpus:0-2, pcpus:35,15,10, siblings:{0-2}, pol:ded, thr:no
                assert topology_on_numa_node['thr'] == 'no', "cpu thread policy is in vm topology"
                # TODO assert '1c,{}t'.format(vcpus_per_numa) in actual_topology, 'vm topology is not as expected'
                assert vcpus_per_numa == len(actual_pcpus), "vm pcpus number per numa node is {} instead of {}".format(
                        len(actual_pcpus), vcpus_per_numa)

                if 1 == vcpus_per_numa:
                    assert not actual_siblings, "siblings should not be included with only 1 vcpu"
                else:
                    assert actual_siblings, 'sibling should be included with dedicated policy and {} vcpus per ' \
                                            'numa node'.format(vcpus_per_numa)

                    siblings_total += actual_siblings

                pcpus_total += actual_pcpus

    return pcpus_total, siblings_total


def _check_vm_topology_on_host(vm_id, vcpus, vm_pcpus, expt_increase, prev_total_cpus, vm_host, cpu_pol, cpu_thr_pol,
                               host_log_core_siblings):

    # Check host side info such as nova-compute.log and virsh pcpupin
    instance_name = nova_helper.get_vm_instance_name(vm_id)
    with host_helper.ssh_to_host(vm_host) as host_ssh:

        LOG.tc_step("Check total allocated vcpus increased by {} from nova-compute.log on host".format(expt_increase))
        post_total_log = host_helper.wait_for_total_allocated_vcpus_update_in_log(host_ssh, prev_cpus=prev_total_cpus)
        assert round(prev_total_cpus + expt_increase, 4) == post_total_log, 'vcpus increase in nova-compute.log is ' \
                                                                            'not as expected'

        LOG.tc_step("Check vcpus for vm via sudo virsh vcpupin")
        vcpus_for_vm = host_helper.get_vcpus_for_instance_via_virsh(host_ssh, instance_name=instance_name)
        assert vcpus == len(vcpus_for_vm), 'vm cpus number is not expected in sudo virsh vcpupin'

        if vm_pcpus:
            all_cpus = []
            for cpus in vcpus_for_vm.values():
                all_cpus += cpus
            assert sorted(vm_pcpus) == sorted(all_cpus), 'pcpus from vm-topology is different than virsh vcpupin'
        else:
            LOG.warning('Skip pcpus check in virsh vcpupin for floating vm')

        LOG.tc_step("Get cpu affinity list for vm via taskset -pc")
        affined_cpus = vm_helper.get_affined_cpus_for_vm(vm_id, host_ssh=host_ssh, vm_host=vm_host,
                                                         instance_name=instance_name)

        if 'ded' in cpu_pol:

            if cpu_thr_pol == 'isolate':
                LOG.tc_step("Check affined cpus for isolate vm is its pcpus plus the siblings of those pcpus")
                expt_affined_cpus = []

                for pcpu in vm_pcpus:
                    for host_sibling_pair in host_log_core_siblings:
                        if pcpu in host_sibling_pair:
                            expt_affined_cpus += host_sibling_pair
                expt_affined_cpus = sorted(list(set(expt_affined_cpus)))

            else:
                LOG.tc_step("Check affined cpus for dedicated vm is the same as its pcpus shown in vm-topology")
                expt_affined_cpus = vm_pcpus

            assert len(affined_cpus) <= len(expt_affined_cpus) + 2
            assert set(expt_affined_cpus) <= set(affined_cpus)

        else:
            LOG.tc_step("Check affined cpus for floating vm is the same as unpinned cpus on vm host")
            # TODO count all numa nodes for floating vm. Any way to get numa nodes dynamically without  cli?
            cpus_info = host_helper.get_vcpus_info_in_log(host_ssh=host_ssh, rtn_list=True, numa_nodes=[0, 1])
            unpinned_cpus = []

            for item in cpus_info:
                unpinned_cpus_for_numa = item['unpinned_cpulist']
                unpinned_cpus += unpinned_cpus_for_numa
            unpinned_cpus = sorted(unpinned_cpus)

            err_msg = "Affined cpus for vm: {}, Unpinned cpus on vm host: {}".format(affined_cpus, unpinned_cpus)
            assert affined_cpus == unpinned_cpus, 'Affined cpus for floating vm are different than unpinned cpus ' \
                                                  'on vm host {}\n{}'.format(vm_host, err_msg)


def _check_vm_topology_on_vm(vm_id, vcpus, siblings_total):
    # Check from vm in /proc/cpuinfo and /sys/devices/.../cpu#/topology/core_siblings_list
    expt_sib_list = [[vcpu] for vcpu in range(vcpus)] if not siblings_total else siblings_total
    actual_sib_list = []
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.tc_step("Check vm has {} cores from inside vm via /proc/cpuinfo.".format(vcpus))
        assert vcpus == vm_helper.get_proc_num_from_vm(vm_ssh)

        LOG.tc_step("Check vm /sys/devices/system/cpu/[cpu#]/topology/core_siblings_list")
        for cpu in ['cpu{}'.format(i) for i in range(vcpus)]:
            actual_sib_list_for_cpu = vm_ssh.exec_cmd('cat /sys/devices/system/cpu/{}/topology/core_siblings_list'.
                                                      format(cpu), fail_ok=False)[1]

            sib_for_cpu = common._parse_cpus_list(actual_sib_list_for_cpu)
            if sib_for_cpu not in actual_sib_list:
                actual_sib_list.append(sib_for_cpu)

    assert sorted(expt_sib_list) == sorted(actual_sib_list)


def check_vm_vcpus_via_nova_show(vm_id, min_cpu, current_cpu, max_cpu, con_ssh=None):
    actual_vcpus = eval(nova_helper.get_vm_nova_show_value(vm_id=vm_id, field='wrs-res:vcpus', con_ssh=con_ssh))
    assert [min_cpu, current_cpu, max_cpu] == actual_vcpus, "vcpus in nova show {} is not as expected".format(vm_id)


def check_vm_numa_nodes(vm_id, on_vswitch_nodes=True):
    vm_host, vm_numa_nodes = vm_helper.get_vm_host_and_numa_nodes(vm_id)
    vswitch_cores_dict = host_helper.get_host_cpu_cores_for_function(vm_host, function='vSwitch')
    vswitch_procs = list(vswitch_cores_dict.keys())

    if on_vswitch_nodes:
        assert set(vm_numa_nodes) <= set(vswitch_procs), "VM {} is on numa nodes {} instead of vswitch numa nodes {}" \
                                                         "".format(vm_id, vm_numa_nodes, vswitch_procs)
    else:
        assert not (set(vm_numa_nodes) & set(vswitch_procs)), "VM {} is on vswitch numa node(s). VM numa nodes: {}, " \
                                                              "vSwitch numa nodes: {}" .format(vm_id, vm_numa_nodes,
                                                                                               vswitch_procs)

def compare_times(time_1, time_2):
    """
    Compares 2 times found from datetime.now(), timestamps found from system host-show, time.time(), etc.
    Args:
        time_1 (datetime, str, float):
        time_2 (datetime, str, float):

    Returns (int):
        -1, time_1 is less than time_2
        0, time_1 is equal to time_2
        1, time_1 is greater than time_2

    """

    # get year, month, day, hour, minute, second
    if isinstance(time_1, str):
        time_1 = datetime.strptime(time_1.replace('T', ' ').split('.')[0], "%Y-%m-%d %H:%M:%S")
    if isinstance(time_2, str):
        time_2 = datetime.strptime(time_2.replace('T', ' ').split('.')[0], "%Y-%m-%d %H:%M:%S")

    if isinstance(time_1, float):
        time_1 = datetime.fromtimestamp(time_1)
    if isinstance(time_2, float):
        time_2 = datetime.fromtimestamp(time_2)

    if time_1 < time_2:
        LOG.info("{} is before {}".format(time_1, time_2))
        return -1
    elif time_1 > time_2:
        LOG.info("{} is after {}".format(time_1, time_2))
        return 1
    elif time_1 == time_2:
        LOG.info("{} is the same as {}".format(time_1, time_2))
        return 0

