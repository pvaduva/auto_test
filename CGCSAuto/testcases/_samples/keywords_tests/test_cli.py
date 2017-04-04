from utils import cli
from consts.auth import CliAuth
from keywords import ceilometer_helper, keystone_helper, system_helper


def test_clis():
    print(CliAuth.get_var('HTTPS'))
    cli.system('host-list')
    cli.system('host-show controller-0')
    cli.nova('list')
    cli.heat('stack-list')
    ceilometer_helper.get_samples()
    keystone_helper.get_endpoints()
    cli.neutron('router-list')
    cli.neutron('router-list', convert_openstack=True)
    cli.cinder('list')
    cli.glance('image-list')


def test_alarms():
    system_helper.get_alarms()
    system_helper.delete_alarms()
    system_helper.get_alarms()
    system_helper.get_alarms_table()
