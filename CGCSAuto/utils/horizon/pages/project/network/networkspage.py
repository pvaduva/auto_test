from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class NetworksTable(tables.TableRegion):
    name = "networks"
    CREATE_NETWORK_FORM_FIELDS = (("net_name", "admin_state", "qos", "vlan_transparent", "with_subnet"),
                                  ("subnet_name", "cidr", "ip_version",
                                   "gateway_ip", "no_gateway"),
                                  ("enable_dhcp", "allocation_pools",
                                   "dns_nameservers", "host_routes"))

    @tables.bind_table_action('create')
    def create_network(self, create_button):
        create_button.click()
        self.wait_till_spinner_disappears()
        return forms.TabbedFormRegion(self.driver, self.CREATE_NETWORK_FORM_FIELDS)

    @tables.bind_table_action('delete')
    def delete_network(self, delete_button):
        delete_button.click()
        return forms.BaseFormRegion(self.driver)


class NetworksPage(basepage.BasePage):
    PARTIAL_URL = 'project/networks'

    DEFAULT_ADMIN_STATE = True
    DEFAULT_VLAN_TRANSPARENT = False
    DEFAULT_CREATE_SUBNET = True
    DEFAULT_SUBNET_REGION = '192.168.0.0/24'
    DEFAULT_IP_VERSION = '4'
    DEFAULT_DISABLE_GATEWAY = False
    DEFAULT_ENABLE_DHCP = True
    NETWORKS_TABLE_NAME_COLUMN = 'Name'
    NETWORKS_TABLE_STATUS_COLUMN = 'Status'
    SUBNET_TAB_INDEX = 1
    DETAILS_TAB_INDEX = 2

    def __init__(self, driver):
        super(NetworksPage, self).__init__(driver)
        self._page_title = "Networks"

    def _get_row_with_network_name(self, name):
        return self.networks_table.get_row(
            self.NETWORKS_TABLE_NAME_COLUMN, name)

    @property
    def networks_table(self):
        return NetworksTable(self.driver)

    def create_network(self, network_name, subnet_name,
                       admin_state=DEFAULT_ADMIN_STATE,
                       qos=None,
                       vlan_transparent=DEFAULT_VLAN_TRANSPARENT,
                       create_subnet=DEFAULT_CREATE_SUBNET,
                       network_address=None,
                       ip_version=DEFAULT_IP_VERSION,
                       gateway_ip=None,
                       disable_gateway=DEFAULT_DISABLE_GATEWAY,
                       enable_dhcp=DEFAULT_ENABLE_DHCP, allocation_pools=None,
                       dns_name_servers=None, host_routes=None):

        create_network_form = self.networks_table.create_network()
        create_network_form.net_name.text = network_name
        if admin_state:
            create_network_form.admin_state.mark()
        if qos is not None:
            create_network_form.qos.value = qos
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

    def delete_network(self, name):
        row = self._get_row_with_network_name(name)
        row.mark()
        confirm_delete_networks_form = self.networks_table.delete_network()
        confirm_delete_networks_form.submit()

    def is_network_present(self, name):
        return bool(self._get_row_with_network_name(name))

    def is_network_active(self, name):
        def cell_getter():
            row = self._get_row_with_network_name(name)
            return row and row.cells[self.NETWORKS_TABLE_STATUS_COLUMN]

        return bool(self.networks_table.wait_cell_status(cell_getter,
                                                         'Active'))
