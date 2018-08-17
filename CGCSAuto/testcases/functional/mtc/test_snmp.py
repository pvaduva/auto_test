from utils.tis_log import LOG
from keywords import system_helper


def test_snmp_community_string():
    """
    SNMP community string create and delete.

    Test steps:
        1.  Create SNMP community string
        2.  Verift its created successfully
        3.  Delete the snmp community string

    """

    # create a comminity sring
    comm_string = 'snmp_test_comm_string'

    LOG.tc_step("Creating snmp community string {}".format(comm_string))
    out = system_helper.create_snmp_comm_string(comm_string=comm_string)

    LOG.tc_step("Check if the snmp community string {} is created".format(comm_string))
    comm_strings = system_helper.get_snmp_comm_string()

    if comm_string not in comm_strings:
        assert 0 == 1, "Failed to create the snmp community string"

    # delete the community-string
    LOG.tc_step("Deleting snmp community string {}".format(comm_string))
    code = system_helper.delete_snmp_comm_string(comm_string)
    assert code == 0, "Failed to delete the snmp community string"
