#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

import os


class StxPath:
    TIS_UBUNTU_PATH = '~/userdata/ubuntu_if_config.sh'
    TIS_CENTOS_PATH = '~/userdata/centos_if_config.sh'
    USERDATA = '~/userdata/'
    IMAGES = '~/images/'
    HEAT = '~/heat/'
    BACKUPS = '/opt/backups'
    CUSTOM_HEAT_TEMPLATES = '~/custom_heat_templates/'
    HELM_CHARTS_DIR = '/www/pages/helm_charts/'
    DOCKER_CONF = '/etc/docker-distribution/registry/config.yml'
    DOCKER_REPO = '/var/lib/docker-distribution/docker/registry/v2/repositories'


class VMPath:
    VM_IF_PATH_UBUNTU = '/etc/network/interfaces.d/'
    ETH_PATH_UBUNTU = '/etc/network/interfaces.d/{}.cfg'
    # Below two paths are common for CentOS, OpenSUSE, and RHEL
    VM_IF_PATH_CENTOS = '/etc/sysconfig/network-scripts/'
    ETH_PATH_CENTOS = '/etc/sysconfig/network-scripts/ifcfg-{}'

    # Centos paths for ipv4:
    RT_TABLES = '/etc/iproute2/rt_tables'
    ETH_RT_SCRIPT = '/etc/sysconfig/network-scripts/route-{}'
    ETH_RULE_SCRIPT = '/etc/sysconfig/network-scripts/rule-{}'
    ETH_ARP_ANNOUNCE = '/proc/sys/net/ipv4/conf/{}/arp_announce'
    ETH_ARP_FILTER = '/proc/sys/net/ipv4/conf/{}/arp_filter'


class UserData:
    ADDUSER_WRSROOT = 'cloud_config_adduser_wrsroot.txt'
    DPDK_USER_DATA = 'dpdk_user_data.txt'


class HeatTemplate:
    STRESS_NG = 'stress_ng.yaml'
    HEAT_DIR = '~/heat/hot/'
    LARGE_HEAT = 'upgrade_heat_template'
    LARGE_HEAT_NAME = 'upgrade_stack'
    SYSTEM_TEST_HEAT = 'system_test_template'
    SYSTEM_TEST_HEAT_NAME = 'NOKIA_V3'


class TestServerPath:
    TEST_FILES = '/sandbox/test_files/'
    CUSTOM_HEAT_TEMPLATES = '/sandbox/custom_heat_templates/'
    CUSTOM_APPS = '/sandbox/custom_apps/'


class PrivKeyPath:
    OPT_PLATFORM = '/opt/platform/id_rsa'
    SYS_HOME = '~/.ssh/id_rsa'


class BuildDirs:
    VALID_BUILD_DIRS = ['TS_15.12_Host', 'TS_16.10_Host',
                        'TS_16.10_Prestaging_Build', 'TC_17.06_Host',
                        'TC_17.06_Prestaging_Build', 'TC_18.03_Host',
                        'TC_18.03_Prestaging_Build', 'TC_18.07_Host',
                        'CGCS_6.0_Host', 'Titanium_R6_build',
                        'StarlingX_18.10', 'StarlingX_Upstream_build']

    def is_builds_dir_name_valid(self, builds_dir_name):
        if builds_dir_name:
            return builds_dir_name in self.VALID_BUILD_DIRS
        else:
            return False


