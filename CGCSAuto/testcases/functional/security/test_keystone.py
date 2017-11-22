from pytest import mark
from keywords import keystone_helper
from utils.tis_log import LOG


@mark.usefixtures('check_alarms')
def test_admin_password():
    """
    Test the deletion of admin user

    Test Steps:
        - Try deleting the default admin user, it should fail

    """

    LOG.info("Deleteing default admin user...expecting it to fail")
    code, msg = keystone_helper.delete_users('admin', fail_ok=True)
    assert code == 1, "Expected default user admin deletion to fail"
