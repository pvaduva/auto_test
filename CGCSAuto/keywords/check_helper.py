###############################################################
# Intended for check functions for test result verifications
# assert is used to fail the check
# LOG.tc_step is used log the info
# Should be called by test function directly
###############################################################
import re
import time

from utils.tis_log import LOG
from consts.cgcs import MELLANOX_DEVICE
from keywords import host_helper, system_helper, vm_helper, nova_helper, network_helper, common

SEP = '\n------------------------------------ '


def check_host_vswitch_port_engine_map(host, con_ssh=None):

    with host_helper.ssh_to_host(host, con_ssh=con_ssh) as host_ssh:
        expt_vswitch_map = host_helper.get_expected_vswitch_port_engine_map(host_ssh)
        actual_vswitch_map = host_helper.get_vswitch_port_engine_map(host_ssh)

    data_ports = system_helper.get_host_ports_for_net_type(host, net_type='data', rtn_list=True)

    device_types = system_helper.get_host_ports_values(host, 'device type', if_name=data_ports, strict=True)
    extra_mt_ports = 0
    for device_type in device_types:
        if re.search(MELLANOX_DEVICE, device_type):
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
        LOG.info("{}No Mellanox device used on {} data interfaces. Perform strict check on port-engine map.".
                 format(SEP, host))

        assert expt_vswitch_map == actual_vswitch_map, "vSwitch mapping unexpected. Expect: {}; Actual: {}".format(
                expt_vswitch_map, actual_vswitch_map)


def check_topology_of_vm(vm_id, vcpus, prev_total_cpus, numa_num=None, vm_host=None, cpu_pol=None, cpu_thr_pol=None,
                         expt_increase=None, min_vcpus=None, current_vcpus=None, prev_siblings=None, con_ssh=None):
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

    log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host, con_ssh=con_ssh)

    if vm_host is None:
        vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

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
                             prev_siblings=prev_siblings)

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

        assert expt_cpu_pol == topology_on_numa_node['pol'], "CPU policy is {} instead of {} in vm-topology".\
            format(topology_on_numa_node['pol'], expt_cpu_pol)
        assert vcpus_per_numa == len(actual_vcpus), 'vm vcpus number on numa node {} is {} instead of {}'.\
            format(node_id, len(actual_vcpus), vcpus_per_numa)

        actual_siblings = topology_on_numa_node['siblings']
        actual_topology = topology_on_numa_node['topology']
        actual_pcpus = sorted(topology_on_numa_node['pcpus'])
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
                if len(actual_vcpus) % 2 == 0:
                    assert actual_siblings, "siblings should be included for dedicated vm"
                    # 2 is the host thread number
                    assert '{}c,2t'.format(int(vcpus_per_numa / 2)) in actual_topology, \
                        "Expected topology: {}c,2t; Actual: {}".format(int(vcpus_per_numa / 2), actual_topology)
                else:
                    assert not actual_siblings, "siblings should not be included for require vm with odd number vcpus"
                    assert '{}c,1t'.format(vcpus_per_numa) in actual_topology, \
                        "Expected topology: {}c,1t; Actual: {}".format(vcpus_per_numa, actual_topology)

                expt_core_len_in_pair = 2
                # siblings_total += actual_siblings

            elif cpu_thr_pol == 'prefer':
                assert vcpus_per_numa == len(actual_pcpus), "vm pcpus number per numa node is {} instead of {}".format(
                        len(actual_pcpus), vcpus_per_numa)
                if is_ht:
                    # Those checks are not guaranteed if vm is migrated from non-HT host to HT host
                    expt_core_len_in_pair = 2
                    if len(actual_vcpus) % 2 == 0:
                        assert '{}c,2t'.format(int(vcpus_per_numa / 2)) in actual_topology, \
                            "Expected topology: {}c,2t; Actual: {}".format(int(vcpus_per_numa / 2), actual_topology)
                        assert actual_siblings, "siblings should be included for prefer vm with even number vcpus " \
                                                "on HT host"
                    else:
                        assert not actual_siblings, "siblings should not be included for prefer vm with odd number vcpu"
                        assert '{}c,1t'.format(vcpus_per_numa) in actual_topology, \
                            "Expected topology: {}c,1t; Actual: {}".format(vcpus_per_numa, actual_topology)
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
        assert max_vcpus == len(pcpus_total), "Max vcpus: {}, pcpus list: {}".format(max_vcpus, pcpus_total)
        assert current_vcpus == len(set(pcpus_total)), "Current vcpus: {}, pcpus: {}".format(max_vcpus, pcpus_total)

    if not siblings_total:
        siblings_total = [[vcpu_] for vcpu_ in range(current_vcpus)]

    LOG.info("vm {} on {} - pcpus total: {}; siblings total: {}".format(vm_id, vm_host, pcpus_total, siblings_total))
    return pcpus_total, siblings_total


