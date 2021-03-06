from consts.stx import GuestImages


class Heat:
    OS_Ceilometer_Alarm = {'params': None, 'verify': ['ceilometer_alarm'], 'heat_user': 'tenant'}
    OS_Cinder_Volume = {'params': None, 'verify': ['volume'], 'heat_user': 'tenant', 'vol_name': 'sample_cinder_vol'}
    OS_Cinder_VolumeAttachment = {'params': ['NETWORK', 'IMAGE', 'FLAVOR'], 'verify': ['vm', 'volume'],
                                  'heat_user': 'tenant','vol_name': 'cinder_volume_demo', 'vm_name': 'cinder_vm'}
    OS_Glance_Image = {'params':None, 'verify': ['image'], 'heat_user': 'admin'}
    OS_Heat_AccessPolicy= {'params': ['NETWORK'], 'verify': ['neutron_port'], 'heat_user': 'tenant', 'port_name': None}
    OS_Heat_Stack = {'params': None, 'verify': ['key_pair'], 'heat_user': 'tenant', 'key_pair_name': 'InlineKP'}
    OS_Neutron_FloatingIP = {'params': None,'verify':['floating_ip'],'heat_user':'tenant'}
    OS_Neutron_Net = {'params': None,'verify':['neutron_net'],'heat_user':'tenant'}
    OS_Neutron_Port = {'params': None,'verify':['neutron_port'],'heat_user':'tenant','port_name':'sample_port'}
    OS_Neutron_Router = {'params': None,'verify':['router'],'heat_user':'admin'}
    OS_Neutron_RouterGateway = {'params': None,'verify':['router_gateway'],'heat_user':'admin'}
    OS_Neutron_RouterInterface = {'params': None,'verify':['router_interface'],'heat_user':'admin'}
    OS_Neutron_SecurityGroup = {'params': None, 'verify':['security_group'],'heat_user':'tenant'}
    OS_Neutron_Subnet = {'params':['NETWORK'], 'verify':['subnet'], 'heat_user':'tenant'}
    OS_Nova_Flavor = {'params': None, 'verify': ['nova_flavor'],'heat_user':'admin'}
    OS_Nova_KeyPair = {'params': None, 'verify': ['key_pair'],'heat_user':'tenant','key_pair_name':'KeyPairDeluxe'}
    OS_Nova_Server = {'params': ['NETWORK', 'IMAGE', 'FLAVOR'], 'verify': ['vm'], 'heat_user': 'tenant',
                      'vm_name': 'nova_server'}
    OS_Nova_ServerGroup = {'params': ['NETWORK', 'IMAGE', 'FLAVOR'], 'verify': ['nova_server_group'],
                           'heat_user': 'tenant'}
    WR_Neutron_Port_Forwarding = {}
    WR_Neutron_ProviderNet = {'params': None,'verify': ['neutron_provider_net'], 'heat_user': 'admin'}
    WR_Neutron_ProviderNetRange = {'params': None, 'verify': ['neutron_provider_net_range'], 'heat_user': 'admin'}
    WR_Neutron_QoSPolicy = {'params': None, 'verify': ['neutron_qos'], 'heat_user': 'admin'}
    OS_Heat_AutoScalingGroup = {'params': ['NETWORK', 'IMAGE', 'FLAVOR'], 'verify': ['vm'], 'heat_user': 'tenant',
                                'vm_name': 'nova_server'}
    NestedAutoScale = {'params': ['NETWORK', 'IMAGE', 'FLAVOR'], 'verify': ['vm'], 'heat_user': 'tenant',
                       'vm_name': 'nova_server'}
    stress_ng = {'heat_user': 'tenant','vm_name': 'stress_ng'}
    VMAutoScaling = {'heat_user': 'tenant', 'vm_name': 'vm_cpu_scale'}


class HeatUpdate:
    # OS_Ceilometer_Alarm = {}
    # OS_Cinder_Volume = {}
    # OS_Cinder_VolumeAttachment = {}
    # OS_Glance_Image = {}
    # OS_Heat_AccessPolicy= {}
    # OS_Heat_Stack = {}
    # OS_Neutron_FloatingIP = {}
    # OS_Neutron_Net = {}
    # OS_Neutron_Port = {}
    # OS_Neutron_Router = {}
    # OS_Neutron_RouterGateway = {}
    # OS_Neutron_RouterInterface = {}
    # OS_Neutron_SecurityGroup = {}
    #  OS_Neutron_Subnet = {}
    # OS_Nova_Flavor = {}
    # OS_Nova_KeyPair = {}
    OS_Nova_Server = {'params': ['IMAGE', 'SIZE'], 'new_vals': ['{}_tis-centos2'.format(GuestImages.DEFAULT['guest']), 3]}
    OS_Nova_ServerGroup = {'params': ['FLAVOR', 'SIZE'], 'new_vals': ['small_float', 3]}
    # WR_Neutron_Port_Forwarding = {}
    # WR_Neutron_ProviderNet = {}
    # WR_Neutron_ProviderNetRange = {}
    # WR_Neutron_QoSPolicy = {}
    # OS_Heat_AutoScalingGroup = {}

