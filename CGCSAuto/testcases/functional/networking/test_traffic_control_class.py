import copy
from pytest import skip

from keywords import system_helper, host_helper
from utils.tis_log import LOG
from consts.cgcs import HostAvailState, TrafficControl


def test_traffic_control_classes():
    """
    References: CGTS-6884
    Test Steps:
        - get interface(s)/dev(s) used by mgmt and infra networks via system host-if-list <controller>
        - get the link capacity via /sys/class/net/<dev>
        - calculate the expected rates for each class based on how system mgmt/infra are configured and the underlying
        link capacity.
        - check the rates set for different traffic control classes for mgmt and infra devs via tc dev show dev <dev>
        - Ensure if follows the expectations in CGTS-6884

    """

    controllers = system_helper.get_controllers(availability=HostAvailState.AVAILABLE)

    for controller in controllers:
        LOG.info("Collect traffic control info for {}".format(controller))
        mgmt = system_helper.get_host_interfaces(host=controller, net_type='mgmt',
                                                 rtn_val=('name', 'type', 'vlan id', 'ports', 'uses i/f'))[0]
        mgmt_if_name, mgmt_type, mgmt_vlan, mgmt_ports, mgmt_uses_ifs = mgmt
        if mgmt_type == 'virtual':
            skip("mgmt is virtual")

        mgmt_dev, mgmt_ports = system_helper.get_host_ports_for_net_type(host=controller, net_type='mgmt',
                                                                         ports_only=False)[0]
        infra = system_helper.get_host_interfaces(host=controller, net_type='infra',
                                                  rtn_val=('name', 'type', 'vlan id', 'ports', 'uses i/f'))
        if not infra:
            mgmt_expt = TrafficControl.MGMT_NO_INFRA
            if_info = {'mgmt': (mgmt_dev, mgmt_ports, mgmt_expt)}
        else:
            pxe_if = system_helper.get_host_interfaces(host=controller, net_type='pxeboot', rtn_val='name')
            pxe_if_name = pxe_if[0] if pxe_if else None

            infra_if_name, infra_type, infra_vlan, infra_ports, infra_uses_ifs = infra[0]
            infra_dev, infra_ports = system_helper.get_host_ports_for_net_type(host=controller, net_type='infra',
                                                                               ports_only=False)[0]
            if infra_type == 'vlan':
                if infra_uses_ifs[0] == mgmt_if_name:
                    LOG.info("Infra is consolidated over mgmt")
                    infra_expt = TrafficControl.INFRA_USES_MGMT
                    mgmt_expt = TrafficControl.MGMT_USED_BY_INFRA
                elif pxe_if and infra_uses_ifs[0] == pxe_if_name:
                    infra_expt = TrafficControl.INFRA_USES_PXE
                    assert mgmt_uses_ifs[0] == pxe_if_name, \
                        "Unknown configuration. infra is consolidated over pxe but mgmt is not."
                    mgmt_expt = TrafficControl.MGMT_USES_PXE
                else:
                    assert 0, "Unknown infra vlan config. uses_if: {}".format(infra_uses_ifs)
            else:
                infra_expt = TrafficControl.INFRA_SEP
                if mgmt_type == 'vlan':
                    assert mgmt_uses_ifs[0] == pxe_if_name, "mgmt net is vlan over non-pxe interface"
                    mgmt_expt = TrafficControl.MGMT_USES_PXE
                else:
                    mgmt_expt = TrafficControl.MGMT_SEP

            if_info = {'mgmt': (mgmt_dev, mgmt_ports, mgmt_expt), 'infra': (infra_dev, infra_ports, infra_expt)}

        with host_helper.ssh_to_host(controller) as controller_ssh:

            for if_net in if_info:
                if_class_dev, if_speed_dev, if_expt = if_info[if_net]
                if_expt = copy.deepcopy(if_expt)
                config = if_expt.pop('config')

                LOG.tc_step("Check {} traffic control classes for {} network {} as as expected: {}. Config: {}".
                            format(controller, if_net, if_class_dev, if_expt, config))
                if_speeds = host_helper.get_nic_speed(con_ssh=controller_ssh, interface=if_speed_dev)
                LOG.info('{} {} underlying link capacity: {}'.format(controller, if_net, if_speeds))

                if_actual = host_helper.get_traffic_control_rates(con_ssh=controller_ssh, dev=if_class_dev)

                if_root, if_root_ceil = if_actual['root']
                expt_ceil_ratio = if_expt['root'][1]
                underlying_speed = int(if_root_ceil/expt_ceil_ratio)

                assert min(if_speeds) <= underlying_speed <= max(if_speeds), \
                    "{} {} root ceil rate unexpected with {} configured. " \
                    "root ceil: {}M, underlying link capacity in Mbit: {}".\
                    format(controller, if_net, config, if_root_ceil, if_speeds)
                assert len(if_expt) == len(if_actual), "{} traffic classes expected: {}; actual: {}. Config: {}".\
                    format(if_net, list(if_expt.keys()), list(if_actual.keys()), config)

                for traffic_class in if_expt:
                    expt_rate, expt_ceil = [int(underlying_speed*ratio) for ratio in if_expt[traffic_class]]
                    actual_rate, actual_ceil = if_actual[traffic_class]
                    LOG.info("{} {} {} class actual rate: {}, ceil: {}".format(controller, if_net, traffic_class,
                                                                               actual_rate, actual_ceil))
                    assert expt_rate == actual_rate, \
                        "{} traffic control class {} expected rate: {}M; actual: {}M. Config: {}".\
                        format(config, if_net, traffic_class, expt_rate, actual_rate)
                    assert expt_ceil == actual_ceil, \
                        "{} traffic control class {} expected ceiling rate: {}M; actual: {}M. Config: {}".\
                        format(if_net, traffic_class, expt_ceil, actual_ceil, config)
