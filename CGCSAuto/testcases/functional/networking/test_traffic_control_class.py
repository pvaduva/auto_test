import re
from pytest import fixture, skip, mark

import keywords.host_helper
from keywords import system_helper, host_helper
from utils.tis_log import LOG
from consts.reasons import SkipReason

def test_traffic_controls():
    """
        CGTS - 6884 - Traffic Controls Changes Required

        Test Steps:
            - Check the interface type
            - Check the speed of the interface
            - Check if traffic profile enabled as per expected value

        Teardown:
            -
    """

    NIC_1G_TC = """class htb 1:1 root rate 1000Mbit ceil 1000Mbit burst 15125b cburst 1375b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 100000Kbit ceil 200000Kbit burst 15337b cburst 1600b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 500000Kbit ceil 1000Mbit burst 15250b cburst 1375b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 300000Kbit ceil 1000Mbit burst 15300b cburst 1375b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 100000Kbit ceil 200000Kbit burst 15337b cburst 1600b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 800000Kbit ceil 1000Mbit burst 15200b cburst 1375b"""

    NIC_10G_TC = """class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 5000Mbit ceil 10000Mbit burst 15000b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 3000Mbit ceil 10000Mbit burst 15000b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 8000Mbit ceil 10000Mbit burst 14000b cburst 0b"""

    NIC_20G_TC = """class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 5000Mbit ceil 10000Mbit burst 15000b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 3000Mbit ceil 10000Mbit burst 15000b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 8000Mbit ceil 10000Mbit burst 14000b cburst 0b"""

    NIC_25G_TC = """class htb 1:1 root rate 25000Mbit ceil 25000Mbit burst 9375b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 2500Mbit ceil 5000Mbit burst 15000b cburst 625b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 12500Mbit ceil 25000Mbit burst 12500b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 7500Mbit ceil 25000Mbit burst 15000b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 2500Mbit ceil 5000Mbit burst 15000b cburst 625b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 20000Mbit ceil 25000Mbit burst 12500b cburst 0b"""

    MGMT_ETH_NIC_1G_TC = """class htb 1:40 parent 1:1 leaf 40: prio 4 rate 100000Kbit ceil 1000Mbit burst 15337b cburst 1375b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 100000Kbit ceil 1000Mbit burst 15337b cburst 1375b
    class htb 1:1 root rate 1000Mbit ceil 1000Mbit burst 15125b cburst 1375b"""

    MGMT_ETH_NIC_10G_TC = """class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1000Mbit ceil 10000Mbit burst 15125b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1000Mbit ceil 10000Mbit burst 15125b cburst 0b
    class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b"""

    MGMT_INFRA_VLAN_NIC_10G_TC = """class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b"""

    INFRA_VLAN_NIC_10G_TC = """class htb 1:1 root rate 9900Mbit ceil 9900Mbit burst 13612b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 990000Kbit ceil 1980Mbit burst 15221b cburst 1237b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 4950Mbit ceil 9900Mbit burst 14850b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 2970Mbit ceil 9900Mbit burst 14850b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 990000Kbit ceil 1980Mbit burst 15221b cburst 1237b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 7920Mbit ceil 9900Mbit burst 13860b cburst 0b"""

    INFRA_VLAN_NIC_20G_TC = """class htb 1:1 root rate 19800Mbit ceil 19800Mbit burst 12375b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1980Mbit ceil 3960Mbit burst 15097b cburst 990b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 9900Mbit ceil 19800Mbit burst 13612b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 5940Mbit ceil 19800Mbit burst 14107b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1980Mbit ceil 3960Mbit burst 15097b cburst 990b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 15840Mbit ceil 19800Mbit burst 11880b cburst 0b """

    INFRA_PXE_NIC_10G_TC = """class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 990000Kbit ceil 1980Mbit burst 15221b cburst 1237b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 4950Mbit ceil 9900Mbit burst 14850b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 2970Mbit ceil 9900Mbit burst 14850b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 990000Kbit ceil 1980Mbit burst 15221b cburst 1237b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 7920Mbit ceil 9900Mbit burst 13860b cburst 0b """

    INFRA_PXE_NIC_20G_TC = """class htb 1:1 root rate 20000Mbit ceil 20000Mbit burst 12500b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1980Mbit ceil 3960Mbit burst 15097b cburst 990b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 9900Mbit ceil 19800Mbit burst 13612b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 5940Mbit ceil 19800Mbit burst 14107b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1980Mbit ceil 3960Mbit burst 15097b cburst 990b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 15840Mbit ceil 19800Mbit burst 11880b cburst 0b"""

    MGMT_PXE_NIC_10G_TC = """class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b """

    MGMT_PXE_NIC_20G_TC = """class htb 1:40 parent 1:1 leaf 40: prio 4 rate 2000Mbit ceil 4000Mbit burst 15000b cburst 1000b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 2000Mbit ceil 4000Mbit burst 15000b cburst 1000b
    class htb 1:1 root rate 20000Mbit ceil 20000Mbit burst 12500b cburst 0b """

    INFRA_AE_NIC_20G_TC = """class htb 1:1 root rate 10000Mbit ceil 10000Mbit burst 13750b cburst 0b
    class htb 1:10 parent 1:1 leaf 10: prio 3 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:20 parent 1:1 leaf 20: prio 1 rate 5000Mbit ceil 10000Mbit burst 15000b cburst 0b
    class htb 1:30 parent 1:1 leaf 30: prio 2 rate 3000Mbit ceil 10000Mbit burst 15000b cburst 0b
    class htb 1:40 parent 1:1 leaf 40: prio 4 rate 1000Mbit ceil 2000Mbit burst 15125b cburst 1250b
    class htb 1:50 parent 1:1 leaf 50: prio 0 rate 8000Mbit ceil 10000Mbit burst 14000b cburst 0b """

    basic_traffic_class = {'1000': NIC_1G_TC,'10000': NIC_10G_TC,  '20000': NIC_20G_TC, '25000': NIC_25G_TC}
    mgmt_eth_traffic_class = {'1000': MGMT_ETH_NIC_1G_TC, '10000': MGMT_ETH_NIC_10G_TC}
    mgmt_vlan_traffic_class = {'1000': MGMT_INFRA_VLAN_NIC_10G_TC, '10000': MGMT_INFRA_VLAN_NIC_10G_TC}
    infra_vlan_traffic_class = {'10000': INFRA_VLAN_NIC_10G_TC, '20000': INFRA_VLAN_NIC_20G_TC}
    infra_pxe_traffic_class = {'10000': INFRA_PXE_NIC_10G_TC, '20000': INFRA_PXE_NIC_20G_TC}
    mgmt_pxe_traffic_class = {'10000': MGMT_PXE_NIC_10G_TC, '20000': MGMT_PXE_NIC_20G_TC}
    infra_ae_traffic_class = {'20000': INFRA_AE_NIC_20G_TC}

    LOG.tc_step("Check the system if infra and mgmt avaialble")
    mgmts = system_helper.get_host_interfaces_info(host='controller-0', rtn_val='name', net_type='mgmt')
    infras = system_helper.get_host_interfaces_info(host='controller-0',rtn_val='name', net_type='infra')

    if mgmts:
        mgmt_port_name = mgmts[0]
        LOG.tc_step("Check mgmt interface net type")
        mgmt_net_type = system_helper.get_host_interfaces_info(host='controller-0',rtn_val='type', net_type='mgmt')[0]
        if infras:
            infra_port_name = infras[0]
            LOG.tc_step("Check infra interface net type")
            infra_net_type = system_helper.get_host_interfaces_info(host='controller-0',rtn_val='type',
                                                                    net_type='infra')[0]
            if infra_net_type == 'vlan' and mgmt_net_type == 'vlan':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, infra_pxe_traffic_class)
                assert result, "Infra traffic class is not set as expected"
                result = _compare_traffic_control(mgmt_port_name, mgmt_pxe_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            elif infra_net_type == 'vlan' and mgmt_net_type == 'ethernet':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, infra_vlan_traffic_class)
                assert result, "Infra traffic class is not set as expected"
                result = _compare_traffic_control(mgmt_port_name, basic_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            elif infra_net_type == 'ae' and mgmt_net_type == 'vlan':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, infra_ae_traffic_class)
                assert result, "Infra traffic class is not set as expected "
                result = _compare_traffic_control(mgmt_port_name, mgmt_vlan_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            elif infra_net_type == 'ae' and mgmt_net_type == 'ethernet':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, infra_ae_traffic_class)
                assert result, "Infra traffic class is not set as expected"
                LOG.info("mgmt traffic class {}".format(mgmt_eth_traffic_class['1000']))
                result = _compare_traffic_control(mgmt_port_name, mgmt_eth_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            elif infra_net_type == 'vlan' and mgmt_net_type == 'ae':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, infra_vlan_traffic_class)
                assert result, "Infra traffic class is not set as expected"
                result = _compare_traffic_control(mgmt_port_name, basic_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            elif infra_net_type == 'ethernet' and mgmt_net_type == 'ae':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, basic_traffic_class)
                assert result, "Infra traffic class is not set as expected"
                result = _compare_traffic_control(mgmt_port_name, mgmt_eth_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            elif infra_net_type == 'ethernet' and mgmt_net_type == 'ethernet':
                LOG.info("Infra type is {} and mgmt type is {}" .format(infra_net_type, mgmt_net_type))
                result = _compare_traffic_control(infra_port_name, basic_traffic_class)
                assert result, "Infra traffic class is not set as expected"
                result = _compare_traffic_control(mgmt_port_name, mgmt_eth_traffic_class)
                assert result, "mgmt traffic class is not set as expected"
            else:
                assert 0, "This case is not handled contact domain owner to include this configuration"
        else:
            LOG.info("No infra and mgmt type is {}".format(mgmt_net_type))
            result = _compare_traffic_control(mgmt_port_name, basic_traffic_class)
            assert result, "mgmt traffic class is not set as expected"

    else:
        LOG.info("Skip the test")
        skip(SkipReason.MGMT_INFRA_UNAVAIL)

def _compare_traffic_control(port_name, expected_traffic_control):
    """
    Check the traffic control based on speed then compare it with expected traffic control string
    Args:
        portname (str): portname of interface type
        expected_traffic_control(str): Each configuration have pre determined traffic control profile
    """
    with host_helper.ssh_to_host('controller-0') as con0_ssh:
        LOG.tc_step("Check interface {} traffic control" .format(port_name))
        traffic_control_info = keywords.host_helper.get_traffic_control_info(con_ssh=con0_ssh, port=port_name)
        LOG.tc_step("Check interface {} speed" .format(port_name))
        nic_speed = keywords.host_helper.get_nic_speed(con_ssh=con0_ssh, port=port_name)
    key = '{}'.format(nic_speed)
    result = re.sub("\s*", "", traffic_control_info) == re.sub("\s*", "", expected_traffic_control[key])
    LOG.info("Actual Traffic control for port {} == {}".format(port_name, traffic_control_info))
    LOG.info("Expected Traffic control for port {} == {}".format(port_name, expected_traffic_control[key]))
    LOG.info("result {}".format(result))
    return result