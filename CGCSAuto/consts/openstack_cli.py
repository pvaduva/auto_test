NEUTRON_MAP = {
    # below are openstack neutron cli mapping
    'floatingip-delete': 'ip floating delete',
    'floatingip-list': 'ip floating list',
    'floatingip-show': 'ip floating show',
    'net-create': 'network create',
    'net-delete': 'network delete',
    'net-list': 'network list',
    'net-show': 'network show',
    'net-update': 'network set',
    'port-delete': 'port delete',
    'port-show': 'port show',
    'router-create': 'router create',
    'router-delete': 'router delete',
    'router-list': 'router list',
    'router-show': 'router show',
    # 'router-update': 'router set',    # doesn't accept --external-gateway-info arg
    'security-group-delete': 'security group delete',
    'security-group-list': 'security group list',
    'security-group-rule-delete': 'security group rule delete',
    'security-group-rule-show': 'security group rule show',
    'subnet-delete': 'subnet delete',
    'subnet-list': 'subnet list',
    'subnetpool-delete': 'subnet pool delete',
    'subnetpool-list': 'subnet pool list',
    'subnetpool-show': 'subnet pool show',
    'subnet-show': 'subnet show',

    # below are wrs extensions mapping
    # 'host-bind-interface': 'host bind interface',
    # 'host-unbind-interface': 'host unbind interface',
    # 'net-list-on-providernet': 'net list on providernet',
    # 'portforwarding-create': 'portforwarding create',
    # 'portforwarding-delete': 'portforwarding delete',
    # 'portforwarding-list': 'portforwarding list',
    # 'portforwarding-show': 'portforwarding show',
    # 'portforwarding-update': 'portforwarding update',
    # 'providernet-connectivity-test-list': 'providernet connectivity test list',
    # 'providernet-connectivity-test-schedule': 'providernet connectivity test schedule',
    # 'providernet-create': 'providernet create',
    # 'providernet-delete': 'providernet delete',
    # 'providernet-list': 'providernet list',
    # 'providernet-range-create': 'providernet range create',
    # 'providernet-range-delete': 'providernet range delete',
    # 'providernet-range-list': 'providernet range list',
    # 'providernet-range-show': 'providernet range show',
    # 'providernet-range-update': 'providernet range update',
    # 'providernet-show': 'providernet show',
    # 'providernet-type-list': 'providernet type list',
    # 'providernet-update': 'providernet update',
    # 'qos-create': 'qos create',
    # 'qos-delete': 'qos delete',
    # 'qos-list': 'qos list',
    # 'qos-show': 'qos show',
    # 'qos-update': 'qos update',
    # 'setting-delete': 'setting delete',
    # 'setting-list': 'setting list',
    # 'setting-show': 'setting show',
    # 'setting-update': 'setting update',
    # 'host-create': 'tis host create',
    # 'host-delete': 'tis host delete',
    # 'host-list': 'tis host list',
    # 'host-show': 'tis host show',
    # 'host-update': 'tis host update',

}
