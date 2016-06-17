class Heat:
    OS_Ceilometer_Alarm = {'params':None,'verify':'ceilometer_alarm','heat_user':'tenant'}
    OS_Cinder_Volume = {'params':None,'verify':'volume','heat_user':'tenant'}
    OS_Cinder_Volume_Attachment = {}
    OS_Glance_Image = {'params':None,'verify':['image'],'heat_user':'admin'}
    OS_Heat_AccessPolicy= {}
    OS_Heat_stack = {}
    OS_Neutron_FloatingIP = {'params':None,'verify':'floating_ip','heat_user':'tenant'}
    OS_Neutron_Net = {'params':None,'verify':'neutron_net','heat_user':'tenant'}
    OS_Neutron_Port = {'params':None,'verify':'neutron_port','heat_user':'tenant'}
    OS_Neutron_Router = {'params':None,'verify':'router','heat_user':'admin'}
    OS_Neutron_RouterGateway = {'params':None,'verify':'router_gateway','heat_user':'admin'}
    OS_Neutron_RouterInterface = {'params':None,'verify':'router_interface','heat_user':'admin'}
    OS_Neutron_SecurityGroup = {'params':None,'verify':'security_group','heat_user':'tenant'}
    OS_Neutron_Subnet = {'params':['NETWORK'],'verify':'subnet', 'heat_user':'tenant'}
    OS_Nova_Flavor = {'params':None,'verify':'nova_flavor','heat_user':'admin'}
    OS_Nova_KeyPair = {'params':None,'verify':'key_pair','heat_user':'tenant'}
    OS_Nova_Server = {'params':['NETWORK', 'IMAGE', 'FLAVOR'],'verify':'vm', 'heat_user':'tenant'}
    OS_Nova_ServerGroup = {'params':None,'verify':'nova_server_group','heat_user':'tenant'}
    WR_Neutron_Port_Forwarding = {}
    WR_Neutron_ProviderNet = {'params':None,'verify':'neutron_provider_net','heat_user':'admin'}
    WR_Neutron_ProviderNetRange = {'params':None,'verify':'neutron_provider_net_range','heat_user':'admin'}
    WR_Neutron_QoSPolicy = {'params':None,'verify':'neutron_qos','heat_user':'admin'}
    OS_Heat_AutoScalingGroup = {}



