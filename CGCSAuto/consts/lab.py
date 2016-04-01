class Labs:
    HP380 = {
        'short_name': 'hp380',
        'name': 'yow-cgcs-hp380-1-4',
        'floating ip': '128.224.150.189',
        'controller-0 ip': '128.224.150.199',
        'controller-1 ip': '128.224.150.129',
        'auth_url': 'http://192.168.204.102:5000/v2.0/',
    }

    IP_1_4 = {
        'short_name': 'ip_1_4',
        'name': 'cgcs-ironpass-1_4',
        'floating ip': '128.224.151.212',
        'controller-0 ip': '128.224.151.192',
        'controller-1 ip': '128.224.151.193',
        'auth_url': 'http://192.168.204.2:5000/v2.0/',
    }

    IP_14_17 = {
        'short_name': 'ip_14_17',
        'name': 'cgcs-ironpass-14_17',
        'floating ip': '128.224.150.54',
        'controller-0 ip': '128.224.150.219',
        'controller-1 ip': '128.224.150.212'
    }

    IP_18_19 = {
        'short_name': 'ip18_19',
        'name': 'cgcs-ironpass-18_19',
        'floating ip': '128.224.150.158',
        'controller-0 ip': '128.224.150.168',
        'controller-1 ip': '128.224.150.169',
    }

    PV0 = {
        'short_name': 'pv0',
        'name': 'yow-cgcs-pv-0',
        'floating ip': '128.224.150.73',
        'controller-0 ip': '128.224.150.26',
        'controller-1 ip': '128.224.150.28',
        'auth_url': 'http://192.168.204.2:5000/v2.0/',
    }

    PV1 = {
        'short_name': 'pv1',
        'name': 'yow-cgcs-pv-1',
        'floating ip': '128.224.151.182',
        'controller-0 ip': '128.224.151.198',
        'controller-1 ip': '128.224.151.199'
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
        'name': 'yow-cgcs-r720-1-2',
        'floating ip': '128.224.150.141',
        'controller-0 ip': '128.224.150.130',
        'controller-1 ip': '128.224.150.106',
    }

    R720_3_7 = {
        'short_name': 'r720_3_7',
        'name': 'yow-cgcs-r720-3_7',
        'floating ip': '128.224.150.142',
        'controller-0 ip': '128.224.151.35',
        'controller-1 ip': '128.224.151.36',
    }

    WCP_3_6 = {
        'short_name': 'wcp_3_6',
        'name': 'yow-cgcs-wildcat-3-6',
        'floating ip': '128.224.151.227',
        'controller-0 ip': '128.224.151.69',
        'controller-1 ip': '128.224.151.70',
    }

    WCP_7_12 = {
        'short_name': 'wcp_7_12',
        'name': 'yow-cgcs-wildcat-7-12',
        'floating ip': '128.224.151.228',
        'controller-0 ip': '128.224.150.220',
        'controller-1 ip': '128.224.150.231',
    }

    WCP_13_14 = {
        'short_name': 'wcp_13_14',
        'name': 'yow-cgcs-wildcat-13-14',
        'floating ip': '128.224.151.229',
        'controller-0 ip': '128.224.150.133',
        'controller-1 ip': '128.224.150.136',
    }

    WCP_15_22 = {
        'short_name': 'wcp_15_22',
        'name': 'yow-cgcs-wildcat-15-22',
        'floating ip': '128.224.151.230',
        'controller-0 ip': '128.224.150.140',
        'controller-1 ip': '128.224.150.180',
    }

    VBOX = {
        'short_name': 'vbox',
        'name': 'vbox',
        'floating ip': '10.10.1.3',
        'controller-0 ip': '10.10.1.1',
        'controller-1 ip': '10.10.1.2',
    }

    LARGE_OFFICE = {
        'name': 'large office',
        'floating ip': ''
    }


def edit_lab_entry():
    # TODO
    raise NotImplementedError


def add_lab_entry(dict_name, lab_name=None, **kwargs):
    """
    Add a new lab dictionary to Labs class
    Args:
        dict_name: name of the entry, such as 'PV0'
        lab_name: name of the TiS system, such as 'yow-cgcs-pv-0'
        **kwargs: other information of the lab such as floating ip, controller ip, etc

    Returns:

    """
    dict_name = dict_name.upper()
    if dict_name in dir(Labs):
        raise ValueError("Entry for {} already exists in Labs class!".format(dict_name))

    if lab_name is None:
        lab_name = dict_name.lower()

    lab_dict = {'name': lab_name}
    lab_dict.update(kwargs)
    setattr(Labs, dict_name, lab_dict)


class NatBox:
    NAT_BOX_HW = {
        'ip': '128.224.150.11',
        'user': 'cgcs',
        'password': 'li69nux'
    }

    NAT_BOX_CUMULUS = {
        'ip': '',
        'user': '',
        'password': ''
    }


