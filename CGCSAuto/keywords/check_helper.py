###############################################################
# Intended for check functions for test result verifications
# assert is used to fail the check
# LOG.tc_step is used log the info
# Should be called by test function directly
###############################################################

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
            assert port in actual_vswitch_map, "port {} is not included in vswitch.ini on {}".format(port, host)
            assert engines == actual_vswitch_map[port], 'engine list for port {} on {} is not as expected'. \
                format(host, port)

    else:
        LOG.tc_step("No Mellanox device used on {} data interfaces. Perform strict check on port-engine map.".
                    format(host))

        assert expt_vswitch_map == actual_vswitch_map


def check_topology_of_vm(vm_id, vcpus, prev_total_cpus, numa_num=None, vm_host=None, cpu_pol=None, cpu_thr_pol=None,
                         con_ssh=None):
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
        con_ssh (SSHClient)

    """
    if vm_host is None:
        vm_host = nova_helper.get_vm_host(vm_id, con_ssh=con_ssh)

    if numa_num is None:
        numa_num = 1

    if cpu_pol == 'dedicated':
        expt_increase = vcpus * 2 if cpu_thr_pol == 'isolate' else vcpus
    else:
        expt_increase = vcpus / 16

    LOG.tc_step("Check total vcpus for vm host is increased by {} via nova host-describe".format(expt_increase))
    post_hosts_cpus = host_helper.get_vcpus_for_computes(hosts=vm_host, rtn_val='used_now')
    assert round(prev_total_cpus + expt_increase, 4) == post_hosts_cpus[vm_host]

    LOG.tc_step('Check vm topology, vcpus, pcpus, siblings, cpu policy, cpu threads policy, via vm-topology')
    pcpus_total, siblings_total = _check_vm_topology_via_vm_topology(vm_id, vcpus=vcpus, cpu_pol=cpu_pol,
                                                                     cpu_thr_pol=cpu_thr_pol, vm_host=vm_host,
                                                                     numa_num=numa_num, con_ssh=con_ssh)

    LOG.tc_step("Check vm vcpus, siblings on vm via /sys/devices/system/cpu/<cpu>/topology/core_siblings_list")
    _check_vm_topology_on_vm(vm_id, vcpus=vcpus, siblings_total=siblings_total)

    LOG.tc_step('Check vm vcpus, pcpus on vm host via nova-compute.log and virsh vcpupin')
    # Note: floating vm pcpus will not be checked via virsh vcpupin
    _check_vm_topology_on_host(vm_id, vcpus=vcpus, vm_pcpus=pcpus_total, prev_total_cpus=prev_total_cpus,
                               expt_increase=expt_increase, vm_host=vm_host)


def _check_vm_topology_via_vm_topology(vm_id, vcpus, cpu_pol, cpu_thr_pol, numa_num, vm_host, con_ssh=None):
    """

    Args:
        vm_id:
        vcpus:
        cpu_pol:
        cpu_thr_pol:
        numa_num:

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

    log_cores_siblings = host_helper.get_logcore_siblings(host=vm_host, con_ssh=con_ssh)

    expt_cpu_pol = 'ded' if 'ded' in cpu_pol else 'sha'
    instance_topology = vm_helper.get_instance_topology(vm_id, con_ssh=con_ssh)

    pcpus_total = []
    siblings_total = []

    vcpus_per_numa = int(vcpus / numa_num)

    for topology_on_numa_node in instance_topology:  # Cannot be on two numa nodes for dedicated vm unless specified
        actual_vcpus = topology_on_numa_node['vcpus']

        assert expt_cpu_pol == topology_on_numa_node['pol'], "CPU policy is not {} in vm-topology".format(expt_cpu_pol)
        assert vcpus_per_numa == len(actual_vcpus), 'vm vcpus number per numa node is not as expected'

        actual_siblings = topology_on_numa_node['siblings']
        actual_topology = topology_on_numa_node['topology']
        actual_pcpus = topology_on_numa_node['pcpus']
        actual_thread_policy = topology_on_numa_node['thr']

        if expt_cpu_pol == 'sha':
            # node:0,   512MB, pgsize:2M, vcpus:0-4, pol:sha
            assert topology_on_numa_node['thr'] is None, "cpu thread policy is in vm topology"
            assert actual_siblings is None, 'siblings should not be included for floating vm'
            assert actual_topology is None, 'topology should not be included for floating vm'
            assert actual_pcpus is None, "pcpu should not be included in vm-topology for floating vm"
            assert actual_thread_policy is None, "cpu thread pol should not be included in vm-topology for floating vm"

        elif cpu_thr_pol:
            # Assumption: hyper-threading must be enabled if vm launched successfully. And thread number is 2.
            assert actual_thread_policy in cpu_thr_pol, 'cpu thread policy in vm topology is {} while flavor ' \
                                                        'spec is {}'.format(actual_thread_policy, cpu_thr_pol)

            if cpu_thr_pol == 'isolate':
                # isolate-5: node:0, 512MB, pgsize:2M, 1s,5c,1t, vcpus:0-4, pcpus:9,24,27,3,26, pol:ded, thr:iso
                assert not actual_siblings, "siblings should not be included with only 1 vcpu"
                assert '{}c,1t'.format(vcpus_per_numa) in actual_topology
            elif cpu_thr_pol == 'require':
                # require-4: node:0, 512MB, pgsize:2M, 1s,2c,2t, vcpus:0-3, pcpus:25,5,8,28, siblings:{0,1},{2,3}, pol:ded, thr:req
                assert actual_siblings, "siblings should be included for dedicated vm"
                assert '{}c,2t'.format(int(vcpus_per_numa / 2)) in actual_topology  # 2 is the host thread number

                siblings_total += actual_siblings
            else:
                raise NotImplemented("New cpu threads policy added? Update automation code.")

            expt_core_len_in_pair = 1 if cpu_thr_pol == 'isolate' else 2
            for pair in log_cores_siblings:
                assert len(set(pair) & set(actual_pcpus)) in [0, expt_core_len_in_pair]

            pcpus_total += actual_pcpus

        else:
            # node:1,   512MB, pgsize:2M, 1s,1c,3t, vcpus:0-2, pcpus:35,15,10, siblings:{0-2}, pol:ded, thr:no
            assert topology_on_numa_node['thr'] == 'no', "cpu thread policy is in vm topology"
            assert '1c,{}t'.format(vcpus_per_numa) in actual_topology, 'vm topology is not as expected'
            assert vcpus_per_numa == len(actual_pcpus), "vm pcpus number per numa node is not as expected"
            assert len(actual_siblings[0])

            if 1 == vcpus_per_numa:
                assert not actual_siblings, "siblings should not be included with only 1 vcpu"
            else:
                assert actual_siblings, 'sibling should be included with dedicated policy and {} vcpus per numa node'.\
                    format(vcpus_per_numa)

                siblings_total += actual_siblings

            pcpus_total += actual_pcpus

    return pcpus_total, siblings_total


def _check_vm_topology_on_host(vm_id, vcpus, vm_pcpus, expt_increase, prev_total_cpus, vm_host):

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

    # TODO: add check via from compute via taskset -apc 98456 for floating vm's actual vcpus.


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