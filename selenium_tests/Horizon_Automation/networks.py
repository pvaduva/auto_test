from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from common_utils import DriverUtils
import constants
import settings
import time

__author__ = 'jbarber'

class Networks():

    @classmethod
    def networks(cls, network_provider_name, network_provider_type, mtu, vlan_transparent):
        print "Create Networks (Admin -> System -> Networks)-----------------------------------------------------------"
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/networks/"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Call Functions below
        cls.create_provider_net(network_provider_name, network_provider_type, mtu, vlan_transparent)
        time.sleep(5)
        provider_net_link = cls.get_provider_net(network_provider_name)
        if(provider_net_link == -1):
            print "Error finding provider net name"
            return
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)
        return provider_net_link

    @classmethod
    def create_provider_net(cls, network_provider_name, network_provider_type, mtu, vlan_transparent):
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "?tab=networks__provider_networks"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        create_button = driver.find_element_by_id("provider_networks__action_create")
        create_button.click()

        name_input = driver.find_element_by_id("id_name")
        name_input.click()
        name_input.send_keys(network_provider_name)

        type_input = Select(driver.find_element_by_id("id_type"))
        # Consider changing 'flat' 'vlan' 'vxlan' to constants?
        if(network_provider_type == "flat"):
            type_input.select_by_visible_text("flat")
        if(network_provider_type == "vlan"):
            type_input.select_by_visible_text("vlan")
        if(network_provider_type == "vxlan"):
            type_input.select_by_visible_text("vxlan")

        mtu_input = driver.find_element_by_id("id_mtu")
        mtu_input.click()
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(Keys.BACKSPACE)
        mtu_input.send_keys(mtu)

        vlan_input = driver.find_element_by_id("id_vlan_transparent")
        if(vlan_transparent == True):
            vlan_input.click()
        if(vlan_transparent == False):
            pass

        vlan_input.submit()

    @classmethod
    def get_provider_net(cls, network_provider_name):
        provider_net_link = -1
        index = [6]
        # TODO: Grab driver, read table, compare to user_name, navigate to modify quotas section!
        # Read table, match name with project ID, use constants like in 'lock_host.py'
        # tuple of Name and Project ID
        # Get driver
        driver = DriverUtils.get_driver()

        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            #print host_local
            # Match host_to_lock with link
            if(network_provider_name in host_local):
                provider_id_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(provider_net_link))
        return provider_id_link

    @classmethod
    def provider_net_range_create(cls, provider_net_link, provider_name, shared, project_name, min_range, max_range):
        # Get driver
        driver = DriverUtils.get_driver()
        DriverUtils.set_url(provider_net_link)
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        create_button = driver.find_element_by_id("provider_network_ranges__action_create")
        create_button.click()

        name_input = driver.find_element_by_id("id_name")
        name_input.click()
        name_input.send_keys(provider_name)

        shared_input = driver.find_element_by_id("id_shared")
        shared_input.click()
        shared_input.send_keys(shared)

        if(project_name == None):
            pass
        else:
            project_input = Select(driver.find_element_by_id("id_tenant_id"))
            project_input.select_by_visible_text(project_name)

        min_range_input = driver.find_element_by_id("id_minimum")
        min_range_input.click()
        min_range_input.send_keys(min_range)

        max_range_input = driver.find_element_by_id("id_maximum")
        max_range_input.click()
        max_range_input.send_keys(max_range)
        max_range_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_qos_policy(cls, policy_name, description, weight, project_name):
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/networks/?tab=networks__qos"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        create_button = driver.find_element_by_id("qos__action_create")
        create_button.click()

        policy_name_input = driver.find_element_by_id("id_name")
        policy_name_input.click()
        policy_name_input.send_keys(policy_name)

        description_input = driver.find_element_by_id("id_description")
        description_input.click()
        description_input.send_keys(description)

        weight_input = driver.find_element_by_id("id_weight")
        weight_input.click()
        weight_input.send_keys(weight)

        if(project_name == None):
            pass
        else:
            project_input = Select(driver.find_element_by_id("id_tenant_id"))
            project_input.select_by_visible_text(project_name)

        policy_name_input.submit()

        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_network(cls, network_name, project_name, network_type, physical_network, \
                       segmentation_id, qos_policy, shared, external_network, vlan_transparent):
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/networks/?tab=networks__networks"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        create_button = driver.find_element_by_id("networks__action_create")
        create_button.click()

        network_name_input = driver.find_element_by_id("id_name")
        network_name_input.click()
        network_name_input.send_keys(network_name)

        project_input = Select(driver.find_element_by_id("id_tenant_id"))
        project_input.select_by_visible_text(project_name)

        network_type_input = Select(driver.find_element_by_id("id_network_type"))
        network_type_input.select_by_visible_text(network_type)

        physical_network_input = Select(driver.find_element_by_id("id_physical_network_vlan"))
        physical_network_input.select_by_visible_text(physical_network)

        segmentation_id_input = driver.find_element_by_id("id_segmentation_id")
        segmentation_id_input.click()
        segmentation_id_input.send_keys(segmentation_id)

        if(qos_policy == None):
            pass
        else:
            qos_policy_input = Select(driver.find_element_by_id("id_qos"))
            qos_policy_input.select_by_visible_text(qos_policy)

        if(shared == True):
            shared_input = driver.find_element_by_id("id_shared")
            shared_input.click()
        else:
            pass

        if(external_network == True):
            external_network_input = driver.find_element_by_id("id_external")
            external_network_input.click()
        else:
            pass

        if(vlan_transparent == True):
            vlan_transparent_input = driver.find_element_by_id("id_vlan_transparent")
            vlan_transparent_input.click()
        else:
            pass

        # Submit create network form
        network_name_input.submit()
        return network_name

    @classmethod
    def create_subnet(cls, network_name, subnet_name, network_address, gateway_ip, disable_gateway,
                      system_managed_subnet, dhcp, allocation_pools, dns_name_servers, host_routes, vlan):
        network_link = -1
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/admin/networks/?tab=networks__networks"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            # Match host_to_lock with link
            if(network_name in host_local):
                network_link = link.get_attribute("href")
        # Append to end of URL
        driver.get(DriverUtils.set_url(network_link))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        create_button = driver.find_element_by_id("subnets__action_create")
        create_button.click()

        subnet_name_input = driver.find_element_by_id("id_subnet_name")
        subnet_name_input.click()
        subnet_name_input.send_keys(subnet_name)

        network_address_input = driver.find_element_by_id("id_cidr")
        network_address_input.click()
        network_address_input.send_keys(network_address)

        if(gateway_ip == None):
            pass
        else:
            gateway_ip_input = driver.find_element_by_id("id_gateway_ip")
            gateway_ip_input.click()
            gateway_ip_input.send_keys(gateway_ip)

        if(disable_gateway == False):
            pass
        else:
            disable_gateway_input = driver.find_element_by_id("id_no_gateway")
            disable_gateway_input.click()

        next_button = driver.find_element_by_css_selector("button.btn-primary:nth-child(1)")
        next_button.click()

        if(system_managed_subnet == False):
            system_managed_subnet_input = driver.find_element_by_id("id_managed")
            system_managed_subnet_input.click()
        else:
            pass

        if(dhcp == False):
            dhcp_input = driver.find_element_by_id("id_enable_dhcp")
            dhcp_input.click()
        else:
            pass

        if(allocation_pools == None):
            pass
        else:
            allocation_pools_input = driver.find_element_by_id("id_allocation_pools")
            allocation_pools_input.click()
            allocation_pools_input.send_keys(allocation_pools)

        if(dns_name_servers == None):
            pass
        else:
            dns_name_servers_input = driver.find_element_by_id("id_dns_nameservers")
            dns_name_servers_input.click()
            dns_name_servers_input.send_keys(dns_name_servers)

        if(host_routes == None):
            pass
        else:
            host_routes_input = driver.find_element_by_id("id_host_routes")
            host_routes_input.click()
            host_routes_input.send_keys(host_routes)

        if(vlan == None):
            pass
        else:
            vlan_input = driver.find_element_by_id("id_vlan_id")
            vlan_input.click()
            vlan_input.send_keys(vlan)

        vlan_input = driver.find_element_by_id("id_vlan_id")
        vlan_input.submit()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)

    @classmethod
    def create_project_subnet(cls, network_name, subnet_name, network_address, gateway_ip, disable_gateway,
                              system_managed_subnet, dhcp, allocation_pools, dns_name_servers, host_routes, vlan):
        network_link = -1
        print network_name
        # Get driver
        driver = DriverUtils.get_driver()
        # Get URL text from class
        url = DriverUtils.get_url()
        # Append to end of URL
        driver.get(DriverUtils.set_url(url + "/project/networks/?tab=networks__networks"))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            print host_local
            # Match host_to_lock with link
            if(network_name in host_local):
                print network_name
                network_link = link.get_attribute("href")
        print network_link
        # Append to end of URL
        driver.get(DriverUtils.set_url(network_link))
        time.sleep(3)
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        create_button = driver.find_element_by_id("subnets__action_create")
        create_button.click()

        subnet_name_input = driver.find_element_by_id("id_subnet_name")
        subnet_name_input.click()
        subnet_name_input.send_keys(subnet_name)

        network_address_input = driver.find_element_by_id("id_cidr")
        network_address_input.click()
        network_address_input.send_keys(network_address)

        if(gateway_ip == None):
            pass
        else:
            gateway_ip_input = driver.find_element_by_id("id_gateway_ip")
            gateway_ip_input.click()
            gateway_ip_input.send_keys(gateway_ip)

        if(disable_gateway == False):
            pass
        else:
            disable_gateway_input = driver.find_element_by_id("id_no_gateway")
            disable_gateway_input.click()

        next_button = driver.find_element_by_css_selector("button.btn-primary:nth-child(1)")
        next_button.click()

        if(system_managed_subnet == False):
            system_managed_subnet_input = driver.find_element_by_id("id_managed")
            system_managed_subnet_input.click()
        else:
            pass

        if(dhcp == False):
            dhcp_input = driver.find_element_by_id("id_enable_dhcp")
            dhcp_input.click()
        else:
            pass

        if(allocation_pools == None):
            pass
        else:
            allocation_pools_input = driver.find_element_by_id("id_allocation_pools")
            allocation_pools_input.click()
            allocation_pools_input.send_keys(allocation_pools)

        if(dns_name_servers == None):
            pass
        else:
            dns_name_servers_input = driver.find_element_by_id("id_dns_nameservers")
            dns_name_servers_input.click()
            dns_name_servers_input.send_keys(dns_name_servers)

        if(host_routes == None):
            pass
        else:
            host_routes_input = driver.find_element_by_id("id_host_routes")
            host_routes_input.click()
            host_routes_input.send_keys(host_routes)

        if(vlan == None):
            pass
        else:
            vlan_input = driver.find_element_by_id("id_vlan_id")
            vlan_input.click()
            vlan_input.send_keys(vlan)

        vlan_input = driver.find_element_by_id("id_vlan_id")
        vlan_input.submit()
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)











































