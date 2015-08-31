#!/usr/bin/env python

"""
This file contains methods for common system operations such as getting
controller personality, checking if we have storage nodes, etc. 

"""

from restapi import RestAPI 
from constants import *
import sys
import logging
import pprint

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
        """ This method returns a list of dicts showing the administrative, operational,
            availability state and task of each host. 

            [{u"controller-0": [u"unlocked", u"disabled", u"offline", u"Booting"]}, ... 
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
                hostattr_list.append(item[u"task"])
                host_dict[hostname] = hostattr_list 
                  
                hoststate_list.append(host_dict)

        pprint.pprint(hoststate_list)
        return hoststate_list

    def check_all_hosts_unlocked_enabled_available(self):
        """ This method checks that all hosts are unlocked, enabled
            and available. 
        """ 

        flag = True
        hoststate_list = RestUtil.get_host_state(self)
        desiredstate_list = [u"unlocked", u"enabled", u"available"]

        logging.info("Check that all hosts are unlocked-enabled-available")
        for item in hoststate_list:
            for hostname in item:
                if set(item[hostname]) != set(desiredstate_list):
                    logging.error("ERROR: %s is not unlocked-enabled-available" % hostname)
                    flag = False
                    
        # If we get here, all nodes are in the correct state 
        if flag == True:
            logging.info("All hosts are in desired state")
        else:
            logging.error("Not all hosts are in desired state")

        return flag 

    def check_all_hosts_available(self):
        """ This method checks that all hosts are available.
        """

        logging.info("Check that all hosts are available")

        hostavailability_list = RestUtil.get_host_availability_state(self)

        # Check that all hosts are available
        for item in hostavailability_list:
            for hostname in item:
                if item[hostname] != u"available":
                    logging.error("Not all hosts are available.")
                    return False
                else:
                    logging.info("All hosts are available.")
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
                    logging.info("System does have storage nodes")
                    return True

        logging.info("System does not have storage nodes")
        return False

    def check_all_hosts_available(self):
        """ This method checks that all hosts are available.
        """

        logging.info("Check that all hosts are available")

        hostavailability_list = RestUtil.get_host_availability_state(self)

        # Check that all hosts are available
        for item in hostavailability_list:
            for hostname in item:
                if item[hostname] != u"available":
                    logging.error("Not all hosts are available.")
                    return False
                else:
                    logging.info("All hosts are available.")
                    return True 

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
                
    def host_action(self, hostname, action):
        """ This performs an arbitrary action on a controller, compute or storage node. 
            It supports: unlock, lock, swact, apply-profile, reboot, reset, power-on,
            power-off and reinstall.  This is based on the restapi sysinv wadl doc.

            Arguments: 
               * hostname, e.g. controller-1
               * action, e.g. unlock

            Note, if you attempt to lock a node that is already locked, TiS will return a
            400 Bad Request error.  It is best to check the state of the system before
            initiating operations.  Same goes for other operations like unlock.

            Commands tested:
                * unlock - works but we get a 504 gateway error anyways
                * lock - works 
                * swact - works
                * reboot - works

            Possible controller commands on unlocked host:
                * lock, (force lock), swact

            Possible controller commands on locked host:
                * unlock, reboot, reinstall, (delete)

            Possible compute commands on unlocked host:
                * lock, (force lock)

            Possible compute commands on locked host:
                * unlock, power-on, power-off, reboot, reset, reinstall, delete 
        """

        uuid = ""  
        actions_list = [u"unlock", u"lock", u"swact", u"apply-profile", u"reboot", 
                        u"reset", u"power-on", u"power-off", u"reinstall"]

        # Check if the action we are requesting is valid
        if action not in actions_list:
            logging.error("ERROR: You've requested an invalid action.")
            logging.info("Valid actions are: %s" % actions_list)
            return 1

        # Action is valid so construct payload for patch request command
        payload = [{"path":"/action", "value": action, "op":"replace"}]

        # Get ihost raw data 
        data = x.get_request(port=SYSINV_PORT, version=SYSINV_VERSION, field="ihosts")

        # Parse ihost data for host uuid 
        for d, l in data.items():
            for item in l:
                if item[u"hostname"] == hostname:
                    uuid = item[u"uuid"]
                    break

        # If we didn't get a uuid, inform the user and return
        if not uuid:
            logging.error("Hostname %s was not found in the system" % hostname)
            return 1

        # Perform the patch request
        logging.info("Performing host action %s on %s" % (action, hostname))
        field = "ihosts/" + uuid
        retval = x.patch_request(port=SYSINV_PORT, version=SYSINV_VERSION, field=field, payload=payload)
        print(retval)

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
    #nodesunlocked_status = RestUtil.check_all_hosts_unlocked_enabled_available(x)
    smallfootprint_status = RestUtil.check_smallfootprint(x)
    storage_status = RestUtil.check_storagenodes(x)
    RestUtil.host_action(x, u"compute-1", u"unlock")


 
