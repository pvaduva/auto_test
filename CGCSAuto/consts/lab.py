# hosts_bulk_add, lab_setup, tis_config will be added to each lab dictionary when initializing install test


class Labs:
    HP380 = {
        'short_name': 'hp380',
        'name': 'yow-cgcs-hp380-1_4',
        'floating ip': '128.224.150.189',
        'controller-0 ip': '128.224.150.199',
        'controller-1 ip': '128.224.150.129',
        # 'auth_url': 'http://192.168.204.102:5000/v3/',
        'controller_nodes': [21768, 21769],
        'compute_nodes': [21770, 21771],
    }

    IP_1_4 = {
        'short_name': 'ip_1_4',
        'name': 'yow-cgcs-ironpass-1_4',
        'floating ip': '128.224.151.212',
        'controller-0 ip': '128.224.151.192',
        'controller-1 ip': '128.224.151.193',
        # 'auth_url': 'http://192.168.204.2:5000/v3/',
        'controller_nodes': [20519, 20520],
        'compute_nodes': [20521, 20522],
    }

    IP_5_6 = {
        'short_name': 'ip_5_6',
        'name': 'yow-cgcs-ironpass-5_6',
        'floating ip': '128.224.151.216',
        'controller-0 ip': '128.224.151.196',
        'controller-1 ip': '128.224.151.197',
        # 'auth_url': 'http://192.168.204.2:5000/v3/',
        'controller_nodes': [20525, 20526],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    IP_7_12 = {
        'short_name': 'ip_7_12',
        'name': 'yow-cgcs-ironpass-7_12',
        'floating ip': '128.224.151.243',
        'controller-0 ip': '128.224.151.244',
        'controller-1 ip': '128.224.150.205',
        'controller_nodes': [21786, 21788],
        'compute_nodes': [21789, 21791],
        'storage_nodes': [21790, 21787]
    }

    IP_14_17 = {
        'short_name': 'ip_14_17',
        'name': 'yow-cgcs-ironpass-14_17',
        'floating ip': '128.224.150.54',
        'controller-0 ip': '128.224.150.219',
        'controller-1 ip': '128.224.150.212',
        'controller_nodes': [23527, 22348],
        'compute_nodes': [22347, 21784],
    }

    IP_18_19 = {
        'short_name': 'ip_18_19',
        'name': 'yow-cgcs-ironpass-18_19',
        'floating ip': '128.224.150.158',
        'controller-0 ip': '128.224.150.168',
        'controller-1 ip': '128.224.150.169',
        'controller_nodes': [22354, 22357],
        'compute_nodes': [22431, 22432, 22433, 22434],
    }

    IP_20_27 = {
        'short_name': 'ip_20_27',
        'name': 'yow-cgcs-ironpass-20_27',
        'floating ip': '128.224.151.49',
        'controller-0 ip': '128.224.151.47',
        'controller-1 ip': '128.224.151.48',
        'controller_nodes': [18541, 21758],
        'compute_nodes': [22417, 22418, 21762, 18537],
        'storage_nodes': [18536, 18551],
    }

    IP_28_30 = {
        'short_name': 'ip_28_30',
        'name': 'yow-cgcs-ironpass-28_30',
        'floating ip': '128.224.150.188',
        'controller-0 ip': '128.224.150.223',
        'controller-1 ip': '128.224.150.179',
        'controller_nodes': [20559],
        'compute_nodes': [20516, 21710],
    }

    IP_31_32 = {
        'short_name': 'ip_31_32',
        'name': 'yow-cgcs-ironpass-31_32',
        'floating ip': '128.224.150.96',
        'controller-0 ip': '128.224.150.92',
        'controller-1 ip': '128.224.150.22',
        'controller_nodes': [21750, 21758],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    IP_33_36 = {
        'short_name': 'ip_33_36',
        'name': 'yow-cgcs-ironpass-33_36',
        'floating ip': '128.224.150.215',
        'controller-0 ip': '128.224.150.32',
        'controller-1 ip': '128.224.151.148',
        'controller_nodes': [20509, 20550],
        'compute_nodes': [21720, 21721]
    }

    IP_37_40 = {
        'short_name': 'ip_37_40',
        'name': 'yow-cgcs-ironpass-37_40',
        'floating ip': '128.224.150.89',
        'controller-0 ip': '128.224.150.175',
        'controller-1 ip': '128.224.150.93',
        'controller_nodes': [20551, 21778],
        'compute_nodes': [21723, 22487]
    }

    PV0 = {
        'short_name': 'pv0',
        'name': 'yow-cgcs-pv-0',
        'floating ip': '128.224.150.73',
        'controller-0 ip': '128.224.150.26',
        'controller-1 ip': '128.224.150.28',
        # 'auth_url': 'http://192.168.204.2:5000/v3/',
        'controller_nodes': [22715, 22716],
        'compute_nodes': [22719, 22720, 23915, 22722],
        'storage_nodes': [23954, 23955, 23916, 22717, 22718, 22721],
    }

    PV1 = {
        'short_name': 'pv1',
        'name': 'yow-cgcs-pv-1',
        'floating ip': '128.224.151.182',
        'controller-0 ip': '128.224.151.198',
        'controller-1 ip': '128.224.151.199',
        'controller_nodes': [23136, 23138],
        'compute_nodes': [23135, 23137, 23140, 23143, 23139, 23141, 23142, 23096],
        'storage_nodes': [23146, 23147],
        'tpm_installed': True,
    }

    PV1_2 = {
        'short_name': 'pv1_2',
        'name': 'yow-cgcs-pv-1_2',
        'floating ip': '128.224.151.182',
        'controller-0 ip': '128.224.151.198',
        'controller-1 ip': '128.224.151.199',
        'controller_nodes': [23136, 23138],
        'compute_nodes': [23135, 23137, 23140, 23143, 23139, 23141, 23142, 23146, 23147, 23096]
    }

    PV2 = {
        'short_name': 'pv2',
        'name': 'yow-cgcs-pv-2',
        'floating ip': '128.224.151.225',
        'controller-0 ip': '128.224.151.223',
        'controller-1 ip': '128.224.151.224',
    }

    R720_1_2 = {
        'short_name': 'r720_1_2',
        'name': 'yow-cgcs-r720-1_2',
        'floating ip': '128.224.150.141',
        'controller-0 ip': '128.224.150.130',
        'controller-1 ip': '128.224.150.106',
        # 'controller_nodes': [22351, 22352],
        'controller_nodes': [22352, 22351],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    R720_3_7 = {
        'short_name': 'r720_3_7',
        'name': 'yow-cgcs-r720-3_7',
        'floating ip': '128.224.150.142',
        'controller-0 ip': '128.224.151.35',
        'controller-1 ip': '128.224.151.36',
        'controller_nodes': [21805, 21806],
        'compute_nodes': [21763, 21764, 21765],
    }

    R730_1 = {
        'short_name': 'r730_1',
        'name': 'yow-cgcs-r730-1',
        'floating ip': '128.224.150.121',
        'controller-0 ip': '128.224.150.121',
        'controller_nodes': [67160],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    R430_1_2 = {
        'short_name': 'r430_1_2',
        'name': 'yow-cgcs-r430-1_2',
        'floating ip': '128.224.150.49',
        'controller-0 ip': '128.224.150.48',
        'controller-1 ip': '128.224.150.52',
        'controller_nodes': [23512, 23513],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'tpm_installed': True,
    }
    
    R430_3_4 = {
        'short_name': 'r430_3_4',
        'name': 'yow-cgcs-r430-3_4',
        'floating ip': '128.224.150.11',
        'controller-0 ip': '128.224.150.8',
        'controller-1 ip': '128.224.150.9',
        'controller_nodes': [32077, 71451],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    SM_1 = {
        'short_name': 'sm_1',
        'name': 'yow-cgcs-supermicro-1',
        'floating ip': '128.224.150.221',
        'controller-0 ip': '128.224.150.221',
        'controller_nodes': [46808],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    SM_2 = {
        'short_name': 'sm_2',
        'name': 'yow-cgcs-supermicro-2',
        'floating ip': '128.224.150.222',
        'controller-0 ip': '128.224.150.222',
        'controller_nodes': [23907],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    SM_3 = {
        'short_name': 'sm_3',
        'name': 'yow-cgcs-supermicro-3',
        'floating ip': '128.224.150.81',
        'controller-0 ip': '128.224.150.81',
        'controller_nodes': [23514],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    SM_4 = {
        'short_name': 'sm_4',
        'name': 'yow-cgcs-supermicro-4',
        'floating ip': '128.224.150.83',
        'controller-0 ip': '128.224.150.83',
        'controller_nodes': [23515],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    SM_5_6 = {
        'short_name': 'sm_5_6',
        'name': 'yow-cgcs-supermicro-5-6',
        'floating ip': '128.224.151.54',
        'controller-0 ip': '128.224.150.84',
        'controller-1 ip': '128.224.150.56',
        'controller_nodes': [23516, 23517],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    WCP_3_6 = {
        'short_name': 'wcp_3_6',
        'name': 'yow-cgcs-wildcat-3_6',
        'floating ip': '128.224.151.227',
        'controller-0 ip': '128.224.150.69',
        'controller-1 ip': '128.224.150.70',
        'controller_nodes': [23198, 23199],
        'compute_nodes': [23200, 23201],
    }

    WCP_7_12 = {
        'short_name': 'wcp_7_12',
        'name': 'yow-cgcs-wildcat-7_12',
        'floating ip': '128.224.151.228',
        'controller-0 ip': '128.224.150.220',
        'controller-1 ip': '128.224.150.231',
        # 'auth_url': 'http://192.168.144.2:5000/v2.0/',
        'controller_nodes': [23202, 23203],
        'compute_nodes': [23206, 23207],
        'storage_nodes': [23204, 23205],
    }

    WCP_13_14 = {
        'short_name': 'wcp_13_14',
        'name': 'yow-cgcs-wildcat-13_14',
        'floating ip': '128.224.151.229',
        'controller-0 ip': '128.224.150.133',
        'controller-1 ip': '128.224.150.136',
        'controller_nodes': [23213, 23214],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    WCP_13 = {
        'short_name': 'wcp_13',
        'name': 'yow-cgcs-wildcat-13',
        'floating ip': '128.224.151.229',
        'controller-0 ip': '128.224.150.133',
        'controller_nodes': [23213],
    }

    WCP_14 = {
        'short_name': 'wcp_14',
        'name': 'yow-cgcs-wildcat-14',
        'floating ip': '128.224.151.217',
        'controller-0 ip': '128.224.150.136',
        'controller_nodes': [23214],
    }

    WCP_15_22 = {
        'short_name': 'wcp_15_22',
        'name': 'yow-cgcs-wildcat-15_22',
        'floating ip': '128.224.151.230',
        'controller-0 ip': '128.224.150.140',
        'controller-1 ip': '128.224.150.180',
        # 'auth_url': 'http://192.168.204.102:5000/v2.0/',
        'controller_nodes': [23215, 23216],
        'compute_nodes': [23219, 23220, 23221, 23222],
        'storage_nodes': [23217, 23218]
    }

    WCP_35_60 = {
        'short_name': 'wcp_35_60',
        'name': 'yow-cgcs-wildcat-35_60',
        'floating ip': '128.224.150.234',
        'controller-0 ip': '128.224.150.232',
        'controller-1 ip': '128.224.150.233',
        'controller_nodes': [23268, 23267],
        'compute_nodes': [23258, 23257, 23256, 23255, 23254, 23253, 23252, 23251,
                          23250, 23249, 23248, 23247, 23246, 23245, 23244, 23243,
                          23262, 23261, 23260, 23259],
        'storage_nodes': [23264, 23263, 23266, 23265],
    }

    WCP_61_62 = {
        'short_name': 'wcp_61_62',
        'name': 'yow-cgcs-wildcat-61_62',
        'floating ip': '128.224.151.82',
        'controller-0 ip': '128.224.151.80',
        'controller-1 ip': '128.224.151.81',
        'controller_nodes': [23280, 23281],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    WCP_63_66 = {
        'short_name': 'wcp_63_66',
        'name': 'yow-cgcs-wildcat-63_66',
        'floating ip': '128.224.151.85',
        'controller-0 ip': '128.224.151.83',
        'controller-1 ip': '128.224.151.84',
        'controller_nodes': [23282, 23283],
        'compute_nodes': [23284, 23285],
        'tpm_installed': True,
    }

    WCP_67 = {
        'short_name': 'wcp_67',
        'name': 'yow-cgcs-wildcat-67',
        'floating ip': '128.224.151.33',
        'auth_url': 'http://127.168.204.2:5000/v3/',
        'controller-0 ip': '128.224.151.33',
        'controller_nodes': [23286],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WCP_68 = {
        'short_name': 'wcp_68',
        'name': 'yow-cgcs-wildcat-68',
        'floating ip': '128.224.151.38',
        'auth_url': 'http://127.168.204.2:5000/v3/',
        'controller-0 ip': '128.224.151.38',
        'controller_nodes': [23287],
        'system_type': 'CPE',
        'system_mode': 'simplex',
        'tpm_installed': True,
    }

    WCP_69_70 = {
        'short_name': 'wcp_69_70',
        'name': 'yow-cgcs-wildcat-69_70',
        'floating ip': '128.224.151.241',
        'controller-0 ip': '128.224.151.240',
        'controller-1 ip': '128.224.151.253',
        'controller_nodes': [23288, 23289],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'tpm_installed': True,
    }

    WCP_71_75 = {
        'short_name': 'wcp_71_75',
        'name': 'yow-cgcs-wildcat-71_75',
        'floating ip': '128.224.151.218',
        'controller-0 ip': '128.224.151.215',
        'controller-1 ip': '128.224.151.24',
        'controller_nodes': [23271, 23272],
        'compute_nodes': [23273, 23274, 23275],
        'tpm_installed': True,
    }

    WCP_76_77 = {
        'short_name': 'wcp_76_77',
        'name': 'yow-cgcs-wildcat-76_77',
        'floating ip': '128.224.150.5',
        'controller-0 ip': '128.224.150.3',
        'controller-1 ip': '128.224.150.4',
        'controller_nodes': [23276, 23277],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'tpm_installed': True,
    }

    WCP_78_79 = {
        'short_name': 'wcp_78_79',
        'name': 'yow-cgcs-wildcat-78_79',
        'floating ip': '128.224.151.237',
        'controller-0 ip': '128.224.151.235',
        'controller-1 ip': '128.224.151.236',
        'controller_nodes': [23278, 23279],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'tpm_installed': True,
    }

    WCP_80_84 = {
        'short_name': 'wcp_80_84',
        'name': 'yow-cgcs-wildcat-80_84',
        'floating ip': '128.224.150.18',
        'controller-0 ip': '128.224.150.14',
        'controller-1 ip': '128.224.150.156',
        'controller_nodes': [23318, 23319],
        'compute_nodes': [23320, 23321, 23322],
    }

    WCP_85_89 = {
        'short_name': 'wcp_85_89',
        'name': 'yow-cgcs-wildcat-85_89',
        'floating ip': '128.224.150.224',
        'controller-0 ip': '128.224.150.244',
        'controller-1 ip': '128.224.150.202',
        'controller_nodes': [23323, 23324],
        'compute_nodes': [23325, 23326, 23327],
    }

    WCP_90_91 = {
        'short_name': 'wcp_90_91',
        'name': 'yow-cgcs-wildcat-90_91',
        'floating ip': '128.224.151.162',
        'controller-0 ip': '128.224.151.151',
        'controller-1 ip': '128.224.151.153',
        'controller_nodes': [23328, 23329],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'tpm_installed': True,
    }

    WCP_92_98 = {
        'short_name': 'wcp_92_98',
        'name': 'yow-cgcs-wildcat-92_98',
        'floating ip': '128.224.151.15',
        'controller-0 ip': '128.224.151.111',
        'controller-1 ip': '128.224.151.205',
        'controller_nodes': [23299, 23300],
        'compute_nodes': [23303, 23304, 23305],
        'storage_nodes': [23301, 23302],
    }

    WCP_99_103 = {
        'short_name': 'wcp_99_103',
        'name': 'yow-cgcs-wildcat-99_103',
        'floating ip': '128.224.151.94',
        'controller-0 ip': '128.224.151.11',
        'controller-1 ip': '128.224.151.13',
        'controller_nodes': [23312, 23313],
        'compute_nodes': [23314, 23315, 23316],
        'tpm_installed': True,
    }

    WCP_113_121 = {
        'short_name': 'wcp_113_121',
        'name': 'yow-cgcs-wildcat-113-121',
        'floating ip': '128.224.150.45',
        'controller-0 ip': '128.224.150.191',
        'controller-1 ip': '128.224.150.57',

    }

    WP_01_02 = {
        'short_name': 'wp_1_2',
        'name': 'yow-cgcs-wolfpass-01_02',
        'floating ip': '128.224.150.254',
        'controller-0 ip': '128.224.150.155',
        'controller-1 ip': '128.224.150.198',
        'controller_nodes': [62031, 29957],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    WP_03_07 = {
        'short_name': 'wp_3_7',
        'name': 'yow-cgcs-wolfpass-03_07',
        'floating ip': '128.224.151.165',
        'controller-0 ip': '128.224.151.163',
        'controller-1 ip': '128.224.151.166',
        'controller_nodes': [98522, 81712],
        'compute_nodes': [94867, 18658, 40810],
    }

    WCP_113_121 = {
        'short_name': 'wcp_113_121',
        'name': 'yow-cgcs-wildcat-113_121',
        'floating ip': '128.224.150.45',
        'controller-0 ip': '128.224.150.191',
        'controller-1 ip': '128.224.150.57',
        'controller_nodes': [31701, 19174],
        'compute_nodes': [11182, 47720, 56027, 28212, 33598],
        'storage_nodes': [11507, 47400],
    }

    VBOX = {
        'short_name': 'vbox',
        'name': 'vbox',
        'floating ip': '10.10.10.2',
        'controller-0 ip': '10.10.10.3',
        'controller-1 ip': '10.10.10.4',
        'controller_nodes': [0, 1],
        'compute_nodes': [0, 1]
    }

    VBOX_1 = {
        'short_name': 'vbox_1',
        'name': 'yow-cgcs-vbox-1',
        'floating ip': '10.10.10.2',
        'controller-0 ip': '10.10.10.3',
        'controller-1 ip': '10.10.10.4',
        'controller_nodes': [0, 1],
        'compute_nodes': [0, 1]
    }

    VBOX_2 = {
        'short_name': 'vbox_2',
        'name': 'yow-cgcs-vbox-2',
        'floating ip': '10.10.10.5',
        'controller-0 ip': '10.10.10.6',
        'controller-1 ip': '10.10.10.7',
        'controller_nodes': [0, 1],
        'compute_nodes': [0, 1],
        'storage_nodes': [0, 1]
    }

    VBOX_3 = {
        'short_name': 'vbox_3',
        'name': 'yow-cgcs-vbox-3',
        'floating ip': '10.10.10.8',
        'controller-0 ip': '10.10.10.9',
        'controller-1 ip': '10.10.10.10',
        'controller_nodes': [0, 1],
        'compute_nodes': [0, 1],
    }

    VBOX_4 = {
        'short_name': 'vbox_4',
        'name': 'yow-cgcs-vbox-4',
        'floating ip': '10.10.10.11',
        'controller-0 ip': '10.10.10.12',
        'controller-1 ip': '10.10.10.13',
        'controller_nodes': [0, 1],
    }

    LARGE_OFFICE = {
        'short_name': 'large_office',
        'name': 'large office',
        'floating ip': '',
        'controller-0 ip': ''
    }

    UNKNOWN = {
        'short_name': 'unknown',
        'name': 'unknown',
        'floating ip': 'unknow_fip',
        'controller-0 ip': 'unknown_con0_ip',
        'controller-1 ip': 'unknown_con1_ip',
    }

    NO_LAB = None


def edit_lab_entry():
    # TODO
    raise NotImplementedError


def add_lab_entry(floating_ip, dict_name=None, short_name=None, name=None, **kwargs):
    """
    Add a new lab dictionary to Labs class
    Args:
        floating_ip (str): floating ip of a lab to be added
        dict_name: name of the entry, such as 'PV0'
        short_name: short name of the TiS system, such as ip_1_4
        name: name of the TiS system, such as 'yow-cgcs-pv-0'
        **kwargs: other information of the lab such as controllers' ips, etc

    Returns:
        dict: lab dict added to Labs class

    """
    for attr in dir(Labs):
        lab = getattr(Labs, attr)
        if isinstance(lab, dict):
            if lab['floating ip'] == floating_ip:
                raise ValueError("Entry for {} already exists in Labs class!".format(floating_ip))

    if dict_name and dict_name in dir(Labs):
        raise ValueError("Entry for {} already exists in Labs class!".format(dict_name))

    if not short_name:
        short_name = floating_ip

    if not name:
        name = floating_ip

    if not dict_name:
        dict_name = floating_ip

    lab_dict = {'name': name,
                'short_name': short_name,
                'floating ip': floating_ip,
                }

    lab_dict.update(kwargs)
    setattr(Labs, dict_name, lab_dict)
    return lab_dict


class NatBoxes:
    # NAT_BOX_HW = {
    #     'name': 'nat_hw',
    #     'ip': '128.224.150.11',
    #     'user': 'cgcs',
    #     'password': 'li69nux'
    # }
    NAT_BOX_HW = {
        'name': 'nat_hw',
        'ip': '128.224.186.181',
        'user': 'svc-cgcsauto',
        'password': ')OKM0okm'
    }

    NAT_BOX_CUMULUS = {
        'name': 'nat_cumulus',
        'ip': '',
        'user': '',
        'password': ''
    }

    # Assume vbox NatBox is
    NAT_BOX_VBOX = {
        'name': 'localhost',
        'ip': 'localhost',
        'user': None,
        'password': None,
    }

    @staticmethod
    def add_natbox(ip, user='svc-cgcsauto', password=')OKM0okm'):
        # this only supports svc-cgcsauto user from cgts group for now
        nat_dict = {'ip': ip,
                    'name': ip,
                    'user': user,
                    'password': password,
                    }
        setattr(NatBoxes, 'NAT_NEW', nat_dict)
        return nat_dict
