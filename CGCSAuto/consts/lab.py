#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#


class Labs:
    HP380 = {
        'short_name': 'hp380',
        'name': 'yow-cgcs-hp380-1_4',
        'floating ip': '128.224.150.189',
        'controller-0 ip': '128.224.150.199',
        'controller-1 ip': '128.224.150.129',
        'controller_nodes': [21768, 21769],
        'compute_nodes': [21770, 21771],
        'ixia_ports': [{'port': (3, 15), 'range': (504, 535)},
                       {'port': (3, 16), 'range': (536, 567)}],
        'default_pxe_menu': [4]
    }

    IP_1_4 = {
        'short_name': 'ip_1_4',
        'name': 'yow-cgcs-ironpass-1_4',
        'floating ip': '128.224.151.212',
        'controller-0 ip': '128.224.151.192',
        'controller-1 ip': '128.224.151.193',
        'controller_nodes': [20519, 20520],
        'compute_nodes': [20521, 20522],
        'ixia_ports': [{'port': (3, 9), 'range': (600, 615)},
                       {'port': (3, 10), 'range': (700, 715)}],
    }

    IP_5_6 = {
        'short_name': 'ip_5_6',
        'name': 'yow-cgcs-ironpass-5_6',
        'floating ip': '128.224.151.216',
        'controller-0 ip': '128.224.151.196',
        'controller-1 ip': '128.224.151.197',
        'controller_nodes': [20525, 20526],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'ixia_ports': [{'port': (3, 7), 'range': (764, 773)},
                       {'port': (3, 8), 'range': (774, 783)}],
    }

    IP_7_12 = {
        'short_name': 'ip_7_12',
        'name': 'yow-cgcs-ironpass-7_12',
        'floating ip': '128.224.151.243',
        'controller-0 ip': '128.224.151.244',
        'controller-1 ip': '128.224.150.205',
        'controller_nodes': [21786, 21788],
        'compute_nodes': [21789, 21791],
        'storage_nodes': [21790, 21787],
        'ixia_ports': [{'port': (3, 3), 'range': (632, 663)},
                       {'port': (3, 4), 'range': (664, 695)}],
    }

    IP_14_17 = {
        'short_name': 'ip_14_17',
        'name': 'yow-cgcs-ironpass-14_17',
        'floating ip': '128.224.150.54',
        'controller-0 ip': '128.224.150.219',
        'controller-1 ip': '128.224.150.212',
        'controller_nodes': [23527, 22348],
        'compute_nodes': [22347, 21784],
        'ixia_ports': [{'port': (3, 11), 'range': (860, 891)},
                       {'port': (3, 12), 'range': (892, 923)}],
    }

    IP_18_19 = {
        'short_name': 'ip_18_19',
        'name': 'yow-cgcs-ironpass-18_19',
        'floating ip': '128.224.150.158',
        'controller-0 ip': '128.224.150.168',
        'controller-1 ip': '128.224.150.169',
        'controller_nodes': [22354, 22357],
        'compute_nodes': [22431, 22432, 22433, 22434],
        'ixia_ports': [{'port': (2, 5), 'range': (1210, 1259)},
                       {'port': (2, 6), 'range': (1260, 1309)}],
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
        'ixia_ports': [{'port': (2, 9), 'range': (1460, 1509)},
                       {'port': (2, 10), 'range': (1560, 1609)}],
    }

    IP_28_30 = {
        'short_name': 'ip_28_30',
        'name': 'yow-cgcs-ironpass-28_30',
        'floating ip': '128.224.150.188',
        'controller-0 ip': '128.224.150.223',
        'controller-1 ip': '128.224.150.179',
        'controller_nodes': [20559],
        'compute_nodes': [20516, 21710],
        'ixia_ports': [{'port': (5, 9), 'range': (2902, 2933)},
                       {'port': (5, 10), 'range': (2966, 3001)}],
    }

    IP_31_32 = {
        'short_name': 'ip_31_32',
        'name': 'yow-cgcs-ironpass-31_32',
        'floating ip': '128.224.150.96',
        'controller-0 ip': '128.224.150.92',
        'controller-1 ip': '128.224.150.22',
        'controller_nodes': [21750, 23964],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'ixia_ports': [{'port': (6, 1), 'range': (1952, 2001)},
                       {'port': (6, 2), 'range': (2002, 2051)}],
    }

    IP_33_36 = {
        'short_name': 'ip_33_36',
        'name': 'yow-cgcs-ironpass-33_36',
        'floating ip': '128.224.150.215',
        'controller-0 ip': '128.224.150.32',
        'controller-1 ip': '128.224.151.148',
        'controller_nodes': [20509, 20550],
        'compute_nodes': [21720, 21721],
        'ixia_ports': [{'port': (6, 3), 'range': (2052, 2101)},

                       {'port': (6, 4), 'range': (2102, 2151)}],
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

    ML350_1 = {
        'short_name': 'ml350_1',
        'name': 'yow-cgcs-ml350-g10-1',
        'floating ip': '128.224.151.181',
        'controller-0 ip': '128.224.151.181',
        'controller_nodes': [55836],
    }

    PV0 = {
        'short_name': 'pv0',
        'name': 'yow-cgcs-pv-0',
        'floating ip': '128.224.150.73',
        'controller-0 ip': '128.224.150.26',
        'controller-1 ip': '128.224.150.28',
        'controller_nodes': [22715, 22716],
        'compute_nodes': [22719, 22720, 23915, 22722],
        'storage_nodes': [23954, 23955, 23916, 22717, 22718, 22721],
        'ixia_ports': [{'port': (5, 1), 'range': (1852, 1884)},
                       {'port': (5, 2), 'range': (1918, 1951)}],
        'default_pxe_menu': [2]
    }

    PV0_AIO_Plus = {
        'short_name': 'pv0_aio_plus',
        'name': 'yow-cgcs-pv-0-aio_plus',
        'floating ip': '128.224.150.73',
        'controller-0 ip': '128.224.150.26',
        'controller-1 ip': '128.224.150.28',
        'controller_nodes': [22715, 22716],
        'system_type': 'AIO_PLUS',
        'system_mode': 'duplex',
        'compute_nodes': [22719, 22720, 23915, 22722],
        'unused_nodes': [23954, 23955, 23916, 22717, 22718, 22721],
        'ixia_ports': [{'port': (5, 1), 'range': (1852, 1884)},
                       {'port': (5, 2), 'range': (1918, 1951)}],
        'default_pxe_menu': [4]
    }

    PV0_AIO_Plus_10 = {
        'short_name': 'pv0_aio_plus_10',
        'name': 'yow-cgcs-pv-0-aio_plus_10',
        'floating ip': '128.224.150.73',
        'controller-0 ip': '128.224.150.26',
        'controller-1 ip': '128.224.150.28',
        'controller_nodes': [22715, 22716],
        'system_type': 'AIO_PLUS',
        'system_mode': 'duplex',
        'compute_nodes': [22719, 22720, 23915, 22722, 23954, 23955, 23916, 22717, 22718, 22721],
        'ixia_ports': [{'port': (5, 1), 'range': (1852, 1884)},
                       {'port': (5, 2), 'range': (1918, 1951)}],
        'default_pxe_menu': [4]
    }

    PV1 = {
        'short_name': 'pv1',
        'name': 'yow-cgcs-pv-1',
        'floating ip': '128.224.151.182',
        'controller-0 ip': '128.224.151.198',
        'controller-1 ip': '128.224.151.199',
        'controller_nodes': [23136, 23138],
        'compute_nodes': [23147, 23146, 23140, 23143, 23139, 23141, 23142,
                          23096],
        'storage_nodes': [23135, 23137],
        'tpm_installed': True,
    }

    PV1_2 = {
        'short_name': 'pv1_2',
        'name': 'yow-cgcs-pv-1_2',
        'floating ip': '128.224.151.182',
        'controller-0 ip': '128.224.151.198',
        'controller-1 ip': '128.224.151.199',
        'controller_nodes': [23136, 23138],
        'compute_nodes': [23135, 23137, 23140, 23143, 23139, 23141, 23142,
                          23146, 23147, 23096]
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
        'ixia_ports': [{'port': (2, 11), 'range': (1660, 1691)},
                       {'port': (2, 12), 'range': (1724, 1755)}],
    }

    R720_3_7 = {
        'short_name': 'r720_3_7',
        'name': 'yow-cgcs-r720-3_7',
        'floating ip': '128.224.150.142',
        'controller-0 ip': '128.224.151.35',
        'controller-1 ip': '128.224.151.36',
        'controller_nodes': [21805, 21806],
        'compute_nodes': [21763, 21764, 21765],
        'ixia_ports': [{'port': (2, 13), 'range': (1756, 1787)},
                       {'port': (2, 14), 'range': (1820, 1851)}],
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
        'ixia_ports': [{'port': (2, 7), 'range': (3002, 3151)}],
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
        'ixia_ports': [{'port': (1, 1), 'range': (600, 633)},
                       {'port': (1, 2), 'range': (667, 699)}],
    }

    SM_2 = {
        'short_name': 'sm_2',
        'name': 'yow-cgcs-supermicro-2',
        'floating ip': '128.224.150.222',
        'controller-0 ip': '128.224.150.222',
        'controller_nodes': [23907],
        'system_type': 'CPE',
        'system_mode': 'simplex',
        'ixia_ports': [{'port': (1, 3), 'range': (734, 766)},
                       {'port': (1, 4), 'range': (767, 799)}],
    }

    SM_3 = {
        'short_name': 'sm_3',
        'name': 'yow-cgcs-supermicro-3',
        'floating ip': '128.224.150.81',
        'controller-0 ip': '128.224.150.81',
        'controller_nodes': [23514],
        'system_type': 'CPE',
        'system_mode': 'simplex',
        'ixia_ports': [{'port': (6, 9), 'range': (600, 649)},
                       {'port': (6, 10), 'range': (700, 749)}],
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
        'name': 'yow-cgcs-supermicro-5_6',
        'floating ip': '128.224.151.54',
        'controller-0 ip': '128.224.150.84',
        'controller-1 ip': '128.224.150.56',
        'controller_nodes': [23516, 23517],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    SM_5_8 = {
        'short_name': 'sm_5_8',
        'name': 'yow-cgcs-supermicro-5_8',
        'floating ip': '128.224.151.54',
        'controller-0 ip': '128.224.150.84',
        'controller-1 ip': '128.224.150.56',
        'controller_nodes': [23516, 23517],
        'compute_nodes': [38294],
    }

    WCP_3_6 = {
        'short_name': 'wcp_3_6',
        'name': 'yow-cgcs-wildcat-3_6',
        'floating ip': '128.224.151.227',
        'controller-0 ip': '128.224.150.69',
        'controller-1 ip': '128.224.150.70',
        'controller_nodes': [23198, 23199],
        'compute_nodes': [23200, 23201],
        'ixia_ports': [{'port': (5, 5), 'range': (2252, 2284)},
                       {'port': (5, 6), 'range': (2318, 2350)}],
    }

    WCP_7_10 = {
        'short_name': 'wcp_7_10',
        'name': 'yow-cgcs-wildcat-7_10',
        'floating ip': '128.224.151.228',
        'controller-0 ip': '128.224.150.220',
        'controller-1 ip': '128.224.150.231',
        'controller_nodes': [23202, 23203],
        'compute_nodes': [23204, 23205],
        'ixia_ports': [{'port': (5, 11), 'range': (2352, 2384)},
                       {'port': (5, 12), 'range': (2418, 2451)}],
    }

    WCP_11 = {
        'short_name': 'wcp_11',
        'name': 'yow-cgcs-wildcat-11',
        'floating ip': '128.224.151.19',
        'controller-0 ip': '128.224.151.19',
        'controller_nodes': [23206],
        'system_type': 'CPE',
        'system_mode': 'simplex',
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
        'floating ip': '128.224.150.133',
        'controller-0 ip': '128.224.150.133',
        'controller_nodes': [23213],
        'ixia_ports': [{'port': (5, 13), 'range': (2452, 2484)},
                       {'port': (5, 14), 'range': (2518, 2551)}],
    }

    WCP_14 = {
        'short_name': 'wcp_14',
        'name': 'yow-cgcs-wildcat-14',
        'floating ip': '128.224.150.136',
        'controller-0 ip': '128.224.150.136',
        'controller_nodes': [23214],
        'ixia_ports': [{'port': (3, 1), 'range': (733, 741)},
                       {'port': (3, 2), 'range': (743, 751)}],
    }

    WCP_15_22 = {
        'short_name': 'wcp_15_22',
        'name': 'yow-cgcs-wildcat-15_22',
        'floating ip': '128.224.151.230',
        'controller-0 ip': '128.224.150.140',
        'controller-1 ip': '128.224.150.180',
        'controller_nodes': [23215, 23216],
        'compute_nodes': [23219, 23220, 23221, 23222],
        'storage_nodes': [23217, 23218],
        'ixia_ports': [{'port': (5, 15), 'range': (2552, 2584)},
                       {'port': (5, 16), 'range': (2618, 2651)}],
    }

    WCP_35_60 = {
        'short_name': 'wcp_35_60',
        'name': 'yow-cgcs-wildcat-35_60',
        'floating ip': '128.224.150.234',
        'controller-0 ip': '128.224.150.232',
        'controller-1 ip': '128.224.150.233',
        'controller_nodes': [23268, 23267],
        'compute_nodes': [23258, 23257, 23256, 23255, 23254, 23253, 23252,
                          23251, 23250, 23249, 23248, 23247, 23246, 23245,
                          23244, 23243, 23262, 23261, 23260, 23259],
        'storage_nodes': [23264, 23263, 23266, 23265],
        'ixia_ports': [{'port': (7, 1), 'range': (3002, 3051)},
                       {'port': (7, 2), 'range': (3002, 3051)},
                       {'port': (7, 3), 'range': (3101, 3151)},
                       {'port': (7, 4), 'range': (3101, 3151)}],
    }

    WCP_35_60_2plus20 = {
        'short_name': 'wcp_35_60_2plus20',
        'name': 'yow-cgcs-wildcat-35_60_2plus20',
        'floating ip': '128.224.150.234',
        'controller-0 ip': '128.224.150.232',
        'controller-1 ip': '128.224.150.233',
        'controller_nodes': [23268, 23267],
        'compute_nodes': [23258, 23257, 23256, 23255, 23254, 23253, 23252,
                          23251, 23250, 23249, 23248, 23247, 23246, 23245,
                          23244, 23243, 23262, 23261, 23260, 23259],
        'ixia_ports': [{'port': (7, 1), 'range': (3002, 3051)},
                       {'port': (7, 2), 'range': (3002, 3051)},
                       {'port': (7, 3), 'range': (3101, 3151)},
                       {'port': (7, 4), 'range': (3101, 3151)}],
    }

    WCP_35_50 = {
        'short_name': 'wcp_35_50',
        'name': 'yow-cgcs-wildcat-35_50',
        'floating ip': '128.224.150.234',
        'controller-0 ip': '128.224.150.232',
        'controller-1 ip': '128.224.150.233',
        'controller_nodes': [23268, 23267],
        'compute_nodes': [23258, 23257, 23256, 23255, 23254, 23253, 23252,
                          23251, 23250, 23249],
        'ixia_ports': [{'port': (7, 1), 'range': (3002, 3051)},
                       {'port': (7, 2), 'range': (3002, 3051)},
                       {'port': (7, 3), 'range': (3101, 3151)},
                       {'port': (7, 4), 'range': (3101, 3151)}],
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
        'ixia_ports': [{'port': (8, 5), 'range': (600, 649)},
                       {'port': (8, 6), 'range': (700, 749)}],
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
        'ixia_ports': [{'port': (8, 9), 'range': (750, 799)},
                       {'port': (8, 10), 'range': (850, 899)}],
    }

    WCP_67 = {
        'short_name': 'wcp_67',
        'name': 'yow-cgcs-wildcat-67',
        'floating ip': '128.224.151.33',
        'controller-0 ip': '128.224.151.33',
        'controller_nodes': [23286],
        'system_type': 'CPE',
        'system_mode': 'simplex',
        'ixia_ports': [{'port': (8, 1), 'range': (2703, 2752)},
                       {'port': (8, 2), 'range': (2802, 2851)}],
    }

    WCP_68 = {
        'short_name': 'wcp_68',
        'name': 'yow-cgcs-wildcat-68',
        'floating ip': '128.224.151.38',
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
        'ixia_ports': [{'port': (7, 5), 'range': (3152, 3201)},
                       {'port': (7, 6), 'range': (3252, 3301)}],
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
        'ixia_ports': [{'port': (7, 7), 'range': (3302, 3351)},
                       {'port': (7, 8), 'range': (3402, 3451)}],
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
        'ixia_ports': [{'port': (7, 9), 'range': (3452, 3501)},
                       {'port': (7, 10), 'range': (3552, 3601)}],
    }

    WCP_80_84 = {
        'short_name': 'wcp_80_84',
        'name': 'yow-cgcs-wildcat-80_84',
        'floating ip': '128.224.150.18',
        'controller-0 ip': '128.224.150.14',
        'controller-1 ip': '128.224.150.156',
        'controller_nodes': [23318, 23319],
        'compute_nodes': [23320, 23321, 23322],
        'ixia_ports': [{'port': (7, 11), 'range': (3602, 3651)},
                       {'port': (7, 12), 'range': (3702, 3751)}],
        'boot_device_dict': {
            'controller-0': '0300', 'controller-1': '0500',
            'compute-0': 'UEFI IPv4: Intel Network 00 at Riser 01 Slot 01',
            'compute-1': 'UEFI IPv4: Intel Network 00 at Riser 01 Slot 01',
            'compute-2': 'UEFI IPv4: Intel Network 00 at Riser 01 Slot 01'},
    }

    WCP_82_83 = {
        'short_name': 'wcp_82_83',
        'name': 'yow-cgcs-wildcat-82_83',
        'floating ip': '128.224.151.95',
        'controller-0 ip': '128.224.151.96',
        'controller-1 ip': '128.224.151.97',
        'controller_nodes': [23320, 23321],
        'boot_device_dict': {'controller-0': '0300', 'controller-1': '0400'},
    }

    WCP_84 = {
        'short_name': 'wcp_84',
        'name': 'yow-cgcs-wildcat-84',
        'floating ip': '128.224.151.4',
        'controller-0 ip': '128.224.151.4',
        'controller_nodes': [23322],
        'boot_device_dict': {'controller-0': '0300'},
    }

    WCP_85_89 = {
        'short_name': 'wcp_85_89',
        'name': 'yow-cgcs-wildcat-85_89',
        'floating ip': '128.224.150.224',
        'controller-0 ip': '128.224.150.244',
        'controller-1 ip': '128.224.150.202',
        'controller_nodes': [23323, 23324],
        'compute_nodes': [23325, 23326, 23327],
        'ixia_ports': [{'port': (7, 13), 'range': (3752, 3801)},
                       {'port': (7, 14), 'range': (3852, 3901)}],
    }

    WCP_85_86 = {
        'short_name': 'wcp_85_86',
        'name': 'yow-cgcs-wildcat-85_86',
        'floating ip': '128.224.150.224',
        'controller-0 ip': '128.224.150.244',
        'controller-1 ip': '128.224.150.202',
        'controller_nodes': [23323, 23324],
        'boot_device_dict': {'controller-0': '0300', 'controller-1': '0500'},
    }

    WCP_87_88 = {
        'short_name': 'wcp_87_88',
        'name': 'yow-cgcs-wildcat-87_88',
        'floating ip': '128.224.151.66',
        'controller-0 ip': '128.224.151.86',
        'controller-1 ip': '128.224.151.229',
        'controller_nodes': [23325, 23326],
        'boot_device_dict': {'controller-0': '0300', 'controller-1': '0500'},
    }

    WCP_89 = {
        'short_name': 'wcp_89',
        'name': 'yow-cgcs-wildcat-89',
        'floating ip': '128.224.151.2',
        'controller-0 ip': '128.224.151.2',
        'controller_nodes': [23327],
        'boot_device_dict': {'controller-0': '0300'}
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
        'ixia_ports': [{'port': (7, 15), 'range': (301, 350)},
                       {'port': (7, 16), 'range': (401, 450)}],
        'boot_device_dict': {'controller-0': '0300', 'controller-1': '8100'},
    }

    WCP_92_98 = {
        'short_name': 'wcp_92_98',
        'name': 'yow-cgcs-wildcat-92_98',
        'floating ip': '128.224.151.15',
        'controller-0 ip': '128.224.151.111',
        'controller-1 ip': '128.224.151.205',
        'controller_nodes': [23299, 23300],
        'compute_nodes': [23303, 23301, 23302],
        'storage_nodes': [23304, 23305],
        'ixia_ports': [{'port': (6, 5), 'range': (3301, 3351)},
                       {'port': (6, 6), 'range': (3402, 3451)}],
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
        'ixia_ports': [{'port': (6, 7), 'range': (3452, 3501)},
                       {'port': (6, 8), 'range': (3552, 3601)}],
    }

    WCP_105 = {
        'short_name': 'wcp_105',
        'name': 'yow-cgcs-wildcat-105',
        'floating ip': '128.224.150.137',
        'controller-0 ip': '128.224.150.137',
        'controller_nodes': [23290],
        'system_type': 'CPE',
        'system_mode': 'simplex',
        'ixia_ports': [{'port': (6, 11), 'range': (3152, 3201)},
                       {'port': (6, 12), 'range': (3252, 3301)}],
    }

    WCP_106 = {
        'short_name': 'wcp_106',
        'name': 'yow-cgcs-wildcat-106',
        'floating ip': '128.224.150.94',
        'controller-0 ip': '128.224.150.94',
        'controller_nodes': [23601],
        'system_type': 'CPE',
        'system_mode': 'simplex',
        'ixia_ports': [{'port': (8, 13), 'range': (900, 999)},
                       {'port': (8, 14), 'range': (1000, 1049)}],
    }

    WCP_111 = {
        'short_name': 'wcp_111',
        'name': 'yow-cgcs-wildcat-111',
        'floating ip': '128.224.151.57',
        'controller-0 ip': '128.224.151.57',
        'controller_nodes': [23600],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WCP_112 = {
        'short_name': 'wcp_112',
        'name': 'yow-cgcs-wildcat-112',
        'floating ip': '128.224.150.148',
        'controller-0 ip': '128.224.150.148',
        'controller_nodes': [95980],
        'system_type': 'CPE',
        'system_mode': 'simplex',
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

    WCP_122 = {
        'short_name': 'wcp_122',
        'name': 'yow-cgcs-wildcat-122',
        'floating ip': '128.224.151.170',
        'controller-0 ip': '128.224.151.170',
        'controller_nodes': [64873],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    ML350_G10 = {
        'short_name': 'ml350_g10',
        'name': 'yow-cgcs-ml350-g10-1',
        'floating ip': '128.224.151.181',
        'controller-0 ip': '128.224.151.181',
        'controller_nodes': [55836],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_1_2 = {
        'short_name': 'wp_1_2',
        'name': 'yow-cgcs-wolfpass-01_02',
        'floating ip': '128.224.150.254',
        'controller-0 ip': '128.224.150.155',
        'controller-1 ip': '128.224.150.198',
        'controller_nodes': [62031, 29957],
        'system_type': 'CPE',
        'system_mode': 'duplex',
        'ixia_ports': [{'port': (8, 7), 'range': (1700, 1799)},
                       {'port': (8, 8), 'range': (1800, 1849)}],
    }

    WP_3_7 = {
        'short_name': 'wp_3_7',
        'name': 'yow-cgcs-wolfpass-03_07',
        'floating ip': '128.224.151.165',
        'controller-0 ip': '128.224.151.163',
        'controller-1 ip': '128.224.151.166',
        'controller_nodes': [98522, 81712],
        'compute_nodes': [94867, 18658, 40810],
    }

    WP_8_12 = {

        'short_name': 'wp_8_12',
        'name': 'yow-cgcs-wolfpass-08_12',
        'floating ip': '128.224.150.149',
        'controller-0 ip': '128.224.150.200',
        'controller-1 ip': '128.224.150.190',
        'controller_nodes': [28894, 36242],
        'compute_nodes': [67712, 94178, 80778],
    }

    WP_13_14 = {
        'short_name': 'wp_13_14',
        'name': 'yow-cgcs-wolfpass-13_14',
        'floating ip': '128.224.150.165',
        'controller-0 ip': '128.224.150.164',
        'controller-1 ip': '128.224.150.236',
        'controller_nodes': [37879, 77147],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    WP_15 = {
        'short_name': 'wp_15',
        'name': 'yow-cgcs-wolfpass-15',
        'floating ip': '128.224.150.245',
        'controller-0 ip': '128.224.150.245',
        'controller_nodes': [59865],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_16_17 = {
        'short_name': 'wp_16_17',
        'name': 'yow-cgcs-wolfpass-16_17',
        'floating ip': '128.224.150.248',
        'controller-0 ip': '128.224.150.247',
        'controller-1 ip': '128.224.150.251',
        'controller_nodes': [98812, 32981],
        'system_type': 'CPE',
        'system_mode': 'duplex',
    }

    WP_22_24 = {
        'short_name': 'wp_22_24',
        'name': 'yow-cgcs-wolfpass-22_24',
        'floating ip': '128.224.151.243',
        'controller-0 ip': '128.224.151.242',
        'controller-1 ip': '128.224.151.155',
        'controller_nodes': [27560, 60807],
        'compute_nodes': [43267],
        'system_type': 'AIO_PLUS',
        'system_mode': 'duplex',
    }

    WP_25 = {
        'short_name': 'wp_25',
        'name': 'yow-cgcs-wolfpass-25',
        'floating ip': '128.224.151.67',
        'controller-0 ip': '128.224.151.67',
        'controller_nodes': [65814],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_26 = {
        'short_name': 'wp_26',
        'name': 'yow-cgcs-wolfpass-26',
        'floating ip': '128.224.151.68',
        'controller-0 ip': '128.224.151.68',
        'controller_nodes': [39680],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_27 = {
        'short_name': 'wp_27',
        'name': 'yow-cgcs-wolfpass-27',
        'floating ip': '128.224.151.178',
        'controller-0 ip': '128.224.151.178',
        'controller_nodes': [95641],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_28 = {
        'short_name': 'wp_28',
        'name': 'yow-cgcs-wolfpass-28',
        'floating ip': '128.224.151.220',
        'controller-0 ip': '128.224.151.220',
        'controller_nodes': [51440],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_29 = {
        'short_name': 'wp_29',
        'name': 'yow-cgcs-wolfpass-29',
        'floating ip': '128.224.151.251',
        'controller-0 ip': '128.224.151.251',
        'controller_nodes': [58383],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_30 = {
        'short_name': 'wp_30',
        'name': 'yow-cgcs-wolfpass-30',
        'floating ip': '128.224.151.204',
        'controller-0 ip': '128.224.151.204',
        'controller_nodes': [90797],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_31 = {
        'short_name': 'wp_31',
        'name': 'yow-cgcs-wolfpass-31',
        'floating ip': '128.224.151.179',
        'controller-0 ip': '128.224.151.179',
        'controller_nodes': [13820],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_32 = {
        'short_name': 'wp_32',
        'name': 'yow-cgcs-wolfpass-32',
        'floating ip': '128.224.151.152',
        'controller-0 ip': '128.224.151.152',
        'controller_nodes': [20106],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_33 = {
        'short_name': 'wp_33',
        'name': 'yow-cgcs-wolfpass-33',
        'floating ip': '128.224.151.203',
        'controller-0 ip': '128.224.151.203',
        'controller_nodes': [73614],
        'system_type': 'CPE',
        'system_mode': 'simplex',
    }

    WP_34 = {
        'short_name': 'wp_34',
        'name': 'yow-cgcs-wolfpass-34',
        'floating ip': '128.224.151.190',
        'controller-0 ip': '128.224.151.190',
        'controller_nodes': [58338],
        'system_type': 'CPE',
        'system_mode': 'simplex',
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

    # Lab to select for auto install a custom system
    CUSTOM = {
        'short_name': 'custom',
        'name': 'custom',
        'floating ip': '',
        'controller-0 ip': '',
        'controller-1 ip': '',
        'controller_nodes': [],
        'compute_nodes': [],
        'storage_nodes': []
    }

    # Distributed Cloud-1
    WCP_80_91 = {
        'short_name': 'wcp_80_91',
        'name': 'yow-cgcs-distributed_cloud-1',
        'floating ip': WCP_90_91['floating ip'],
        'central_region': WCP_90_91,
        'subcloud1': WCP_80_84,     # wcp80-81(84)
        'subcloud2': WCP_82_83,     # wcp82-83
        'subcloud3': WCP_84,      # wcp84
        'subcloud4': WCP_85_86,
        'subcloud5': WCP_87_88,
        'subcloud6': WCP_89,
    }
    # Distributed Cloud-2
    WP_22_34 = {
        'short_name': 'wp_22_34',
        'name': 'yow-cgcs-distributed_cloud-2',
        'floating ip': WP_22_24['floating ip'],
        'central_region': WP_22_24,
        'subcloud1': WP_27,
        'subcloud2': WP_28,
        'subcloud3': WP_29,
        'subcloud4': WP_30,
        'subcloud5': WP_31,
        'subcloud6': WP_32,
        'subcloud7': WP_33,
        'subcloud8': WP_34,
        'subcloud9': WP_25,
        'subcloud10': WP_26
    }

    NO_LAB = None


def update_lab(lab_dict_name=None, lab_name=None, floating_ip=None, **kwargs):
    """
    Update/Add lab dict params for specified lab
    Args:
        lab_dict_name (str|None):
        lab_name (str|None): lab short_name. This is used only if
        lab_dict_name is not specified
        floating_ip (str|None):
        **kwargs: Some possible keys: subcloud1, name, etc

    Returns (dict): updated lab dict

    """

    if not lab_name and not lab_dict_name:
        from consts.proj_vars import ProjVar
        lab_name = ProjVar.get_var('LAB').get('short_name', None)
        if not lab_name:
            raise ValueError("lab_dict_name or lab_name needs to be specified")

    if floating_ip:
        kwargs.update(**{'floating ip': floating_ip})

    if not kwargs:
        raise ValueError("Please specify floating_ip and/or kwargs")

    if not lab_dict_name:
        attr_names = [attr for attr in dir(Labs) if not attr.startswith('__')]
        lab_names = [getattr(Labs, attr).get('short_name') for attr in
                     attr_names]
        lab_index = lab_names.index(lab_name.lower().strip())
        lab_dict_name = attr_names[lab_index]
    else:
        lab_dict_name = lab_dict_name.upper().replace('-', '_')

    lab_dict = getattr(Labs, lab_dict_name)
    lab_dict.update(kwargs)
    return lab_dict


def get_lab_dict(lab, key='short_name'):
    """

    Args:
        lab: lab name or fip
        key: unique identifier to locate a lab. Valid values: short_name,
        name, floating ip

    Returns (dict|None): lab dict or None if no matching lab found
    """
    __lab_attr_list = [attr for attr in dir(Labs) if not attr.startswith('__')]
    __lab_list = [getattr(Labs, attr) for attr in __lab_attr_list]
    __lab_list = [lab for lab in __lab_list if isinstance(lab, dict)]

    lab_info = None
    for lab_ in __lab_list:
        if lab.lower().replace('-', '_') == lab_.get(key).lower().\
                replace('-', '_'):
            lab_info = lab_
            break

    return lab_info


def add_lab_entry(floating_ip, dict_name=None, short_name=None, name=None,
                  **kwargs):
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
                raise ValueError(
                    "Entry for {} already exists in Labs class!".format(
                        floating_ip))

    if dict_name and dict_name in dir(Labs):
        raise ValueError(
            "Entry for {} already exists in Labs class!".format(dict_name))

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
    def add_natbox(ip, user=None, password=None, prompt=None):
        user = user if user else 'svc-cgcsauto'
        password = password if password else ')OKM0okm'

        nat_dict = {'ip': ip,
                    'name': ip,
                    'user': user,
                    'password': password,
                    }
        if prompt:
            nat_dict['prompt'] = prompt
        setattr(NatBoxes, 'NAT_NEW', nat_dict)
        return nat_dict
