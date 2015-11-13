from common_utils import DriverUtils
from lock_host import LockHost
from unlock_host import UnlockHost
from tenants import Tenants
from modify_quotas import ModifyQuotas
from login import Login
from key_pairs import KeyPairs
from flavors import Flavors
from networks import Networks
from logout import Logout
from hosts import Hosts
from routers import Routers
from volumes import Volumes
from images import Images
import settings
import time

__author__ = 'jbarber'


def main():
    """
    # Prep -------------------------------------------------------------------------------------------------------------
    rt = Images.get_guest_image()
    print rt
    # End of Prep ------------------------------------------------------------------------------------------------------
    """
    # LAB_SETUP GUI VERSION --------------------------------------------------------------------------------------------

    # Lab_Setup.conf example here
    project_name_one = "adminTest"
    project_name_two = "tenant1Test"
    project_name_three = "tenant2Test"
    tenant_list = [project_name_two, project_name_three]

    # Start web driver with firefox and set URL address to 10.10.10.2
    DriverUtils.open_driver(settings.DEFAULT_BROWSER)
    DriverUtils.set_url(settings.DEFAULT_URL)

    # Call login module
    Login.login("admin", "admin")

    # Wait for elements on page to load
    DriverUtils.wait_for_elements(settings.DEFAULT_ELEMENT_LOAD_TIME)

    # Create Tenants ---------------------------------------------------------------------------------------------------
    tenant_one = [project_name_one, project_name_one, "adminTest@noreply.com", project_name_one]
    tenant_two = [project_name_two, project_name_two, "tenant1Test@noreply.com", project_name_two]
    tenant_three = [project_name_three, project_name_three, "tenant2Test@noreply.com", project_name_three]

    Tenants.tenants(tenant_one[0], tenant_one[1], tenant_one[2], tenant_one[3])

    time.sleep(5)

    Tenants.tenants(tenant_two[0], tenant_two[1], tenant_two[2], tenant_two[3])

    time.sleep(5)

    Tenants.tenants(tenant_three[0], tenant_three[1], tenant_three[2], tenant_three[3])

    # End of Create Tenants --------------------------------------------------------------------------------------------

    time.sleep(5)

    # Modify Quotas ----------------------------------------------------------------------------------------------------
    # params (user_name, metadata Items, VCPUs, Instances, Injected Files, Injected File Content (Bytes), Volumes,
    # Volume Snapshots ,Total Size of Volumes and Snapshots (GB), RAM (MB), Security Groups, Security Groups Rules,
    # Floating IPs, Networks, Ports, Routers, Subnets)
    modify_tenant_one = [project_name_one, None, 0, 0, None, None, None, None, None, None, None, None, 0, 2, 10, None, 3]
    modify_tenant_two = [project_name_two, None, 2, 1, None, None, 2, 2, None, None, None, None, 1, 3, 39, None, 13]
    modify_tenant_three = [project_name_three, None, 2, 1, None, None, 2, 2, None, None, None, None, 1, 3, 39, None, 13]

    ModifyQuotas.quotas(modify_tenant_one[0], modify_tenant_one[1], modify_tenant_one[2], modify_tenant_one[3],
                        modify_tenant_one[4], modify_tenant_one[5], modify_tenant_one[6], modify_tenant_one[7],
                        modify_tenant_one[8], modify_tenant_one[9], modify_tenant_one[10], modify_tenant_one[11],
                        modify_tenant_one[12], modify_tenant_one[13], modify_tenant_one[14], modify_tenant_one[15],
                        modify_tenant_one[16])

    time.sleep(8)

    ModifyQuotas.quotas(modify_tenant_two[0], modify_tenant_two[1], modify_tenant_two[2], modify_tenant_two[3],
                        modify_tenant_two[4], modify_tenant_two[5], modify_tenant_two[6], modify_tenant_two[7],
                        modify_tenant_two[8], modify_tenant_two[9], modify_tenant_two[10], modify_tenant_two[11],
                        modify_tenant_two[12], modify_tenant_two[13], modify_tenant_two[14], modify_tenant_two[15],
                        modify_tenant_two[16])

    time.sleep(8)

    ModifyQuotas.quotas(modify_tenant_three[0], modify_tenant_three[1], modify_tenant_three[2], modify_tenant_three[3],
                        modify_tenant_three[4], modify_tenant_three[5], modify_tenant_three[6], modify_tenant_three[7],
                        modify_tenant_three[8], modify_tenant_three[9], modify_tenant_three[10], modify_tenant_three[11],
                        modify_tenant_three[12], modify_tenant_three[13], modify_tenant_three[14], modify_tenant_three[15],
                        modify_tenant_three[16])

    time.sleep(8)
    # End of Modify Quotas ---------------------------------------------------------------------------------------------

    # Create Flavors ---------------------------------------------------------------------------------------------------
    # Params (flavor_name, vcpus, ram, root_disk, ephemeral_disk, swap_disk)
    flavor_one = ["smallTest", 1, 512, 1, 0, 0, "CPU Policy", "Dedicated", "Memory Page Size", "2048"]
    flavor_two = ["medium.dpdkTest", 2, 1024, 1, 0, 0, "CPU Policy", "Dedicated", "Memory Page Size", "2048",
                  "VCPU Model", "Intel Core i7 9xx (Nehalem Class Core i7)"]
    flavor_three = ["small.floatTest", 1, 512, 1, 0, 0, "CPU Policy", "Dedicated", "Memory Page Size", "2048"]

    flavor_full_link = Flavors.flavors(flavor_one[0], flavor_one[1], flavor_one[2], flavor_one[3], flavor_one[4],
                                       flavor_one[5])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_one[6], flavor_one[7])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_one[8], flavor_one[9])
    time.sleep(8)
    flavor_full_link = Flavors.flavors(flavor_two[0], flavor_two[1], flavor_two[2], flavor_two[3], flavor_two[4],
                                       flavor_two[5])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_two[6], flavor_two[7])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_two[8], flavor_two[9])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_two[10], flavor_two[11])
    time.sleep(8)
    flavor_full_link = Flavors.flavors(flavor_three[0], flavor_three[1], flavor_three[2], flavor_three[3],
                                       flavor_three[4], flavor_three[5])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_three[6], flavor_three[7])
    time.sleep(5)
    Flavors.create_extra_spec(flavor_full_link, flavor_three[8], flavor_three[9])
    time.sleep(3)
    # End of Create Flavors --------------------------------------------------------------------------------------------

    # Create Key Pairs -------------------------------------------------------------------------------------------------
    Logout.logout()
    time.sleep(3)
    Login.login(project_name_two, project_name_two)
    time.sleep(3)
    # Create key-pair
    KeyPairs.key_pairs("keypair-tenant1Test")
    time.sleep(3)
    Logout.logout()
    time.sleep(3)
    Login.login(project_name_three, project_name_three)
    time.sleep(3)
    # Create key-pair
    KeyPairs.key_pairs("keypair-tenant2Test")
    time.sleep(3)
    Logout.logout()
    time.sleep(3)
    Login.login("admin", "admin")
    time.sleep(3)
    # End of Create Key Pairs ------------------------------------------------------------------------------------------

    # Provider Networks ------------------------------------------------------------------------------------------------
    provider_network_one = ["group0-ext0Test", "vlan", 1500, False, "group0-ext0-r0-0Test", True, None, 10, 10]
    provider_network_two = ["group0-data0Test", "vlan", 1500, False, "group0-data0-r1-0Test", True, project_name_two, 600, 615]
    provider_network_three = ["group0-data0bTest", "vlan", 1500, False, "group0-data0b-r2-0Test", True, None, 700, 731]
    provider_network_four = ["group0-data1Test", "vlan", 1500, False, "group0-data1-r3-0Test", True, project_name_three, 616, 631]

    provider_net_link = Networks.networks(provider_network_one[0], provider_network_one[1], provider_network_one[2],
                                          provider_network_one[3])
    time.sleep(4)
    # Create range for provider net above
    Networks.provider_net_range_create(provider_net_link, provider_network_one[4], provider_network_one[5],
                                       provider_network_one[6], provider_network_one[7], provider_network_one[8])
    time.sleep(4)
    provider_net_link = Networks.networks(provider_network_two[0], provider_network_two[1], provider_network_two[2],
                                          provider_network_two[3])
    time.sleep(4)
    # Create range for provider net above                         GET PROJECT Name TO HERE TO REPLACE NONE
    Networks.provider_net_range_create(provider_net_link, provider_network_two[4], provider_network_two[5],
                                       provider_network_two[6], provider_network_two[7], provider_network_two[8])
    time.sleep(4)
    provider_net_link = Networks.networks(provider_network_three[0], provider_network_three[1], provider_network_three[2],
                                          provider_network_three[3])
    time.sleep(4)
    # Create range for provider net above
    Networks.provider_net_range_create(provider_net_link, provider_network_three[4], provider_network_three[5],
                                       provider_network_three[6], provider_network_three[7], provider_network_three[8])
    time.sleep(4)
    provider_net_link = Networks.networks(provider_network_four[0], provider_network_four[1], provider_network_four[2],
                                          provider_network_four[3])
    time.sleep(4)
    # Create range for provider net above                        GET PROJECT Name TO HERE TO REPLACE NONE
    Networks.provider_net_range_create(provider_net_link, provider_network_four[4], provider_network_four[5],
                                       provider_network_four[6], provider_network_four[7], provider_network_four[8])
    time.sleep(3)
    # END Of Provider Networks------------------------------------------------------------------------------------------

    # SCRIPT EXPECTS COMPUTES TO BE ONLINE NOW
    # Check computes have 'Availability State' as 'Online'

    host_list = Hosts.hosts()

    # Create Interfaces ------------------------------------------------------------------------------------------------
    provider_net_list1 = ["group0-ext0Test", "group0-data0Test", "group0-data0Test"]
    provider_net_list2 = ["group0-data1Test"]

    for host in host_list:
        # Testing Problems Here (Not possible to test without fresh install??)
        # Hosts.create_interface(host[0], "data0Test", "data", "ethernet", "active/standby", "eth2", 1500, provider_net_list1)
        # Hosts.create_interface(host[0], "data1Test", "data", "ethernet", "active/standby", "eth3", 1500, provider_net_list2)
        time.sleep(3)
        # Host Profiles
        if_profile_name = "ifprofile-" + host[0] + "Test"
        time.sleep(3)
        cpu_profile_name = "cpuprofile-" + host[0] + "Test"
        time.sleep(3)
        mem_profile_name = "memprofile-" + host[0] + "Test"
        time.sleep(3)
        Hosts.create_interface_profile(host[0], if_profile_name)
        time.sleep(3)
        Hosts.create_cpu_profile(host[0], cpu_profile_name)
        time.sleep(3)
        Hosts.create_mem_profile(host[0], mem_profile_name)
        # Not sure how to apply profiles? Look like lab_setup.sh profiles when I create them
    # End of Create Interfaces -----------------------------------------------------------------------------------------

    # Create Images ----------------------------------------------------------------------------------------------------
    time.sleep(3)
    Images.images("cgcs-guest", "http://yow-ssp3-lx.wrs.com/buildarea3/users/jbarber/cgcs-guest.img", "Raw", False, None, None,
                  True, False)
    time.sleep(3)

    # End of Create Images ---------------------------------------------------------------------------------------------

    # Create Volumes ---------------------------------------------------------------------------------------------------
    Logout.logout()
    time.sleep(3)
    Login.login(project_name_two, project_name_two)
    time.sleep(3)
    Volumes.volumes("vol-tenant1-avp1Test", "Image", "cgcs-guest (608.0 MB)", "nova")
    time.sleep(3)
    Logout.logout()
    time.sleep(3)
    Login.login(project_name_three, project_name_three)
    time.sleep(3)
    Volumes.volumes("vol-tenant2-avp1Test", "Image", "cgcs-guest (608.0 MB)", "nova")
    time.sleep(3)
    Logout.logout()
    time.sleep(3)
    time.sleep(3)
    Login.login("admin", "admin")
    time.sleep(3)
    # End of Create Volumes --------------------------------------------------------------------------------------------

    # Create QoS Policies ----------------------------------------------------------------------------------------------

    qos_policy_list = ["external-qos","internal-qos"]

    Networks.create_qos_policy("external-qosTest", "External Network Policy", 16, "adminTest")
    time.sleep(4)
    Networks.create_qos_policy("internal-qosTest", "Internal Network Policy", 4, "adminTest")

    for tenant in tenant_list:
        name = tenant + "-mgmt-qosTest"
        desc = tenant + "Management Network PolicyTest"
        Networks.create_qos_policy(name, desc, 8, tenant)
        qos_policy_list.append(name)
    time.sleep(4)
    # End of Create QoS Policies ---------------------------------------------------------------------------------------

    # Create Networks --------------------------------------------------------------------------------------------------
    network_one = ["external-net0Test", project_name_one, "vlan", "group0-ext0Test", 10, "external-qos", True, True,
                   False]
    network_two = ["internal0-net0Test", project_name_one, "vlan", "group0-data0bTest", 701, "internal-qos", True,
                   False, False]
    network_three = ["tenant1-mgmt-netTest", project_name_two, "vlan", "group0-data0Test", 601,
                                           "tenant1Test-mgmt-qosTest", False, False, False]
    subnet_one = ["external-subnet0", "192.168.1.0/24", "192.168.1.1", False, True, False, "192.168.1.2,192.168.1.254",
                  None, None, None]
    subnet_two = ["internal0-subnet0-1", "10.0.1.0/24", None, True, False, False, None, None, None, 1]

    network_name = Networks.create_network(network_one[0], network_one[1], network_one[2], network_one[3],
                                           network_one[4], network_one[5], network_one[6], network_one[7],
                                           network_one[8])
    time.sleep(4)
    # Create subnet for network above
    Networks.create_subnet(network_name, subnet_one[0], subnet_one[1], subnet_one[2], subnet_one[3], subnet_one[4],
                           subnet_one[5], subnet_one[6], subnet_one[7], subnet_one[8], subnet_one[9])
    # WORKS FROM HERE UP!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    time.sleep(4)
    # Create Network
    network_name = Networks.create_network(network_two[0], network_two[1], network_two[2], network_two[3],
                                           network_two[4], network_two[5], network_two[6], network_two[7],
                                           network_two[8])
    time.sleep(4)
    # Create subnet for network above
    Networks.create_subnet(network_name, subnet_two[0], subnet_two[1], subnet_two[2], subnet_two[3], subnet_two[4],
                           subnet_two[5], subnet_two[6], subnet_two[7], subnet_two[8], subnet_two[9])
    time.sleep(4)
    # Create Network (NOTE: CHANGE 601 BACK TO 600 AFTER TESTING)
    network_name = Networks.create_network(network_three[0], network_three[1], network_three[2], network_three[3],
                                           network_three[4], network_three[5], network_three[6], network_three[7],
                                           network_three[8])
    # End of Create Networks -------------------------------------------------------------------------------------------

    # Create Router, router interfaces and Subnets ---------------------------------------------------------------------
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
                              "10.101.1.2,10.101.1.30", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, None]
    project_subnet_t1_four = ["tenant1-mgmt-subnet4", "10.101.1.32/27", "10.101.1.33", False, True, True,
                              "10.101.1.34,10.101.1.62", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]
    project_subnet_t1_five = ["tenant1-mgmt-subnet5", "10.101.1.64/27", "10.101.1.65", False, True, True,
                             "10.101.1.66,10.101.1.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1]


    project_subnet_t2_one = []
    project_subnet_t2_two = []
    project_subnet_t2_three = []
    project_subnet_t2_four = []
    project_subnet_t2_five = []

    time.sleep(4)
    Logout.logout()
    time.sleep(4)
    # Tenant 1 Router and Subnets

    Login.login(project_name_two, project_name_two)
    time.sleep(4)

    router_one = "tenant1-routerTest"
    router_link = Routers.routers(router_one, "external-net0Test")

    time.sleep(4)
    Networks.create_project_subnet(network_name, project_subnet_t1_zero[0],project_subnet_t1_zero[1],
                                   project_subnet_t1_zero[2], project_subnet_t1_zero[3], project_subnet_t1_zero[4],
                                   project_subnet_t1_zero[5], project_subnet_t1_zero[6], project_subnet_t1_zero[7],
                                   project_subnet_t1_zero[8], project_subnet_t1_zero[9])
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant1-mgmt-netTest: " + "192.168.101.0/27 " + "(tenant1-mgmt-subnet0)"
    Routers.create_router_interface(router_link, subnet_name, "192.168.101.1")
    time.sleep(4)
    Networks.create_project_subnet(network_name, project_subnet_t1_one[0],project_subnet_t1_one[1],
                                   project_subnet_t1_one[2], project_subnet_t1_one[3], project_subnet_t1_one[4],
                                   project_subnet_t1_one[5], project_subnet_t1_one[6], project_subnet_t1_one[7],
                                   project_subnet_t1_one[8], project_subnet_t1_one[9])
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant1-mgmt-netTest: " + "192.168.101.32/27 " + "(tenant1-mgmt-subnet1)"
    Routers.create_router_interface(router_link, subnet_name, "192.168.101.33")
    time.sleep(4)
    Networks.create_project_subnet(network_name, project_subnet_t1_two[0],project_subnet_t1_two[1],
                                   project_subnet_t1_two[2], project_subnet_t1_two[3], project_subnet_t1_two[4],
                                   project_subnet_t1_two[5], project_subnet_t1_two[6], project_subnet_t1_two[7],
                                   project_subnet_t1_two[8], project_subnet_t1_two[9])
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant1-mgmt-netTest: " + "192.168.101.64/27 " + "(tenant1-mgmt-subnet2)"
    Routers.create_router_interface(router_link, subnet_name, "192.168.101.65")
    time.sleep(4)
    Networks.create_project_subnet(network_name, project_subnet_t1_three[0],project_subnet_t1_three[1],
                                   project_subnet_t1_three[2], project_subnet_t1_three[3], project_subnet_t1_three[4],
                                   project_subnet_t1_three[5], project_subnet_t1_three[6], project_subnet_t1_three[7],
                                   project_subnet_t1_three[8], project_subnet_t1_three[9])
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant1-mgmt-netTest: " + "10.101.1.0/27 " + "(tenant1-mgmt-subnet3)"
    Routers.create_router_interface(router_link, subnet_name, "10.101.1.1")
    time.sleep(4)
    Networks.create_project_subnet(network_name, project_subnet_t1_four[0],project_subnet_t1_four[1],
                                   project_subnet_t1_four[2], project_subnet_t1_four[3], project_subnet_t1_four[4],
                                   project_subnet_t1_four[5], project_subnet_t1_four[6], project_subnet_t1_four[7],
                                   project_subnet_t1_four[8], project_subnet_t1_four[9])
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant1-mgmt-netTest: " + "10.101.1.32/27 " + "(tenant1-mgmt-subnet4)"
    Routers.create_router_interface(router_link, subnet_name, "10.101.1.33")
    time.sleep(4)
    Networks.create_project_subnet(network_name, project_subnet_t1_five[0],project_subnet_t1_five[1],
                                   project_subnet_t1_five[2], project_subnet_t1_five[3], project_subnet_t1_five[4],
                                   project_subnet_t1_five[5], project_subnet_t1_five[6], project_subnet_t1_five[7],
                                   project_subnet_t1_five[8], project_subnet_t1_five[9])
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant1-mgmt-netTest: " + "10.101.1.64/27 " + "(tenant1-mgmt-subnet5)"
    Routers.create_router_interface(router_link, subnet_name, "10.101.1.65")
    time.sleep(4)

    Logout.logout()
    time.sleep(4)
    Login.login("admin", "admin")

    # Tenant 2 Router and Subnets
    time.sleep(4)
    # Create Network
    # Create Network (NOTE: CHANGE 617 BACK TO 616 AFTER TESTING)
    network_name = Networks.create_network("tenant2-mgmt-netTest", project_name_three, "vlan", "group0-data1Test", 617,
                                           "tenant2Test-mgmt-qosTest", False, False, False)
    time.sleep(4)
    Logout.logout()
    time.sleep(4)
    Login.login(project_name_three, project_name_three)
    time.sleep(4)
    router_two = "tenant2-routerTest"
    time.sleep(4)
    router_link = Routers.routers(router_two, "external-net0Test")
    time.sleep(4)
    Networks.create_project_subnet(network_name, "tenant2-mgmt-subnet0", "192.168.201.0/27", "192.168.201.1", False,
                            True, True, "192.168.201.2,192.168.201.30", "147.11.57.133\n128.224.144.130\n147.11.57.128",
                            None, None)
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant2-mgmt-netTest: " + "192.168.201.0/27 " + "(tenant2-mgmt-subnet0)"
    Routers.create_router_interface(router_link, subnet_name, "192.168.201.1")
    time.sleep(4)
    Networks.create_project_subnet(network_name, "tenant2-mgmt-subnet1", "192.168.201.32/27", "192.168.201.33", False,
                            True, True, "192.168.201.34,192.168.201.62", "147.11.57.133\n128.224.144.130\n147.11.57.128",
                            None, None)
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant2-mgmt-netTest: " + "192.168.201.32/27 " + "(tenant2-mgmt-subnet1)"
    Routers.create_router_interface(router_link, subnet_name, "192.168.201.33")
    time.sleep(4)
    Networks.create_project_subnet(network_name, "tenant2-mgmt-subnet2", "192.168.201.64/27", "192.168.201.65", False, True,
                           True, "192.168.201.66,192.168.201.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, None)
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant2-mgmt-netTest: " + "192.168.201.64/27 " + "(tenant2-mgmt-subnet2)"
    Routers.create_router_interface(router_link, subnet_name, "192.168.201.65")
    time.sleep(4)
    Networks.create_project_subnet(network_name, "tenant2-mgmt-subnet3", "10.201.1.0/27", "10.201.1.1", False, True,
                           True, "10.201.1.2,10.201.1.30", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1)
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant2-mgmt-netTest: " + "10.201.1.0/27 " + "(tenant2-mgmt-subnet3)"
    Routers.create_router_interface(router_link, subnet_name, "10.201.1.1")
    time.sleep(4)
    Networks.create_project_subnet(network_name, "tenant2-mgmt-subnet4", "10.201.1.32/27", "10.201.1.33", False, True,
                           True, "10.201.1.34,10.201.1.62", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1)
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant2-mgmt-netTest: " + "10.201.1.32/27 " + "(tenant2-mgmt-subnet4)"
    Routers.create_router_interface(router_link, subnet_name, "10.201.1.33")
    time.sleep(4)
    Networks.create_project_subnet(network_name, "tenant2-mgmt-subnet5", "10.201.1.64/27", "10.201.1.65", False, True,
                           True, "10.201.1.66,10.201.1.94", "147.11.57.133\n128.224.144.130\n147.11.57.128", None, 1)
    time.sleep(4)
    # Create router interface
    subnet_name = "tenant2-mgmt-netTest: " + "10.201.1.64/27 " + "(tenant2-mgmt-subnet5)"
    Routers.create_router_interface(router_link, subnet_name, "10.201.1.65")
    time.sleep(4)
    Logout.logout()
    time.sleep(4)
    Login.login("admin", "admin")
    time.sleep(4)

    network_name = Networks.create_network("tenant1-net0Test", project_name_two, "vlan", "group0-data0Test", 602,
                                           None, False, False, False)
    time.sleep(4)
    # Create Subnet
    Networks.create_subnet(network_name, "tenant1-subnet0", "172.16.0.0/24", None, True, False, False, None, None, None,
                           None)
    time.sleep(4)
    network_name = Networks.create_network("tenant2-net0Test", project_name_three, "vlan", "group0-data1Test", 618,
                                           None, False, False, False)
    time.sleep(4)
    # Create Subnet
    Networks.create_subnet(network_name, "tenant2-subnet0", "172.18.0.0/24", None, True, False, False, None, None, None,
                           None)

if __name__ == "__main__":
    main()


