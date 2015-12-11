'''
lab_setup_horizon.py - Entry point for lab setup in Horizon using Selenium for VirtualBox

Copyright (c) 2015 Wind River Systems, Inc.

The right to copy, distribute, modify, or otherwise make use
of this software may be licensed only pursuant to the terms
of an applicable Wind River license agreement.


This is the entry point of the lab setup in Horizon for VirtualBox. It runs
every command that lab_setup.sh would run for a VirtualBox setup.
'''

'''
modification history:
---------------------
26nov15,jbb  Initial file
30nov15,jbb  Add catch all exceptions
30nov15,jbb  Add parse args
'''

from common_utils import DriverUtils
from tenants import Tenants
from modify_quotas import ModifyQuotas
from authentication import Login
from authentication import Logout
from key_pairs import KeyPairs
from flavors import Flavors
from networks import Networks
from hosts import Hosts
from routers import Routers
from volumes import Volumes
from images import Images
import settings
import argparse
import traceback


def main():

    # Get opts
    parser = argparse.ArgumentParser(
        description='Automated lab setup in Horizon')
    parser.add_argument("--headless",
                        help="Must have pyvirtualdisplay module", required=False, action='store_true')
    args = parser.parse_args()
    try:

        # Prep ---------------------------------------------------------------------------------------------------------
        Images.get_guest_image()
        print "Test: PASS - Get cgcs-guest.img"
        # End of Prep --------------------------------------------------------------------------------------------------

        # LAB_SETUP GUI VERSION ----------------------------------------------------------------------------------------
        project_name_one = "admin"
        project_name_two = "tenant1"
        project_name_three = "tenant2"
        tenant_list = [project_name_two, project_name_three]

        # Start web driver with firefox and set URL address to 10.10.10.2
        DriverUtils.open_driver(settings.DEFAULT_BROWSER, args.headless)
        DriverUtils.set_url(settings.DEFAULT_URL)

        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

        # Call login module
        Login.login(project_name_one, project_name_one)

        # Wait for elements on page to load
        DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)
        print "Test: PASS - Begin Lab Setup"

        # Create Tenants -----------------------------------------------------------------------------------------------
        tenant_two = [project_name_two, project_name_two, "tenant1@noreply.com", project_name_two]
        tenant_three = [project_name_three, project_name_three, "tenant2t@noreply.com", project_name_three]

        Tenants.tenants(tenant_two[0], tenant_two[1], tenant_two[2], tenant_two[3])
        Tenants.tenants(tenant_three[0], tenant_three[1], tenant_three[2], tenant_three[3])
        print "Test: PASS - Create tenants"
        # End of Create Tenants ----------------------------------------------------------------------------------------

        # Modify Quotas ------------------------------------------------------------------------------------------------
        # params (user_name, metadata Items, VCPUs, Instances, Injected Files, Injected File Content (Bytes), Volumes,
        # Volume Snapshots ,Total Size of Volumes and Snapshots (GB), RAM (MB), Security Groups, Security Groups Rules,
        # Floating IPs, Networks, Ports, Routers, Subnets)
        quota_dict_tenant_one = {'id_metadata_items': None, 'id_cores': [0, 'text'], 'id_instances': [0, 'text'],
                            'id_injected_files': None, 'id_injected_file_content_bytes': None, 'id_volumes': [2, 'text'],
                            'id_snapshots': [2, 'text'], 'id_gigabytes': None, 'id_ram': None, 'id_security_group': None,
                            'id_security_group_rule': None, 'id_floatingip': [0, 'text'], 'id_network': [4, 'text'],
                            'id_port': [10, 'text'], 'id_router': None, 'id_subnet': [3, 'text']}
        quota_dict_tenant_two = {'id_metadata_items': None, 'id_cores': [2, 'text'], 'id_instances': [1, 'text'],
                            'id_injected_files': None, 'id_injected_file_content_bytes': None, 'id_volumes': [2, 'text'],
                            'id_snapshots': [2, 'text'], 'id_gigabytes': None, 'id_ram': None, 'id_security_group': None,
                            'id_security_group_rule': None, 'id_floatingip': [1, 'text'], 'id_network': [3, 'text'],
                            'id_port': [39, 'text'], 'id_router': None, 'id_subnet': [13, 'text']}
        quota_dict_tenant_three = {'id_metadata_items': None, 'id_cores': [2, 'text'], 'id_instances': [1, 'text'],
                            'id_injected_files': None, 'id_injected_file_content_bytes': None, 'id_volumes': [2, 'text'],
                            'id_snapshots': [2, 'text'], 'id_gigabytes': None, 'id_ram': None, 'id_security_group': None,
                            'id_security_group_rule': None, 'id_floatingip': [1, 'text'], 'id_network': [3, 'text'],
                            'id_port': [39, 'text'], 'id_router': None, 'id_subnet': [13, 'text']}
        ModifyQuotas.quotas(project_name_one, quota_dict_tenant_one)
        ModifyQuotas.quotas(project_name_two, quota_dict_tenant_two)
        ModifyQuotas.quotas(project_name_three, quota_dict_tenant_three)
        print "Test: PASS - Modify quotas"
        # End of Modify Quotas -----------------------------------------------------------------------------------------

        # Create Flavors -----------------------------------------------------------------------------------------------
        # Params (flavor_name, vcpus, ram, root_disk, ephemeral_disk, swap_disk)
        flavor_one = ["small", 1, 512, 1, 0, 0, "CPU Policy", "Dedicated", "Memory Page Size", "2048"]
        flavor_two = ["medium.dpdk", 2, 1024, 1, 0, 0, "CPU Policy", "Dedicated", "Memory Page Size", "2048",
                      "VCPU Model", "Intel Core i7 9xx (Nehalem Class Core i7)"]
        flavor_three = ["small.float", 1, 512, 1, 0, 0, "CPU Policy", "Dedicated", "Memory Page Size", "2048"]

        flavor_full_link = Flavors.flavors(flavor_one[0], flavor_one[1], flavor_one[2], flavor_one[3], flavor_one[4],
                                           flavor_one[5])
        Flavors.create_extra_spec(flavor_full_link, flavor_one[6], flavor_one[7])
        Flavors.create_extra_spec(flavor_full_link, flavor_one[8], flavor_one[9])
        flavor_full_link = Flavors.flavors(flavor_two[0], flavor_two[1], flavor_two[2], flavor_two[3], flavor_two[4],
                                           flavor_two[5])
        Flavors.create_extra_spec(flavor_full_link, flavor_two[6], flavor_two[7])
        Flavors.create_extra_spec(flavor_full_link, flavor_two[8], flavor_two[9])
        Flavors.create_extra_spec(flavor_full_link, flavor_two[10], flavor_two[11])
        flavor_full_link = Flavors.flavors(flavor_three[0], flavor_three[1], flavor_three[2], flavor_three[3],
                                           flavor_three[4], flavor_three[5])
        Flavors.create_extra_spec(flavor_full_link, flavor_three[6], flavor_three[7])
        Flavors.create_extra_spec(flavor_full_link, flavor_three[8], flavor_three[9])
        print "Test: PASS - Create flavors"
        # End of Create Flavors ----------------------------------------------------------------------------------------

        # Create Key Pairs ---------------------------------------------------------------------------------------------
        Logout.logout()
        Login.login(project_name_two, project_name_two)
        KeyPairs.key_pairs("keypair-tenant1")
        Logout.logout()
        Login.login(project_name_three, project_name_three)
        KeyPairs.key_pairs("keypair-tenant2")
        Logout.logout()
        Login.login(project_name_one, project_name_one)
        print "Test: PASS - Create key pairs"
        # End of Create Key Pairs --------------------------------------------------------------------------------------
        # Provider Networks --------------------------------------------------------------------------------------------
        provider_network_one = ["group0-ext0", "vlan", 1500, True, "group0-ext0-r0-0", True, None, 10, 10]
        provider_network_two = ["group0-data0", "vlan", 1500, True, "group0-data0-r1-0", True, project_name_two, 600, 615]
        provider_network_three = ["group0-data0b", "vlan", 1500, True, "group0-data0b-r2-0", True, None, 700, 731]
        provider_network_four = ["group0-data1", "vlan", 1500, True, "group0-data1-r3-0", True, project_name_three, 616, 631]

        provider_net_link = Networks.networks(provider_network_one[0], provider_network_one[1], provider_network_one[2],
                                              provider_network_one[3])
        print provider_net_link
        # Create range for provider net above
        Networks.provider_net_range_create(provider_net_link, provider_network_one[4], provider_network_one[5],
                                           provider_network_one[6], provider_network_one[7], provider_network_one[8])
        provider_net_link = Networks.networks(provider_network_two[0], provider_network_two[1], provider_network_two[2],
                                              provider_network_two[3])
        # Create range for provider net above
        Networks.provider_net_range_create(provider_net_link, provider_network_two[4], provider_network_two[5],
                                           provider_network_two[6], provider_network_two[7], provider_network_two[8])
        provider_net_link = Networks.networks(provider_network_three[0], provider_network_three[1], provider_network_three[2],
                                              provider_network_three[3])
        # Create range for provider net above
        Networks.provider_net_range_create(provider_net_link, provider_network_three[4], provider_network_three[5],
                                           provider_network_three[6], provider_network_three[7], provider_network_three[8])
        provider_net_link = Networks.networks(provider_network_four[0], provider_network_four[1], provider_network_four[2],
                                              provider_network_four[3])
        # Create range for provider net above
        Networks.provider_net_range_create(provider_net_link, provider_network_four[4], provider_network_four[5],
                                           provider_network_four[6], provider_network_four[7], provider_network_four[8])
        print "Test: PASS - Create provider networks"
        # END Of Provider Networks--------------------------------------------------------------------------------------

        # SCRIPT EXPECTS COMPUTES TO BE ONLINE NOW
        # Check computes have 'Availability State' as 'Online'
        host_list = Hosts.hosts()

        # Create Interfaces & Modify Hosts -----------------------------------------------------------------------------
        provider_net_list1 = ["group0-ext0", "group0-data0", "group0-data0b"]
        provider_net_list2 = ["group0-data1"]

        for hostname in host_list:
            Hosts.modify_interface(hostname[0], "data0", "data", "eth2", 1500, provider_net_list1)
            Hosts.modify_interface(hostname[0], "data1", "data", "eth3", 1500, provider_net_list2)
            # Local storage changes:
            Hosts.add_local_storage(hostname[0], 2048)

        # Controller-1 Changes:
        # Modify OAM interfaces for controller-1
        Hosts.modify_interface("controller-1", "oam0", "oam", "eth0", 1500, None)
        # Add cinder device configuration for controller-1
        Hosts.create_cinder_device("controller-1")


        for host in host_list:
            # Host Profiles
            if_profile_name = "ifprofile-" + host[0]
            cpu_profile_name = "cpuprofile-" + host[0]
            mem_profile_name = "memprofile-" + host[0]
            Hosts.create_interface_profile(host[0], if_profile_name)
            Hosts.create_cpu_profile(host[0], cpu_profile_name)
            Hosts.create_mem_profile(host[0], mem_profile_name)
            # Not sure how to apply profiles? Look like lab_setup.sh profiles when I create them
        print "Test: PASS - Create & modify host interfaces"
        # Create Interfaces & Modify Hosts -----------------------------------------------------------------------------

        # Create Images ------------------------------------------------------------------------------------------------
        # FIX TODO: Jira: https://jira.wrs.com:8443/browse/CGTS-3158
        # TODO: If Jira above is fixed, please uncomment the two lines of code (Images.images) below.
        # TODO: You no longer need to manually createthe guest image.
        # Images.images("cgcs-guest", "http://yow-cgcs-test.wrs.com/files/cgcs_guestimg/cgcs-guest.img", "Raw", False,
        #              None, None, True, False)
        print "Test: PASS - Create image"
        # End of Create Images -----------------------------------------------------------------------------------------

        # Create Volumes -----------------------------------------------------------------------------------------------
        Logout.logout()
        Login.login(project_name_two, project_name_two)
        Volumes.volumes("vol-tenant1-avp1", "Image", "cgcs-guest (608.0 MB)", "nova")
        Logout.logout()
        Login.login(project_name_three, project_name_three)
        Volumes.volumes("vol-tenant2-avp1", "Image", "cgcs-guest (608.0 MB)", "nova")
        Logout.logout()
        Login.login(project_name_one, project_name_one)
        print "Test: PASS - Create volumes"
        # End of Create Volumes ----------------------------------------------------------------------------------------

        # Create QoS Policies ------------------------------------------------------------------------------------------
        qos_policy_list = ["external-qos","internal-qos"]

        Networks.create_qos_policy("external-qos", "External Network Policy", 16, project_name_one)
        Networks.create_qos_policy("internal-qos", "Internal Network Policy", 4, project_name_one)

        for tenant in tenant_list:
            name = tenant + "-mgmt-qos"
            desc = tenant + "Management Network Policy"
            Networks.create_qos_policy(name, desc, 8, tenant)
            qos_policy_list.append(name)
        print "Test: PASS - QoS policies"
        # End of Create QoS Policies -----------------------------------------------------------------------------------

        # Create Networks ----------------------------------------------------------------------------------------------
        network_one = ["external-net0", project_name_one, "vlan", "group0-ext0", 10, "external-qos", True, True,
                       False]
        network_two = ["internal0-net0", project_name_one, "vlan", "group0-data0b", 700, "internal-qos", True,
                       False, False]
        network_three = ["tenant1-mgmt-net", project_name_two, "vlan", "group0-data0", None,
                                               "tenant1-mgmt-qos", False, False, False]
        subnet_one = ["external-subnet0", "192.168.1.0/24", "192.168.1.1", False, True, False, "192.168.1.2,192.168.1.254",
                      None, None, None]
        subnet_two = ["internal0-subnet0-1", "10.0.1.0/24", None, True, False, False, None, None, None, 1]

        network_name = Networks.create_network(network_one[0], network_one[1], network_one[2], network_one[3],
                                               network_one[4], network_one[5], network_one[6], network_one[7],
                                               network_one[8])
        # Create subnet for network above
        Networks.create_subnet(network_name, subnet_one[0], subnet_one[1], subnet_one[2], subnet_one[3], subnet_one[4],
                               subnet_one[5], subnet_one[6], subnet_one[7], subnet_one[8], subnet_one[9])

        # Create Network
        network_name = Networks.create_network(network_two[0], network_two[1], network_two[2], network_two[3],
                                               network_two[4], network_two[5], network_two[6], network_two[7],
                                               network_two[8])
        # Create subnet for network above
        Networks.create_subnet(network_name, subnet_two[0], subnet_two[1], subnet_two[2], subnet_two[3], subnet_two[4],
                               subnet_two[5], subnet_two[6], subnet_two[7], subnet_two[8], subnet_two[9])

        network_name = Networks.create_network(network_three[0], network_three[1], network_three[2], network_three[3],
                                               network_three[4], network_three[5], network_three[6], network_three[7],
                                               network_three[8])
        print "Test: PASS - Create networks"
        # End of Create Networks ---------------------------------------------------------------------------------------

        # Create Router, router interfaces and Subnets -----------------------------------------------------------------
        # ...............................................Tenant 1.......................................................
        project_subnet_t1_zero = ["tenant1-mgmt-subnet0", "192.168.101.0/27", "192.168.101.1", False, True, True,
                                  "192.168.101.2,192.168.101.30", "147.11.57.133\n128.224.144.130\n147.11.57.128", None,
                                  None]
        project_subnet_t1_one = ["tenant1-mgmt-subnet1", "192.168.101.32/27", "192.168.101.33", False, True, True,
                                 "192.168.101.34,192.168.101.62", "147.11.57.133\n128.224.144.130\n147.11.57.128", None,
                                 None]
        project_subnet_t1_two = ["tenant1-mgmt-subnet2", "192.168.101.64/27", "192.168.101.65", False, True, True,
                                 "192.168.101.66,192.168.101.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None,
                                   None]
        project_subnet_t1_three = ["tenant1-mgmt-subnet3", "10.101.1.0/27", "10.101.1.1", False, True, True,
                                   "10.101.1.2,10.101.1.30", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]
        project_subnet_t1_four = ["tenant1-mgmt-subnet4", "10.101.1.32/27", "10.101.1.33", False, True, True,
                                  "10.101.1.34,10.101.1.62", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]
        project_subnet_t1_five = ["tenant1-mgmt-subnet5", "10.101.1.64/27", "10.101.1.65", False, True, True,
                                  "10.101.1.66,10.101.1.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]
        Logout.logout()
        # Tenant 1 Router and Subnets
        Login.login(project_name_two, project_name_two)
        router_one = "tenant1-router"
        router_link = Routers.routers(router_one, "external-net0")
        Networks.create_project_subnet(network_name, project_subnet_t1_zero[0],project_subnet_t1_zero[1],
                                       project_subnet_t1_zero[2], project_subnet_t1_zero[3], project_subnet_t1_zero[4],
                                       project_subnet_t1_zero[5], project_subnet_t1_zero[6], project_subnet_t1_zero[7],
                                       project_subnet_t1_zero[8], project_subnet_t1_zero[9])
        # Create router interface
        subnet_name = "tenant1-mgmt-net: " + "192.168.101.0/27 " + "(tenant1-mgmt-subnet0)"
        Routers.create_router_interface(router_link, subnet_name, "192.168.101.1")
        Networks.create_project_subnet(network_name, project_subnet_t1_one[0],project_subnet_t1_one[1],
                                       project_subnet_t1_one[2], project_subnet_t1_one[3], project_subnet_t1_one[4],
                                       project_subnet_t1_one[5], project_subnet_t1_one[6], project_subnet_t1_one[7],
                                       project_subnet_t1_one[8], project_subnet_t1_one[9])
        # Create router interface
        subnet_name = "tenant1-mgmt-net: " + "192.168.101.32/27 " + "(tenant1-mgmt-subnet1)"
        Routers.create_router_interface(router_link, subnet_name, "192.168.101.33")
        Networks.create_project_subnet(network_name, project_subnet_t1_two[0],project_subnet_t1_two[1],
                                       project_subnet_t1_two[2], project_subnet_t1_two[3], project_subnet_t1_two[4],
                                       project_subnet_t1_two[5], project_subnet_t1_two[6], project_subnet_t1_two[7],
                                       project_subnet_t1_two[8], project_subnet_t1_two[9])
        # Create router interface
        subnet_name = "tenant1-mgmt-net: " + "192.168.101.64/27 " + "(tenant1-mgmt-subnet2)"
        Routers.create_router_interface(router_link, subnet_name, "192.168.101.65")
        Networks.create_project_subnet(network_name, project_subnet_t1_three[0],project_subnet_t1_three[1],
                                       project_subnet_t1_three[2], project_subnet_t1_three[3], project_subnet_t1_three[4],
                                       project_subnet_t1_three[5], project_subnet_t1_three[6], project_subnet_t1_three[7],
                                       project_subnet_t1_three[8], project_subnet_t1_three[9])
        # Create router interface
        subnet_name = "tenant1-mgmt-net: " + "10.101.1.0/27 " + "(tenant1-mgmt-subnet3)"
        Routers.create_router_interface(router_link, subnet_name, "10.101.1.1")
        Networks.create_project_subnet(network_name, project_subnet_t1_four[0],project_subnet_t1_four[1],
                                       project_subnet_t1_four[2], project_subnet_t1_four[3], project_subnet_t1_four[4],
                                       project_subnet_t1_four[5], project_subnet_t1_four[6], project_subnet_t1_four[7],
                                       project_subnet_t1_four[8], project_subnet_t1_four[9])
        # Create router interface
        subnet_name = "tenant1-mgmt-net: " + "10.101.1.32/27 " + "(tenant1-mgmt-subnet4)"
        Routers.create_router_interface(router_link, subnet_name, "10.101.1.33")
        Networks.create_project_subnet(network_name, project_subnet_t1_five[0],project_subnet_t1_five[1],
                                       project_subnet_t1_five[2], project_subnet_t1_five[3], project_subnet_t1_five[4],
                                       project_subnet_t1_five[5], project_subnet_t1_five[6], project_subnet_t1_five[7],
                                       project_subnet_t1_five[8], project_subnet_t1_five[9])
        # Create router interface
        subnet_name = "tenant1-mgmt-net: " + "10.101.1.64/27 " + "(tenant1-mgmt-subnet5)"
        Routers.create_router_interface(router_link, subnet_name, "10.101.1.65")
        Logout.logout()
        Login.login(project_name_one, project_name_one)
        Routers.router_distributed(router_link, False)
        print "Test: PASS - Create router & subnets for tenant 1"
        # ............................................End of Tenant 1...................................................

        # ...............................................Tenant 2.......................................................

        project_subnet_t2_zero = ["tenant2-mgmt-subnet0", "192.168.201.0/27", "192.168.201.1", False, True, True,
                                  "192.168.201.2,192.168.201.30", "147.11.57.133\n128.224.144.130\n147.11.57.128", None,
                                  None]
        project_subnet_t2_one = ["tenant2-mgmt-subnet1", "192.168.201.32/27", "192.168.201.33", False, True, True,
                                 "192.168.201.34,192.168.201.62", "147.11.57.133\n128.224.144.130\n147.11.57.128", None,
                                 None]
        project_subnet_t2_two = ["tenant2-mgmt-subnet2", "192.168.201.64/27", "192.168.201.65", False, True, True,
                                 "192.168.201.66,192.168.201.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None,
                                 None]
        project_subnet_t2_three = ["tenant2-mgmt-subnet3", "10.201.1.0/27", "10.201.1.1", False, True, True,
                                   "10.201.1.2,10.201.1.30", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]
        project_subnet_t2_four = ["tenant2-mgmt-subnet4", "10.201.1.32/27", "10.201.1.33", False, True, True,
                                  "10.201.1.34,10.201.1.62", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]
        project_subnet_t2_five = ["tenant2-mgmt-subnet5", "10.201.1.64/27", "10.201.1.65", False, True, True,
                                  "10.201.1.66,10.201.1.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]

        # Tenant 2 Router and Subnets
        # Create Network
        network_name = Networks.create_network("tenant2-mgmt-net", project_name_three, "vlan", "group0-data1", None,
                                               "tenant2-mgmt-qos", False, False, False)
        Logout.logout()
        Login.login(project_name_three, project_name_three)
        router_two = "tenant2-router"
        router_link = Routers.routers(router_two, "external-net0")
        Networks.create_project_subnet(network_name, project_subnet_t2_zero[0],project_subnet_t2_zero[1],
                                       project_subnet_t2_zero[2], project_subnet_t2_zero[3], project_subnet_t2_zero[4],
                                       project_subnet_t2_zero[5], project_subnet_t2_zero[6], project_subnet_t2_zero[7],
                                       project_subnet_t2_zero[8], project_subnet_t2_zero[9])
        # Create router interface
        subnet_name = "tenant2-mgmt-net: " + "192.168.201.0/27 " + "(tenant2-mgmt-subnet0)"
        Routers.create_router_interface(router_link, subnet_name, "192.168.201.1")
        Networks.create_project_subnet(network_name, project_subnet_t2_one[0],project_subnet_t2_one[1],
                                       project_subnet_t2_one[2], project_subnet_t2_one[3], project_subnet_t2_one[4],
                                       project_subnet_t2_one[5], project_subnet_t2_one[6], project_subnet_t2_one[7],
                                       project_subnet_t2_one[8], project_subnet_t2_one[9])
        # Create router interface
        subnet_name = "tenant2-mgmt-net: " + "192.168.201.32/27 " + "(tenant2-mgmt-subnet1)"
        Routers.create_router_interface(router_link, subnet_name, "192.168.201.33")
        Networks.create_project_subnet(network_name, project_subnet_t2_two[0],project_subnet_t2_two[1],
                                       project_subnet_t2_two[2], project_subnet_t2_two[3], project_subnet_t2_two[4],
                                       project_subnet_t2_two[5], project_subnet_t2_two[6], project_subnet_t2_two[7],
                                       project_subnet_t2_two[8], project_subnet_t2_two[9])
        # Create router interface
        subnet_name = "tenant2-mgmt-net: " + "192.168.201.64/27 " + "(tenant2-mgmt-subnet2)"
        Routers.create_router_interface(router_link, subnet_name, "192.168.201.65")
        Networks.create_project_subnet(network_name, project_subnet_t2_three[0],project_subnet_t2_three[1],
                                       project_subnet_t2_three[2], project_subnet_t2_three[3], project_subnet_t2_three[4],
                                       project_subnet_t2_three[5], project_subnet_t2_three[6], project_subnet_t2_three[7],
                                       project_subnet_t2_three[8], project_subnet_t2_three[9])
        # Create router interface
        subnet_name = "tenant2-mgmt-net: " + "10.201.1.0/27 " + "(tenant2-mgmt-subnet3)"
        Routers.create_router_interface(router_link, subnet_name, "10.201.1.1")
        Networks.create_project_subnet(network_name, project_subnet_t2_four[0],project_subnet_t2_four[1],
                                       project_subnet_t2_four[2], project_subnet_t2_four[3], project_subnet_t2_four[4],
                                       project_subnet_t2_four[5], project_subnet_t2_four[6], project_subnet_t2_four[7],
                                       project_subnet_t2_four[8], project_subnet_t2_four[9])
        # Create router interface
        subnet_name = "tenant2-mgmt-net: " + "10.201.1.32/27 " + "(tenant2-mgmt-subnet4)"
        Routers.create_router_interface(router_link, subnet_name, "10.201.1.33")
        Networks.create_project_subnet(network_name, project_subnet_t2_five[0],project_subnet_t2_five[1],
                                       project_subnet_t2_five[2], project_subnet_t2_five[3], project_subnet_t2_five[4],
                                       project_subnet_t2_five[5], project_subnet_t2_five[6], project_subnet_t2_five[7],
                                       project_subnet_t2_five[8], project_subnet_t2_five[9])
        # Create router interface
        subnet_name = "tenant2-mgmt-net: " + "10.201.1.64/27 " + "(tenant2-mgmt-subnet5)"
        Routers.create_router_interface(router_link, subnet_name, "10.201.1.65")
        Logout.logout()
        Login.login(project_name_one, project_name_one)
        Routers.router_distributed(router_link, True)
        network_name = Networks.create_network("tenant1-net0", project_name_two, "vlan", "group0-data0", None,
                                               None, False, False, False)
        # Create Subnet
        Networks.create_subnet(network_name, "tenant1-subnet0", "172.16.0.0/24", None, True, False, False, None, None, None,
                               None)
        network_name = Networks.create_network("tenant2-net0", project_name_three, "vlan", "group0-data1", None,
                                               None, False, False, False)
        # Create Subnet
        Networks.create_subnet(network_name, "tenant2-subnet0", "172.18.0.0/24", None, True, False, False, None, None, None,
                               None)
        print "Test: PASS - Create router & subnets for tenant 2"
        # ............................................End of Tenant 2...................................................

        print "Test: UI Tests finished"
        DriverUtils.driver.quit()

    except:
        print "Test: FAIL - Exception Thrown"
        traceback.print_exc()
        print "Common exceptions are: Timeout,\nElementNotVisibleException,\nElementNotSelectableException,\n" \
              "NoSuchElementException"


if __name__ == "__main__":
    main()
