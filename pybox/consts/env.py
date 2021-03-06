import getpass
from sys import platform

user = getpass.getuser()

if platform == 'win32' or platform == 'win64':
    FILEPATH = 'C:\\Temp\\install_files\\'
    LOGPATH = 'C:\\Temp\\pybox_logs'
    ISOPATH = "C:\\Temp\\install_files\\{}\\bootimage.iso"
    PORT = 10000
else:
    FILEPATH = '/tmp/install_files/'
    LOGPATH = '/tmp/pybox_logs'
    ISOPATH = "/tmp/install_files/{}/bootimage.iso"


class BuildServers:
    CGTS4 = {
        'short_name': 'cgts4',
        'name': 'yow-cgts4-lx.wrs.com',
        'ip': '128.224.145.137'
    }

    CGTS3 = {
        'short_name': 'cgts3',
        'name': 'yow-cgts3-lx.wrs.com',
        'ip': '128.224.145.134'
    }

    CGTS2 = {
        'short_name': 'cgts2',
        'name': 'yow-cgts2-lx.wrs.com',
        'ip': '128.224.145.117'
    }


    CGTS1 = {
        'short_name': 'cgts1',
        'name': 'yow-cgts1-lx.wrs.com',
        'ip': '128.224.145.95'
    }


class Builds:
    R6 = {
        'release': 'R6',
        'iso': '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/export/bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/CGCS_6.0_Guest/latest_tis-centos-guest.img'
    }

    R5 = {
        'release': 'R5',
        'iso': '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/CGCS_5.0_Guest/latest_tis-centos-guest.img'
    }

    R4 = {
        'release': 'R4',
        'iso': '/localdisk/loadbuild/jenkins/TC_17.06_Host/latest_bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/TC_17.06_Guest/latest_tis-centos-guest.img',
        'patches': ['/folk/cgts/patches-to-verify/17.06/', '/folk/cgts/rel-ops/17.06/patches/']
    }

    R3 = {
        'release': 'R3',
        'iso': '/localdisk/loadbuild/jenkins/TS_16.10_Host/respun-GA/export/bootimage.iso', 
        'guest': '/localdisk/loadbuild/jenkins/CGCS_3.0_Guest_Daily_Build/cgcs-guest.img', 
        'patches': ['/folk/cgts/patches-to-verify/16.10/', '/folk/cgts/rel-ops/16.10/patches/']
    }

    R2 = {
        'release': 'R2',
        'iso': '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/TS_15.12_Guest/cgcs-guest.img',
        'patches': ['/folk/cgts/patches-to-verify/15.12/', '/folk/cgts/rel-ops/15.12/patches/']
    }


class Licenses:
    R2 = {
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-CPE-15.12-full-dec2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-15.12-full-dec2018.lic'
    }

    R3 = {
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-CPE-16.10-full-dec2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-16.10-full-dec2018.lic'
    }

    R4 = {
        'AIO-SX': '/folk/cgts/lab/licenses/wrslicense-AIO-SX-17.06-full-dec2018.lic',
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-AIO-DX-17.06-full-dec2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-17.06-full-dec2018.lic'
    }

    R5 = {
        'AIO-SX': '/folk/cgts/lab/licenses/wrslicense-AIO-SX-18.03-full-dec2018.lic',
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-AIO-DX-18.03-full-dec2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-18.03-full-dec2018.lic'
    }

    R6 = {
        'AIO-SX': '/folk/cgts/lab/licenses/wrslicense-AIO-SX-R6-full-nov2018.lic',
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-AIO-DX-R6-full-nov2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-R6-full-nov2018.lic'
    }


class Lab:
    VBOX = {
        'short_name': 'lvm',
        'name': 'lvm',
        'floating_ip': '10.10.10.7',
        'controller-0_ip': '10.10.10.8',
        'controller-1_ip': '10.10.10.9',
        'username': 'wrsroot',
        'password': 'Li69nux*',
    }


class Files:
    R6 = {
        'setup': [
            # TODO Need to find a way to update based on build or use generic CGCS_DEV
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf',
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/iptables.rules',
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-tenant2-resources.yaml',
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-tenant1-resources.yaml',
            '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-admin-resources.yaml'
        ],
        'config': '/localdisk/loadbuild/jenkins/CGCS_6.0_Host/latest_green_build/lab/yow/cgcs-vbox/TiS_config.ini_centos'

    }
    R5={
        'setup': [
            # TODO Need to find a way to update based on build or use generic CGCS_DEV
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/iptables.rules',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-tenant2-resources.yaml',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-tenant1-resources.yaml',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-admin-resources.yaml',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup_aio_1_disk.conf',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup_aio_2_disks.conf',
            '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup_aio_3_disks.conf'

        ],
        'config': '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_build/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/TiS_config.ini_centos'
    }
    R4 = {
        'setup': [
            '/localdisk/designer/jenkins/TC_17.06_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/designer/jenkins/TC_17.06_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/designer/jenkins/TC_17.06_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf'
        ],
        'config': "/localdisk/designer/jenkins/CGCS_4.0_Centos_Pull_CGCS_DEV_0027/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/system_config.centos"
    }
    R3 = {
        'setup': [
            '/localdisk/designer/jenkins/TS_16.10_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/designer/jenkins/TS_16.10_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/designer/jenkins/TS_16.10_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf'
        ],
        'config': "/localdisk/designer/jenkins/CGCS_3.0_Centos_Pull_CGCS_DEV_0019/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/system_config.centos" 
    }
    R2 = {
        'setup': [
            '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/export/lab/scripts/lab_setup.sh',
            '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/export/lab/scripts/lab_cleanup.sh',
            '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/export/lab/yow/cgcs-vbox/lab_setup.conf'
        ],
        'config': "/localdisk/designer/jenkins/TS_15.12_Pull/wrlinux-x/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/system_config"
    }
