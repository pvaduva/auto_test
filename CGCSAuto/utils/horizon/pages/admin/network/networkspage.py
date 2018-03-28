from utils.horizon.pages.project.network import networkspage


class NetworksTable(networkspage.NetworksTable):

    CREATE_NETWORK_FORM_FIELDS = (("name", "tenant_id", "network_type",
                                   "admin_state", "qos", "vlan_transparent",
                                   'shared', "external", "with_subnet",
                                   "physical_network_flat", "physical_network_vlan",
                                   "physical_network_vxlan", "segmentation_id"),
                                  ("subnet_name", "cidr", "ip_version",
                                   "gateway_ip", "no_gateway"),
                                  ("enable_dhcp", "allocation_pools",
                                   "dns_nameservers", "host_routes"))


class NetworksPage(networkspage.NetworksPage):
    PARTIAL_URL = 'admin/networks'

    DEFAULT_PROJECT_NAME = 'tenant1'
    DEFAULT_NETWORK_TYPE = 'vlan'
    DEFAULT_PHYSICAL_NETWORK = 'group0-data0'
    DEFAULT_SEGMENTATION_ID = 10
    DEFAULT_SHARED = False
    DEFAULT_EXTERNAL = False
    DEFAULT_ADMIN_STATE = True
    DEFAULT_VLAN_TRANSPARENT = False
    DEFAULT_CREATE_SUBNET = True
    DEFAULT_SUBNET_REGION = '192.168.0.0/24'
    DEFAULT_IP_VERSION = '4'
    DEFAULT_DISABLE_GATEWAY = False
    DEFAULT_ENABLE_DHCP = True
    NETWORKS_TABLE_NAME_COLUMN = 'Network Name'
    NETWORKS_TABLE_STATUS_COLUMN = 'Status'
    SUBNET_TAB_INDEX = 1
    DETAILS_TAB_INDEX = 2


    @property
    def networks_table(self):
        return NetworksTable(self.driver)

    def create_network(self, network_name, subnet_name,
                       tenant_id=DEFAULT_PROJECT_NAME,
                       network_type=DEFAULT_NETWORK_TYPE,
                       physical_network=DEFAULT_PHYSICAL_NETWORK,
                       segmentation_id=DEFAULT_SEGMENTATION_ID,
                       admin_state=DEFAULT_ADMIN_STATE,
                       qos=None,
                       shared=DEFAULT_SHARED,
                       external=DEFAULT_EXTERNAL,
                       vlan_transparent=DEFAULT_VLAN_TRANSPARENT,
                       create_subnet=DEFAULT_CREATE_SUBNET,
                       network_address=None,
                       ip_version=DEFAULT_IP_VERSION,
                       gateway_ip=None,
                       disable_gateway=DEFAULT_DISABLE_GATEWAY,
                       enable_dhcp=DEFAULT_ENABLE_DHCP, allocation_pools=None,
                       dns_name_servers=None, host_routes=None):

        create_network_form = self.networks_table.create_network()
        create_network_form.name.text = network_name
        create_network_form.tenant_id.text = tenant_id
        create_network_form.network_type.value = network_type
        if network_type == 'vlan':
            create_network_form.physical_network_vlan.value = physical_network
            create_network_form.segmentation_id = segmentation_id
        if network_type == 'vxlan':
            create_network_form.physical_network_vxlan.value = physical_network
        if network_type == 'flat':
            create_network_form.physical_network_flat.value = physical_network
        if admin_state:
            create_network_form.admin_state.mark()
        if qos is not None:
            create_network_form.qos.value = qos
        if shared:
            create_network_form.shared.mark()
        if external:
            create_network_form.external.mark()
        if vlan_transparent:
            create_network_form.vlan_transparent.mark()
        if not create_subnet:
            create_network_form.with_subnet.unmark()
            create_network_form.switch_to(self.DETAILS_TAB_INDEX)
        else:
            create_network_form.switch_to(self.SUBNET_TAB_INDEX)
            create_network_form.subnet_name.text = subnet_name
            if network_address is None:
                network_address = self.DEFAULT_SUBNET_REGION
            create_network_form.cidr.text = network_address

            create_network_form.ip_version.value = ip_version
            if gateway_ip is not None:
                create_network_form.gateway_ip.text = gateway_ip
            if disable_gateway:
                create_network_form.disable_gateway.mark()
            create_network_form.switch_to(self.DETAILS_TAB_INDEX)
            if not enable_dhcp:
                create_network_form.enable_dhcp.unmark()
            if allocation_pools is not None:
                create_network_form.allocation_pools.text = allocation_pools
            if dns_name_servers is not None:
                create_network_form.dns_nameservers.text = dns_name_servers
            if host_routes is not None:
                create_network_form.host_routes.text = host_routes
        create_network_form.submit()