def _check_vm_topology_on_host(vm_id, vcpus, vm_pcpus, expt_increase, prev_total_cpus, vm_host, cpu_pol, cpu_thr_pol,
                               host_log_core_siblings):

    # Check host side info such as nova-compute.log and virsh pcpupin
    LOG.tc_step('Check vm topology from vm_host via: nova-compute.log, virsh vcpupin, taskset')
    instance_name = nova_helper.get_vm_instance_name(vm_id)
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
            # TODO count all numa nodes for floating vm. Any way to get numa nodes dynamically from vm host?
            cpus_info = host_helper.get_vcpus_info_in_log(host_ssh=host_ssh, rtn_list=True, numa_nodes=[0, 1])
            unpinned_cpus = []

            for item in cpus_info:
                unpinned_cpus_for_numa = item['unpinned_cpulist']
                unpinned_cpus += unpinned_cpus_for_numa
            unpinned_cpus = sorted(unpinned_cpus)

            err_msg = "Affined cpus for vm: {}, Unpinned cpus on vm host: {}".format(affined_cpus, unpinned_cpus)
            assert affined_cpus == unpinned_cpus, 'Affined cpus for floating vm are different than unpinned cpus ' \
                                                  'on vm host {}\n{}'.format(vm_host, err_msg)


def _check_vm_topology_on_vm(vm_id, vcpus, siblings_total, current_vcpus, prev_siblings=None):
    # Check from vm in /proc/cpuinfo and /sys/devices/.../cpu#/topology/thread_siblings_list
    LOG.tc_step('Check vm topology from within the vm via: /sys/devices/system/cpu')
    actual_sib_list = []
    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_id) as vm_ssh:
        LOG.info("{}Check vm present|online|offline cores from inside vm via /sys/devices/system/cpu/".format(SEP))
        present_cores, online_cores, offline_cores = vm_helper.get_proc_nums_from_vm(vm_ssh)
        expt_sib_lists = [[[vcpu] for vcpu in range(len(online_cores))]] if not siblings_total else [siblings_total]
        if prev_siblings:
            expt_sib_lists.append(prev_siblings)

        assert vcpus == len(present_cores), "Number of vcpus for vm: {}, present cores from " \
                                            "/sys/devices/system/cpu/present: {}".format(vcpus, len(present_cores))
        assert current_vcpus == len(online_cores), \
            "Current vcpus for vm: {}, online cores from /sys/devices/system/cpu/online: {}".\
            format(current_vcpus, online_cores)

        expt_total_cores = len(online_cores) + len(offline_cores)
        assert expt_total_cores in [len(present_cores), 512], \
            "Number of present cores: {}. online+offline cores: {}".format(vcpus, expt_total_cores)

        LOG.info("{}Check vm /sys/devices/system/cpu/[cpu#]/topology/thread_siblings_list".format(SEP))
        for cpu in ['cpu{}'.format(i) for i in range(len(online_cores))]:
            actual_sib_list_for_cpu = vm_ssh.exec_cmd('cat /sys/devices/system/cpu/{}/topology/thread_siblings_list'.
                                                      format(cpu), fail_ok=False)[1]

            sib_for_cpu = common._parse_cpus_list(actual_sib_list_for_cpu)
            if sib_for_cpu not in actual_sib_list:
                actual_sib_list.append(sib_for_cpu)

        if len(online_cores) == len(present_cores):
            assert sorted(actual_sib_list) in sorted(expt_sib_lists), "Expt sib lists: {}, actual sib list: {}".\
                format(sorted(expt_sib_lists), sorted(actual_sib_list))


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

