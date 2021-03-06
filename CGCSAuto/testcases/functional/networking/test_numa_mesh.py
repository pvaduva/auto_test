from pytest import mark, skip

from utils import table_parser, cli
from utils.tis_log import LOG
from keywords import host_helper, check_helper, system_helper


# Remove since it's covered by test_modify_cpu_unlock_negative
@mark.p2
def _test_set_cpu_cores_denied_unlocked_host():
    nova_hosts = host_helper.get_up_hypervisors()

    assert nova_hosts, "No nova host is up."

    LOG.tc_step("Verify host-cpu-modify is rejected if host is unlocked.")
    for host in nova_hosts:
        code, msg = host_helper.modify_host_cpu(host, 'vswitch', p0=1, fail_ok=True)
        assert 1 == code, "modify host cpu CLI is not rejected with return code 1."
        assert 'Host must be locked' in msg

        LOG.tc_step("Verify one ore more cpu cores are assigned to Platform and vSwitch.")
        table_ = table_parser.table(cli.system('host-cpu-list', host)[1])

        platform_cores = table_parser.get_values(table_, 'log_core', assigned_function='Platform')

        assert len(platform_cores) >= 1, "At least one core should be assigned to Platform"

        vswitch_cores = table_parser.get_values(table_, 'log_core', assigned_function='vSwitch')
        assert len(vswitch_cores) >= 1, "At least one core should be assigned to vSwitch"


# TODO: Add parameter for lab support split and lab that doesn't
@mark.p2
def test_vswitch_ports_cores_mapping():
    if not system_helper.is_avs():
        skip("vshell commands unsupported by OVS")

    up_hypervisors = host_helper.get_hypervisors(state='up')
    assert up_hypervisors, "No hypervisor is up."

    for host in up_hypervisors:
        LOG.tc_step("Find out expected port-engine mapping for {} via vshell port/engine-list".format(host))

        check_helper.check_host_vswitch_port_engine_map(host)
