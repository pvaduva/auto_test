from pytest import mark
from utils.tis_log import LOG
from utils import cli, exceptions
from keywords import system_helper, host_helper


@mark.domain_sanity
def test_delete_unlocked_node():
    """
    Attempts to delete each unlocked node.
    Fails if one unlocked node does get deleted.

    Test Steps:
        - Creates a list of every unlocked host
        - Iterate through each host and attempt to delete it
        - Verify that each host rejected the delete request

    """

    hosts = host_helper.get_hosts(administrative='unlocked')

    deleted_nodes = []

    for node in hosts:
        LOG.tc_step("attempting to delete {}".format(node))
        LOG.info("{} state: {}".format(node, host_helper.get_hostshow_value(node, field='administrative')))
        res, out = cli.system('host-delete', node, fail_ok=True, rtn_list=True)

        LOG.tc_step("Delete request - result: {}\tout: {}".format(res, out))

        assert 1 == res, "FAIL: The delete request for {} was not rejected".format(node)

        LOG.tc_step("Confirming that the node was not deleted")
        res, out = cli.system('host-show', node, fail_ok=True, rtn_list=True)

        if 'host not found' in out or res != 0:
            # the node was deleted even though it said it wasn't
            LOG.tc_step("{} was deleted.".format(node))
            deleted_nodes.append(node)

    assert not deleted_nodes, "Fail: Delete request for the following node(s) " \
                              "{} was accepted.".format(deleted_nodes)


def test_delete_nonexisting_host_negative():
    """
    TC1933
    Verfiy that cli rejects attempts to delete a non-existent node

    Test Steps:
        - Create a name that no node has
        - Attempt to delete a node with that name
        - Verify that the command is rejected

    """
    nodes = host_helper.get_hosts()
    name = nodes[len(nodes) - 1] + "a"
    while True:
        if name not in nodes:
            break
        name += "a"
    LOG.tc_step("Attempt to delete {}".format(name))
    code, out = cli.system('host-delete', name, fail_ok=True, rtn_list=True)
    assert 1 == code, "FAIL: Attempting to delete non-existent {} was not rejected".format(name)
