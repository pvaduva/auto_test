WRSROOT_HOME = '/home/wrsroot/'


class TiSPath:
    TIS_UBUNTU_PATH = '/home/wrsroot/userdata/ubuntu_if_config.sh'
    TIS_CENTOS_PATH = '/home/wrsroot/userdata/centos_if_config.sh'
    USERDATA = '/home/wrsroot/userdata/'
    IMAGES = '/home/wrsroot/images/'
    INSTALL_STATUS = 'home/wrsroot/autoinstall_status.log'
    HEAT = '/home/wrsroot/heat/'
    BACKUPS = '/opt/backups'
    CUSTOM_HEAT_TEMPLATES = '/home/wrsroot/custom_heat_templates/'


class VMPath:
    VM_IF_PATH_UBUNTU = '/etc/network/interfaces.d/'
    ETH_PATH_UBUNTU = '/etc/network/interfaces.d/{}.cfg'
    # Below two paths are common for CentOS, OpenSUSE, and RHEL
    VM_IF_PATH_CENTOS = '/etc/sysconfig/network-scripts/'
    ETH_PATH_CENTOS = '/etc/sysconfig/network-scripts/ifcfg-{}'


class UserData:
    ADDUSER_WRSROOT = 'cloud_config_adduser_wrsroot.txt'
    DPDK_USER_DATA = 'dpdk_user_data.txt'


class HeatTemplate:
    STRESS_NG = 'stress_ng.yaml'
    HEAT_DIR = '{}heat/hot/'.format(WRSROOT_HOME)


class TestServerPath:
    USER_DATA = '/home/svc-cgcsauto/userdata/'
    TEST_SCRIPT = '/home/svc-cgcsauto/test_scripts/'
    CUSTOM_HEAT_TEMPLATES = '/sandbox/custom_heat_templates/'


class PrivKeyPath:
    OPT_PLATFORM = '/opt/platform/id_rsa'
    WRS_HOME = '/home/wrsroot/.ssh/id_rsa'


class BuildServerPath:
    DEFAULT_BUILD_SERVER = 'yow-cgts4-lx'
    DEFAULT_WORK_SPACE = '/localdisk/loadbuild/jenkins'
    DEFAULT_HOST_BUILDS_DIR = '/localdisk/loadbuild/jenkins/TC_18.03_Host'
    DEFAULT_GUEST_IMAGE_PATH = '/localdisk/loadbuild/jenkins/TC_18.03_Guest/latest_build/export/tis-centos-guest.img'
    DEFAULT_HOST_BUILD_PATH = '{}/latest_build'.format(DEFAULT_HOST_BUILDS_DIR)
    DEFAULT_LICENSE_PATH = '/folk/cgts/lab/license.lic'
    DEFAULT_PATCH_DIR = '/folk/cgts/patches-to-verify/'
    HEAT_TEMPLATES = 'std/repo/addons/wr-cgcs/layers/cgcs/openstack/recipes-base/python-heat/python-heat/templates'
    CONFIG_LAB_REL_PATH = 'std/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab'

    LATEST_HOST_BUILD_PATHS = {'15.12': '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/',
                               '16.10': '/localdisk/loadbuild/jenkins/TS_16.10_Host/latest_build/',
                               '17.06': '/localdisk/loadbuild/jenkins/TC_17.06_Host/latest_build/',
                               '18.01': '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/',
                               '18.03': '/localdisk/loadbuild/jenkins/TC_18.03_Host/latest_build/',
                               '18.04': '/localdisk/loadbuild/jenkins/TC_18.04_Host/latest_build/',
                               }
    TIS_LICENSE_PATHS = {'15.12': ['/folk/cgts/lab/TiS15-GA-full.lic', '/folk/cgts/lab/TiS15.12-CPE-full-dec2016.lic'],
                         '16.10': ['/folk/cgts/lab/TiS16-full.lic', '/folk/cgts/lab/TiS16-CPE-full.lic'],
                         '17.00': ['/folk/cgts/lab/TiS17-full.lic', '/folk/cgts/lab/TiS17-CPE-full.lic'],
                         '17.06': ['/folk/cgts/lab/TiS17-full.lic', '/folk/cgts/lab/TiS17-CPE-full.lic'],
                         '18.01': ['/folk/cgts/lab/R5-full.lic', '/folk/cgts/lab/R5-AIO-DX-full.lic',
                                   '/folk/cgts/lab/R5-AIO-SX-full.lic'],
                         '18.03': ['/folk/cgts/lab/R5-full.lic', '/folk/cgts/lab/R5-AIO-DX-full.lic',
                                   '/folk/cgts/lab/R5-AIO-SX-full.lic']
                         }

    PATCH_DIR_PATHS = {'15.12': DEFAULT_PATCH_DIR + '15.12',
                       '16.10': DEFAULT_PATCH_DIR + '16.10',
                       '17.06': DEFAULT_PATCH_DIR + '17.06',
                       '18.01': '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/last_build_with_test_patches/test_patches',
                       }

    GUEST_IMAGE_PATHS = {'15.12': '/localdisk/loadbuild/jenkins/TS_15.12_Guest/cgcs-guest.img',
                         '16.10': '/localdisk/loadbuild/jenkins/CGCS_3.0_Guest_Daily_Build/cgcs-guest.img',
                         '17.06':
                             '/localdisk/loadbuild/jenkins/TC_17.06_Guest/latest_build/export/tis-centos-guest.img',
                         '18.01':
                             '/localdisk/loadbuild/jenkins/CGCS_5.0_Guest/latest_build/export/tis-centos-guest.img',
                         '18.03':
                             '/localdisk/loadbuild/jenkins/TC_18.03_Guest/latest_build/export/tis-centos-guest.img'
                         }


class BMCPath:
    SENSOR_DATA_DIR = '/var/run/ipmitool/'
    SENSOR_DATA_FILE_PATH = '{}/hwmond_{}_sensor_data'      # need to provide dir and host


class SecurityPath:
    DEFAULT_CERT_PATH = '/home/wrsroot/server-with-key.pem'
    ALT_CERT_PATH = '/home/wrsroot/certificates-files/server-with-key.pem.bk'
