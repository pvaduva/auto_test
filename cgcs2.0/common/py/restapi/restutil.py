#!/usr/bin/env python

"""
This file contains methods for common system operations such as getting
controller personality, checking if we have storage nodes, etc. 

"""

from restapi import *

class RestUtil(RestAPI):
    def __init__(self, ip=IP):
        RestAPI.__init__(self,ip=ip) 

    def get_controller_personality(self):
        """ This method returns a list of dicts containing the controller hostname
            along with its personality.  e.g.

            [{u"controller-0", u"Controller-Active"}, .. ]
        """

        logging.info("Return controller personalities")

        hostpersonality_list = [] 

        # Get ihost data
        data = x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")

        # Parse ihost data for controller hostname and personality
        for d, l in data.items():
            for item in l:
                if item[u"personality"] == u"controller":
                    host_dict = {}
                    hostname = item[u"hostname"]
                    personality = item[u"capabilities"][u"Personality"]
                    host_dict[hostname] = personality
                    hostpersonality_list.append(host_dict)

        pprint.pprint(hostpersonality_list)
        return hostpersonality_list

    def get_active_controller(self):
        """ This method returns the active controller as a string, e.g. controller-0
        """

        hostpersonality_list = RestUtil.get_controller_personality(self)

        logging.info("Checking for active controller")
        # Check which controller is active
        for item in hostpersonality_list: 
            for hostname in item:
                if item[hostname] == "Controller-Active":
                    logging.info("Active controller is: %s" % hostname)
                    return hostname

        # If we didn't return yet, that is an error
        logging.error("No active controller found")
        return 1 

    def get_inactive_controller(self):
        """ This method returns the inactive controller as a string, e.g. controller-1
        """

        hostpersonality_list = RestUtil.get_controller_personality(self)

        logging.info("Checking for inactive controller")
        # Check which controller is active
        for item in hostpersonality_list: 
            for hostname in item:
                if item[hostname] == "Controller-Standby":
                    logging.info("Inactive controller is: %s" % hostname)
                    return hostname

        # If we didn't return yet, that is an error
        logging.error("No inactive controller found")
        return 1 

    def get_host_state(self):
        """ This method returns a list of dicts showing the administrative, operational
            and availability state of each host. 

            [{u"controller-0": [u"unlocked", u"enabled", u"available"]}, ... 
            ] 

            This is the equivalent of doing a system host-list.
        """

        logging.info("Return host administrative, operational and availability state")

        hoststate_list = []
       
        # Get ihost data 
        data = x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")

        # Parse ihost data for controller hostname and availability 
        for d, l in data.items():
            for item in l:
                host_dict = {}
                hostattr_list = []
                hostname = item[u"hostname"]
                hostattr_list.append(item[u"administrative"])
                hostattr_list.append(item[u"operational"])
                hostattr_list.append(item[u"availability"])
                host_dict[hostname] = hostattr_list 
                  
                hoststate_list.append(host_dict)

        pprint.pprint(hoststate_list)
        return hoststate_list

    def check_all_hosts_unlocked_enabled_available(self):
        """ This method checks that all hosts are unlocked, enabled
            and available. 
        """ 

        hoststate_list = RestUtil.get_host_state(self)
        desiredstate_list = [u"unlocked", u"enabled", u"available"]

        logging.info("Check that all hosts are unlocked-enabled-available")
        for item in hoststate_list:
            for hostname in item:
                if set(item[hostname]) != set(desiredstate_list):
                    logging.error("TEST FAILED: %s is not unlocked-enabled-available" % hostname)
                    return False

        # If we get here, all nodes are in the correct state 
        logging.info("TEST PASSED: All hosts are in desired state")
        return True

    def check_all_hosts_available(self):
        """ This method checks that all hosts are available.
        """

        logging.info("Check that all hosts are available")

        hostavailability_list = RestUtil.get_host_availability_state(self)

        # Check that all hosts are available
        for item in hostavailability_list:
            for hostname in item:
                if item[hostname] != u"available":
                    logging.error("TEST FAILED: Not all hosts are available.")
                    return False
                else:
                    logging.info("TEST PASSED: All hosts are available.")
                    return True 

    def get_nova_services(self):
        """ This method returns details about nova services in a list containing 
            dicts format.  e.g.

            [{u"binary": u"nova-cert", u"host": "controller-1", ....
             {u"binary": u"nova-consoleauth", u"host": "controller-1", ...
             ...
            ] 
        """

        logging.info("Return a list of nova services")

        version = NOVA_VERSION + "/" + x.tenant_token
        data = x.get_request(port=NOVA_PORT, version=version, field="os-services")
        pprint.pprint(data[u"services"])

        return data[u"services"]

    def check_nova_services_state(self):
        """ This method checks the state of nova services to ensure they are correct.
            We are expecting that all services are enabled and up, except those
            belong to the inactive controller.  An exception to this rule is when
            we have a small footprint system.  In which case, the nova-compute service
            will be up on both active and inactive controllers.
        """

        logging.info("Check that the nova services are in the correct state.") 
        inactive_controller = RestUtil.get_inactive_controller(self) 

        return

    def check_smallfootprint(self):
        """ Return True if the system we are testing is configured for small
            footprint.  Otherwise, return False.
        """
 
        logging.info("Checking if system is configured for small footprint")
        
        data = x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")

        # Parse ihost data for subfunctions field 
        for d, l in data.items():
            for item in l:
                if item[u"subfunctions"] == u"controller,compute":
                    logging.info("System is configured for small footprint")
                    return True

        logging.info("System is not configured for small footprint")
        return False

    def check_storagenodes(self):
        """ Return True if the system we are testing has storage nodes.  Otherwise, 
            return False.
        """

        logging.info("Checking if system has storage nodes")

        data = x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")

        # Parse ihost data for personality 
        for d, l in data.items():
            for item in l:
                if item[u"personality"] == u"storage":
                    return True

        logging.info("System does not have storage nodes")
        return False

    def disable_services(self, hostname):
        """ This disables all services associated with a particular host.  Not sure
            how useful this is.  The services will be brought back up by the 
            system automatically.
        """

        disableservices_list = []

        # Determine what services need to disabled
        data = RestUtil.get_nova_services(self) 
        for item in data:
            if item[u"host"] == hostname:
                disableservices_list.append(item[u"binary"])

        logging.info("Services to be disabled for %s" % hostname)
        pprint.pprint(disableservices_list)

        # Construct payload
        for item in disableservices_list:
            payload_dict = {}
            payload_dict[u"host"] = hostname
            payload_dict[u"binary"] = item
            print(payload_dict)

        # Disable services 
        version = NOVA_VERSION + "/" + x.tenant_token
        x.put_request(port=NOVA_PORT, version=version, field="os-services/disable", payload=payload_dict)

        data = RestUtil.get_nova_services(self) 
                
    def unlock_host(self, hostname):
        """ This performs a host unlock of a controller, compute or storage node.  This is
            equivalent of a system host-unlock <node>.

            Returns True if unlock was successful.  Returns False if the node could not be
            unlocked.
        """

    def lock_host(self, hostname):
        """ This performs a host unlock of a controller, compute or storage node.  This is
            equivalent of a system host-unlock <node>.

            Returns True if unlock was successful.  Returns False if the node could not be
            unlocked.
        """
   
        # Construct payload 
        payload_dict = {}
        payload_dict[u"path"] = u"/administrative" 
        payload_dict[u"value"] = u"locked"
        payload_dict[u"op"] = u"replace"

        field = "ihosts/" + hostname
        x.put_request(port=SYSINV_PORT, version=SYSINV_VERSION, field=field, payload=payload_dict)

        RestUtil.get_host_state(self)        

if __name__ == "__main__":
    # Self test for class

    logging.basicConfig(level=logging.INFO)
    #pp = pprint.PrettyPrinter(indent=4)

    # Init object and get token 
    logging.info("Init and display REST API object")
    x = RestUtil(ip="128.224.150.189")
    #x = RestUtil(ip="128.224.150.141")
    print(x)

    active_controller = RestUtil.get_active_controller(x)
    inactive_controller = RestUtil.get_inactive_controller(x)
    nodesunlocked_status = RestUtil.check_all_hosts_unlocked_enabled_available(x)
    smallfootprint_status = RestUtil.check_smallfootprint(x)
    storage_status = RestUtil.check_storagenodes(x)
    RestUtil.get_nova_services(x)
    RestUtil.disable_services(x, u"compute-1")
    #RestUtil.lock_host(x, u"compute-1")


 
