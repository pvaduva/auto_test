from utils.tis_log import LOG
from keywords import system_helper


def test_snmp_community_string():
    """
    SNMP community string create and delete.

    Test steps:
        1.  Create SNMP community string
        2.  Verify its created successfully
        3.  Delete the snmp community string

    """

    # create a community sring
    comm_string = 'snmp_test_comm_string'

    LOG.tc_step("Creating snmp community string {}".format(comm_string))
    system_helper.create_snmp_comm(comm_string=comm_string)

    LOG.tc_step("Check if the snmp community string {} is created".format(comm_string))
    comm_strings = system_helper.get_snmp_comms()
    assert comm_string in comm_strings, "Failed to create the snmp community string"

    # delete the community-string
    LOG.tc_step("Deleting snmp community string {}".format(comm_string))
    system_helper.delete_snmp_comm(comm_string, check_first=False)
