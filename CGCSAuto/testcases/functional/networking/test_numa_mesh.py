from utils import table_parser, cli
from utils.tis_log import LOG
from keywords import host_helper


def test_setting_denied_unlocked_host():
    nova_hosts = host_helper.get_nova_hosts()

    assert nova_hosts, "No nova host is up."

    LOG.tc_step("Verify host-cpu-modify is rejected if host is unlocked.")
    for host in nova_hosts:
        code, msg = host_helper.modify_host_cpu(host, 'vswitch', p0=1, fail_ok=True)
        assert 1 == code, "CLI is not rejected with return code 1."
        assert 'Host must be locked' in msg

        LOG.tc_step("Verify one ore more cpu cores are assigned to Platform and vSwitch.")
        table_ = table_parser.table(cli.system('host-cpu-list', host))

        platform_cores = table_parser.get_values(table_, 'log_core', assigned_function='Platform')

        assert len(platform_cores) >= 1, "At least one core should be assigned to Platform"

        vswitch_cores = table_parser.get_values(table_, 'log_core', assigned_function='vSwitch')
        assert len(vswitch_cores) >= 1, "At least one core should be assigned to vSwitch"


# TODO: Add parameter for lab support split and lab that doesn't
def test_ports_cores_mapping():
    nova_hosts = host_helper.get_nova_hosts()
    assert nova_hosts, "No nova host is up."

    for host in nova_hosts:

        with host_helper.ssh_to_host(host) as host_ssh:
            expt_vswitch_map = host_helper.get_expected_vswitch_port_engine_map(host_ssh)
            actual_vswitch_map = host_helper.get_vswitch_port_engine_map(host_ssh)

        assert expt_vswitch_map == actual_vswitch_map
