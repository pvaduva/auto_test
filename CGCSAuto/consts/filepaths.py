class TiSPath:
    TIS_UBUNTU_PATH = '/home/wrsroot/userdata/ubuntu_if_config.sh'
    TIS_CENTOS_PATH = '/home/wrsroot/userdata/centos_if_config.sh'
    USERDATA = '/home/wrsroot/userdata/'
    IMAGES = '/home/wrsroot/images/'


class VMPath:
    VM_IF_PATH_UBUNTU = '/etc/network/interfaces.d/'
    VM_IF_PATH_CENTOS = '/etc/sysconfig/network-scripts/'
    ETH_PATH_UBUNTU = '/etc/network/interfaces.d/{}.cfg'
    ETH_PATH_CENTOS = '/etc/sysconfig/network-scripts/ifcfg-{}'


class UserData:
    ADDUSER_WRSROOT = 'cloud_config_adduser_wrsroot.txt'


class TestServerPath:
    USER_DATA = '/home/svc-cgcsauto/userdata/'


class PrivKeyPath:
    OPT_PLATFORM = "/opt/platform/id_rsa"
    WRS_HOME = '/home/wrsroot/.ssh/id_rsa'


WRSROOT_HOME = '/home/wrsroot/'
