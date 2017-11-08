ISOPATH = "/tmp/bootimage.iso"

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
    R5 = {
        'release': 'R5',
        'iso': '/localdisk/loadbuild/jenkins/CGCS_5.0_Host/latest_bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/CGCS_5.0_Guest/latest_tis-centos-guest.img'
    }

    R4 = {
        'release': 'R4',
        'iso': '/localdisk/loadbuild/jenkins/TC_17.06_Host/latest_bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/TC_17.06_Guest/latest_tis-centos-guest.img',
        'patches': '/folk/cgts/rel-ops/17.06/patches'
    }

    R3 = {
        'release': 'R3',
        'iso': '/localdisk/loadbuild/jenkins/TS_16.10_Host/respun-GA/export/bootimage.iso', 
        'guest': '/localdisk/loadbuild/jenkins/CGCS_3.0_Guest_Daily_Build/cgcs-guest.img', 
        'patches': '/folk/cgts/rel-ops/16.10/patches'
    }

    R2 = {
        'release': 'R2',
        'iso': '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_bootimage.iso',
        'guest': '/localdisk/loadbuild/jenkins/TS_15.12_Guest/cgcs-guest.img',
        'patches': '/folk/cgts/rel-ops/15.12/patches'
    }

class Licenses:
    R2 = {
        'AIO': '/folk/cgts/lab/licenses/wrslicense-CPE-15.12-full-jan2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-15.12-full-jan2018.lic'
    }

    R3 = {
        'AIO': '/folk/cgts/lab/licenses/wrslicense-CPE-16.10-full-jan2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-16.10-full-jan2018.lic'
    }

    R4 = {
        'AIO-SX': '/folk/cgts/lab/licenses/wrslicense-AIO-SX-17.06-full-jan2018.lic',
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-CPE-17.06-full-jan2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-17.06-full-jan2018.lic'
    }

    R5 = {
        'AIO-SX': '/folk/cgts/lab/licenses/wrslicense-AIO-SX-R5-full-jan2018.lic',
        'AIO-DX': '/folk/cgts/lab/licenses/wrslicense-AIO-DX-R5-full-jan2018.lic',
        'Standard': '/folk/cgts/lab/licenses/wrslicense-R5-full-jan2018.lic'
    }


class Lab:
    VBOX = {
        'short_name': 'vbox',
        'name': 'vbox',
        'floating_ip': '10.10.10.3',
        'controller-0_ip': '10.10.10.1',
        'controller-1_ip': '10.10.10.2',
        'username': 'wrsroot',
        'password': 'Li69nux*',
    }

class Files:
    R5={
        'setup': [
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf',
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/iptables.rules',
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-tenant2-resources.yaml',
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-tenant1-resources.yaml',
            '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup-admin-resources.yaml'
        ],
        'config': '/localdisk/designer/jenkins/CGCS_5.0_Pull_CGCS_DEV_0030/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/'
    }

    R4 = {
        'setup': [
            '/localdisk/designer/jenkins/TC_17.06_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/designer/jenkins/TC_17.06_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/designer/jenkins/TC_17.06_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf'
        ]
    }
    R3 = {
        'setup': [
            '/localdisk/designer/jenkins/TS_16.10_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_setup.sh',
            '/localdisk/designer/jenkins/TS_16.10_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/scripts/lab_cleanup.sh',
            '/localdisk/designer/jenkins/TS_16.10_Pull/cgcs-root/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/cgcs-vbox/lab_setup.conf'
        ]
    }
    R2 = {
        'setup': [
            '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/export/lab/scripts/lab_setup.sh',
            '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/export/lab/scripts/lab_cleanup.sh',
            '/localdisk/loadbuild/jenkins/TS_15.12_Host/latest_build/export/lab/yow/cgcs-vbox/lab_setup.conf'
        ]
    }
    FILENAMES = {
        'R5':  {
            'setup': ['lab_cleanup.sh',
                      'lab_setup.sh',
                      'lab_setup.conf',
                      'iptables.rules',
                      'lab_setup-tenant2-resources.yaml',
                      'lab_setup-tenant1-resources.yaml',
                      'lab_setup-admin-resources.yaml'],
            'config': 'TiS_config.ini_centos',
            'guest': 'tis-centos-guest.img',
            'licence': 'licence.lic'},
        'R4':  {
            'setup': ['lab_cleanup.sh',
                      'lab_setup.sh',
                      'lab_setup.conf',
                      'iptables.rules'],
            'config': 'TiS_config.ini_centos',
            'guest': 'tis-centos-guest.img',
            'licence': 'licence.lic'},
        'R3':  {
            'setup': ['lab_cleanup.sh',
                      'lab_setup.sh',
                      'lab_setup.conf',
                      'iptables.rules'],
            'config': 'TiS_config.ini_centos',
            'guest': 'tis-centos-guest.img',
            'licence': 'licence.lic'},
        'R2':  {
            'setup': ['lab_cleanup.sh',
                      'lab_setup.sh',
                      'lab_setup.conf',
                      'iptables.rules'],
            'config': 'TiS_config.ini_centos',
            'guest': 'tis-centos-guest.img',
            'licence': 'licence.lic'},
        }
    PATCHES = {
        'R5':'/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build/latest_build/',
        'R4':'/localdisk/loadbuild/jenkins/TC_17.06_Test_Patch_Build/latest_build/',
        'R3':'/localdisk/loadbuild/jenkins/TS_16.10_Patch_Formal_Build/export/patch_data/',
        'R2':''
    }