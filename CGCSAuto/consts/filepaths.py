WRSROOT_HOME = '/home/wrsroot/'


class TiSPath:
    TIS_UBUNTU_PATH = '/home/wrsroot/userdata/ubuntu_if_config.sh'
    TIS_CENTOS_PATH = '/home/wrsroot/userdata/centos_if_config.sh'
    USERDATA = '/home/wrsroot/userdata/'
    IMAGES = '/home/wrsroot/images/'
    INSTALL_STATUS = 'home/wrsroot/autoinstall_status.log'


class VMPath:
    VM_IF_PATH_UBUNTU = '/etc/network/interfaces.d/'
    ETH_PATH_UBUNTU = '/etc/network/interfaces.d/{}.cfg'
    # Below two paths are common for CentOS, OpenSUSE, and RHEL
    VM_IF_PATH_CENTOS = '/etc/sysconfig/network-scripts/'
    ETH_PATH_CENTOS = '/etc/sysconfig/network-scripts/ifcfg-{}'


class UserData:
    ADDUSER_WRSROOT = 'cloud_config_adduser_wrsroot.txt'


class TestServerPath:
    USER_DATA = '/home/svc-cgcsauto/userdata/'


class PrivKeyPath:
    OPT_PLATFORM = "/opt/platform/id_rsa"
    WRS_HOME = '/home/wrsroot/.ssh/id_rsa'


class BuildServerPath:
    DEFAULT_BUILD_SERVER = 'yow-cgts4-lx'
    DEFAULT_GUEST_IMAGE_PATH = '/localdisk/loadbuild/jenkins/CGCS_3.0_Guest_Daily_Build/cgcs-guest.img'
    DEFAULT_HOST_BUILD_PATH = '/localdisk/loadbuild/jenkins/CGCS_3.0_Centos_Build/latest_build/'
    DEFAULT_LICENSE_PATH = '/folk/cgts/lab/TiS16-full.lic'
    HEAT_TEMPLATES = ''