class BuildServerPath:

    DEFAULT_BUILD_SERVER = 'yow-cgts1-lx'
    DEFAULT_WORK_SPACE = '/localdisk/loadbuild/jenkins'
    TITANIUM_HOST_BUILDS_DIR = '/localdisk/loadbuild/jenkins/Titanium_R6_build'
    STX_HOST_BUILDS_DIR = \
        '/localdisk/loadbuild/jenkins/StarlingX_Upstream_build'
    STX_RELEASE_DIR = '/localdisk/loadbuild/jenkins/StarlingX_18.10'
    STX_MASTER_CENGN_DIR = '/import/mirrors/cengn/master/centos'
    EAR_HOST_BUILDS_DIR = '/localdisk/loadbuild/jenkins/TC_19.05_Build'

    DEFAULT_HOST_BUILDS_DIR = STX_MASTER_CENGN_DIR
    DEFAULT_GUEST_IMAGE_PATH = '/localdisk/loadbuild/jenkins/CGCS_6.0_Guest/' \
                               'latest_build/export/tis-centos-guest.img'
    LATEST_BUILD = 'latest_build'
    EAR_HOST_BUILD_PATH = '{}/{}'.format(EAR_HOST_BUILDS_DIR, LATEST_BUILD)
    DEFAULT_HOST_BUILD_PATH = '{}/latest_build'.format(DEFAULT_HOST_BUILDS_DIR)
    DEFAULT_LICENSE_PATH = '/folk/cgts/lab/license.lic'
    DEFAULT_PATCH_DIR = '/folk/cgts/patches-to-verify/'
    DEFAULT_PATCH_ENABLE_DEV_DIR = \
        '/folk/cgts/tools/Enable_dev_certificate_patch/'
    HEAT_TEMPLATES_PREV = 'std/repo/addons/wr-cgcs/layers/cgcs/openstack/' \
                          'recipes-base/python-heat/python-heat/templates'
    HEAT_TEMPLATES = 'export/heat-templates'
    LAB_CONF_DIR_PREV = 'std/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab'
    LAB_CONF_DIR = "lab"
    STX_HELM_CHARTS_CENGN = 'outputs/helm-charts'
    ISO_PATH_CENGN = 'outputs/iso/bootimage.iso'
    ISO_PATH = 'export/bootimage.iso'
    STX_HELM_CHARTS = 'helm-charts'
    TITANIUM_HELM_CHARTS = 'helm-charts/centos'
    DEFAULT_HELM_CHARTS = STX_HELM_CHARTS_CENGN
    DEFAULT_ISO = ISO_PATH_CENGN
    DEPLOY_MANAGER_PATH = '/folk/cgts/lab/deployment-manager/'
    DEPLOY_MANAGER_REPO_PATH = LAB_CONF_DIR + "/deployment-manager"
    PLAY_BOOKS_PATH = LAB_CONF_DIR + "/playbooks"
    DEFAULT_CUMULUS_DOCKER_REGISTRY_CERT_PATH = LAB_CONF_DIR + '/pki/cumulus-docker-registry-ca-cert.pem'
    TITANIUM_DEPLOYMENT_MGR_TGZ = "wind-river-cloud-platform-deployment-manager-2.0.0.tgz"

    HEAT_TEMPLATES_EXTS = {'16.10': HEAT_TEMPLATES_PREV,
                           '17.06': HEAT_TEMPLATES_PREV,
                           '18.03': HEAT_TEMPLATES_PREV,
                           'default': HEAT_TEMPLATES}

    DEFAULT_LAB_CONFIG_PATH_EXTS = {'16.10': LAB_CONF_DIR_PREV,
                                    '17.06': LAB_CONF_DIR_PREV,
                                    '18.03': LAB_CONF_DIR_PREV,
                                    'default': LAB_CONF_DIR}

    class BldsDirNames:
        TS_15_12_HOST = 'TS_15.12_Host'
        TS_16_10_HOST = 'TS_16.10_Host'
        TS_16_10_PRESTAGING_BUILD = 'TS_16.10_Prestaging_Build'
        TC_17_06_HOST = 'TC_17.06_Host'
        TC_17_06_PRESTAGING_BUILD = 'TC_17.06_Prestaging_Build'
        TC_18_03_HOST = 'TC_18.03_Host'
        TC_18_03_PRESTAGING_BUILD = 'TC_18.03_Prestaging_Build'
        TC_18_07_HOST = 'TC_18.07_Host'
        CGCS_6_0_HOST = 'CGCS_6.0_Host'
        TITANIUM_R6_BUILD = 'Titanium_R6_build'
        STARLINGX_18_10 = 'StarlingX_18.10'
        STARLINGX_UPSTREAM = 'StarlingX_Upstream_build'
        TC_19_05_BUILD = 'TC_19.05_Build'

        R2_VERSION_SEARCH_REGEX = r'(?:15.12|CGTS_2.0)'
        R3_VERSION_SEARCH_REGEX = r'(?:_16.10|CGCS_3.0)'
        R4_VERSION_SEARCH_REGEX = r'(?:_17.06|CGCS_4.0)'
        R5_VERSION_SEARCH_REGEX = r'(?:_18.03|CGCS_5.0)'
        R6_VERSION_SEARCH_REGEX = r'(?:CGCS_6.0|_R6_|StarlingX)'

    LATEST_HOST_BUILD_PATHS = {
        '15.12': os.path.join(DEFAULT_WORK_SPACE,
                              BldsDirNames.TS_15_12_HOST, LATEST_BUILD),
        '16.10': os.path.join(DEFAULT_WORK_SPACE, BldsDirNames.TS_16_10_HOST,
                              LATEST_BUILD),
        '17.06': [
            os.path.join(DEFAULT_WORK_SPACE,
                         BldsDirNames.TC_17_06_HOST, LATEST_BUILD),
            os.path.join(DEFAULT_WORK_SPACE,
                         BldsDirNames.TC_17_06_PRESTAGING_BUILD,
                         LATEST_BUILD)
        ],
        '18.03': [
            os.path.join(DEFAULT_WORK_SPACE, BldsDirNames.TC_18_03_HOST,
                         LATEST_BUILD),
            os.path.join(DEFAULT_WORK_SPACE,
                         BldsDirNames.TC_18_03_PRESTAGING_BUILD, LATEST_BUILD)],
        'default': [
            os.path.join(DEFAULT_WORK_SPACE, BldsDirNames.TITANIUM_R6_BUILD,
                         LATEST_BUILD),
            os.path.join(DEFAULT_WORK_SPACE, BldsDirNames.STARLINGX_18_10,
                         LATEST_BUILD),
            os.path.join(DEFAULT_WORK_SPACE, BldsDirNames.STARLINGX_UPSTREAM,
                         LATEST_BUILD),
            os.path.join(DEFAULT_WORK_SPACE, BldsDirNames.CGCS_6_0_HOST,
                         LATEST_BUILD)],
    }

    TIS_LICENSE_PATHS = {
        '15.12': ['/folk/cgts/lab/TiS15-GA-full.lic',
                  '/folk/cgts/lab/TiS15.12-CPE-full-dec2016.lic'],
        '16.10': ['/folk/cgts/lab/TiS16-full.lic',
                  '/folk/cgts/lab/TiS16-CPE-full.lic'],
        '17.00': ['/folk/cgts/lab/TiS17-full.lic',
                  '/folk/cgts/lab/TiS17-CPE-full.lic'],
        '17.06': ['/folk/cgts/lab/TiS17-full.lic',
                  '/folk/cgts/lab/TiS17-CPE-full.lic'],
        '18.01': ['/folk/cgts/lab/R5-full.lic',
                  '/folk/cgts/lab/R5-AIO-DX-full.lic',
                  '/folk/cgts/lab/R5-AIO-SX-full.lic'],
        '18.03': ['/folk/cgts/lab/R5-full.lic',
                  '/folk/cgts/lab/R5-AIO-DX-full.lic',
                  '/folk/cgts/lab/R5-AIO-SX-full.lic'],
        '18.07': ['/folk/cgts/lab/R6-EAR1-eval.lic',
                  '/folk/cgts/lab/R6-EAR1-AIO-DX-eval.lic',
                  '/folk/cgts/lab/R6-EAR1-AIO-SX-eval.lic'],
        '19.10': ['/folk/cgts/lab/licenses/wrslicense-wrcp-1910.lic',
                  '/folk/cgts/lab/licenses/wrslicense-wrcp-1910.lic',
                  '/folk/cgts/lab/licenses/wrslicense-wrcp-1910.lic'],
        'default': ['/folk/cgts/lab/R6-full.lic',
                    '/folk/cgts/lab/R6-AIO-DX-full.lic',
                    '/folk/cgts/lab/R6-AIO-SX-full.lic'],
    }

    PATCH_DIR_PATHS = {
        '15.12': DEFAULT_PATCH_DIR + '15.12',
        '16.10': DEFAULT_PATCH_DIR + '16.10',
        '17.06': DEFAULT_PATCH_DIR + '17.06',
        '18.03': DEFAULT_PATCH_DIR + '18.03',
        '18.04': DEFAULT_WORK_SPACE + '/CGCS_6.0_Test_Patch_Build/latest_build',
        'default':
            DEFAULT_WORK_SPACE + '/CGCS_6.0_Test_Patch_Build/latest_build',
    }

    TEST_PATCH_DIR_PATHS = {
        '18.03': DEFAULT_WORK_SPACE + '/TC_18.03_Test_Patch_Build/latest_build',
        '18.04': DEFAULT_WORK_SPACE + '/CGCS_6.0_Test_Patch_Build/latest_build',
        'default':
            DEFAULT_WORK_SPACE + '/CGCS_6.0_Test_Patch_Build/latest_build',
    }

    PATCH_ENABLE_DEV_CERTIFICATES = {
        'default':
            DEFAULT_PATCH_ENABLE_DEV_DIR + 'PATCH.ENABLE_DEV_CERTIFICATE.patch',
        '17.06':
            DEFAULT_PATCH_ENABLE_DEV_DIR +
            'PATCH.ENABLE_DEV_CERTIFICATE-17.06.patch',
        '18.03':
            DEFAULT_PATCH_ENABLE_DEV_DIR +
            'PATCH.ENABLE_DEV_CERTIFICATE-18.03.patch',
        '18.04':
            DEFAULT_PATCH_ENABLE_DEV_DIR + 'PATCH.ENABLE_DEV_CERTIFICATE.patch',
    }

    GUEST_IMAGE_PATHS = {
        '15.12':
            '/localdisk/loadbuild/jenkins/TS_15.12_Guest/cgcs-guest.img',
        '16.10':
            '/localdisk/loadbuild/jenkins/CGCS_3.0_Guest_Daily_Build/'
            'cgcs-guest.img',
        '17.06':
            '/localdisk/loadbuild/jenkins/TC_17.06_Guest/latest_build/export/'
            'tis-centos-guest.img',
        '18.03':
            '/localdisk/loadbuild/jenkins/TC_18.03_Guest/latest_build/export/'
            'tis-centos-guest.img',
        '18.07':
            '/localdisk/loadbuild/jenkins/TC_18.07_Guest/latest_build/export/'
            'tis-centos-guest.img',
        'default':
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Guest/latest_build/export/'
            'tis-centos-guest.img',
        }


