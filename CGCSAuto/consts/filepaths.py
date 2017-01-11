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
    OPT_PLATFORM = '/opt/platform/id_rsa'
    WRS_HOME = '/home/wrsroot/.ssh/id_rsa'


class BuildServerPath:
    DEFAULT_BUILD_SERVER = 'yow-cgts4-lx'
    DEFAULT_WORK_SPACE = '/localdisk/loadbuild/jenkins'
    DEFAULT_HOST_BUILDS_DIR = '/localdisk/loadbuild/jenkins/CGCS_4.0_Centos_Build'
    DEFAULT_GUEST_IMAGE_PATH = '/localdisk/loadbuild/jenkins/CGCS_4.0_Centos_Guest_Build/latest_tis-centos-guest.img'
    DEFAULT_HOST_BUILD_PATH = '{}/latest_build/'.format(DEFAULT_HOST_BUILDS_DIR)
    DEFAULT_LICENSE_PATH = '/folk/cgts/lab/TiS16-full.lic'
    HEAT_TEMPLATES = ''
    LATEST_HOST_BUILD_PATHS = {'15.12': '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/',
                               '16.10': '/localdisk/loadbuild/jenkins/TS_16.10_Host/latest_build/',
                               '17.00': '/localdisk/loadbuild/jenkins/CGCS_4.0_Centos_Build/latest_build/',
                              }
    TIS_LICENSE_PATHS = {'15.12': ['/folk/cgts/lab/TiS15-GA-full.lic', '/folk/cgts/lab/TiS15.12-CPE-full-dec2016.lic'],
                         '16.10': ['/folk/cgts/lab/TiS16-full.lic', '/folk/cgts/lab/TiS16-CPE-full.lic'],
                         '17.00': ['/folk/cgts/lab/TiS17-full.lic', '/folk/cgts/lab/TiS17-CPE-full.lic'],
                        }

    PATCH_DIR_PATHS = {'15.12': '/folk/cgts/patches-to-verify/15.12',
                       '16.10': '/folk/cgts/patches-to-verify/16.10',
                       '17.00': None
                      }