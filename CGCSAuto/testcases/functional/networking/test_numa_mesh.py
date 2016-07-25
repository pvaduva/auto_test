from pytest import mark

from utils import table_parser, cli
from utils.tis_log import LOG
from keywords import host_helper, system_helper


@mark.p1
def test_set_cpu_cores_denied_unlocked_host():
    nova_hosts = host_helper.get_nova_hosts()

    assert nova_hosts, "No nova host is up."

    LOG.tc_step("Verify host-cpu-modify is rejected if host is unlocked.")
    for host in nova_hosts:
        code, msg = host_helper.modify_host_cpu(host, 'vswitch', p0=1, fail_ok=True)
        assert 1 == code, "modify host cpu CLI is not rejected with return code 1."
        assert 'Host must be locked' in msg

        LOG.tc_step("Verify one ore more cpu cores are assigned to Platform and vSwitch.")
        table_ = table_parser.table(cli.system('host-cpu-list', host))

        platform_cores = table_parser.get_values(table_, 'log_core', assigned_function='Platform')

        assert len(platform_cores) >= 1, "At least one core should be assigned to Platform"

        vswitch_cores = table_parser.get_values(table_, 'log_core', assigned_function='vSwitch')
        assert len(vswitch_cores) >= 1, "At least one core should be assigned to vSwitch"


# TODO: Add parameter for lab support split and lab that doesn't
@mark.p1
def test_vswitch_ports_cores_mapping():
    up_hypervisors = host_helper.get_hypervisors(state='up')
    assert up_hypervisors, "No hypervisor is up."

    for host in up_hypervisors:
        LOG.tc_step("Find out expected port-engine mapping for {} via vshell port/engine-list".format(host))

        with host_helper.ssh_to_host(host) as host_ssh:
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
                assert engines == actual_vswitch_map[port], 'engine list for port {} on {} is not as expected'.\
                    format(host, port)

        else:
            LOG.tc_step("No Mellanox device used on {} data interfaces. Perform strict check on port-engine map.".
                        format(host))

            assert expt_vswitch_map == actual_vswitch_map