class BMCPath:
    SENSOR_DATA_DIR = '/var/run/ipmitool/'
    # need to provide dir and host
    SENSOR_DATA_FILE_PATH = '{}/hwmond_{}_sensor_data'
    @staticmethod
    def get_ipmi_sensor_data_files(node):
        IMPI_SENSOR_DATA_DIR = '/var/run/bmc/ipmitool/'
        file = 'hwmond_%s_sensor_data' % node
        return [os.path.join(IMPI_SENSOR_DATA_DIR, file)]

    @staticmethod
    def get_redfish_sensor_data_files(node):
        REDFISH_SENSOR_DATA_DIR = '/var/run/bmc/redfishtool/'
        thermal_sensor_file = 'hwmond_%s_thermal_sensor_data' % node
        power_sensor_file = 'hwmond_%s_power_sensor_data' % node
        return [os.path.join(REDFISH_SENSOR_DATA_DIR, thermal_sensor_file),
                os.path.join(REDFISH_SENSOR_DATA_DIR, power_sensor_file)]


class SecurityPath:
    DEFAULT_CERT_PATH = '~/server-with-key.pem'
    ALT_CERT_PATH = '~/certificates-files/server-with-key.pem.bk'
    CA_CERT_PATH = '~/ca-cert.pem'


class IxiaPath:
    CFG_500FPS = "D:/CGCS/IxNetwork/cgcsauto/pair_at_500fps.ixncfg"
    WCP35_60_Traffic = "D:/CGCS/IxNetwork/cgcsauto/WCP35_L3_208Vms.ixncfg"
    CFG_UDP = "D:/CGCS/IxNetwork/cgcsauto/udp.ixncfg"


class CompConfPath:
    COMP_EXTEND = '/etc/nova/compute_extend.conf'
    COMP_RESERVED = '/etc/nova/compute_reserved.conf'


class MuranoPath:
    APP_DEMO_PATH = '/folk/cgts/users/jsun3/' \
                    'com.wrs.titanium.murano.examples.demo.zip'
    BASE_PACKAGES = ["/var/cache/murano/meta/io.murano.zip",
                     "/var/cache/murano/meta/io.murano.applications.zip"]


class TuxlabServerPath:
    DEFAULT_TUXLAB_SERVER = 'yow-tuxlab2'
    DEFAULT_BARCODES_DIR = '/export/pxeboot/vlm-boards'


class LogPath:
    LAB_SETUP_LOG = '~/lab_setup.group0.log'
    HEAT_SETUP_LOG = '~/launch_heat_stacks.log'
    CONFIG_CONTROLLER_LOG = '/var/log/puppet/latest/puppet.log'


class SysLogPath:
    DC_MANAGER = '/var/log/dcmanager/dcmanager.log'
    DC_ORCH = '/var/log/dcorch/dcorch.log'
