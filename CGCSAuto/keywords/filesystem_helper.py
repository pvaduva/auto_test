import ast
import re

from utils import cli, table_parser
from utils.clients.ssh import ControllerClient


def get_controllerfs(filesystem, rtn_value="size"):
    """
    Returns the value of a particular filesystem.

    Arguments:
    - rtn_value(str) - what value to get, e.g. size
    - filesystem(str) - e.g. scratch, database, etc.
    
    Returns:
    - Desired value (int if 'size' is desired, else return string)
    """

    cmd = "controllerfs-show {}".format(filesystem)
    table_ = table_parser.table(cli.system(cmd))
    out = table_parser.get_value_two_col_table(table_, rtn_value)

    if rtn_value == "size":
        return int(ast.literal_eval(out))
    else:
        return out


def check_controllerfs(**kwargs):
    """
    This validates that the underlying controller filesystem aligns with the
    expected values.

    Arguments:
    - kwargs - dict of name:value pair(s)
    """

    con_ssh = ControllerClient.get_active_controller()

    for fs in kwargs:
        if fs == "database":
            fs_name = "pgsql-lv"
            expected_size = int(kwargs[fs]) * 2
        elif fs == "glance":
            fs_name = "cgcs-lv"
            expected_size = int(kwargs[fs])
        else:
            fs_name = fs + "-lv"
            expected_size = int(kwargs[fs])

        cmd = "lvs --units g --noheadings -o lv_size -S lv_name={}".format(fs_name)
        rc, out = con_ssh.exec_sudo_cmd(cmd)

        actual_size = re.match(r'[\d]+', out.lstrip())
        assert actual_size, "Unable to determine actual filesystem size"
        assert int(actual_size.group(0)) == expected_size, "{} should be {} but was {}".format(fs, expected_size, actual_size)


def modify_controllerfs(fail_ok=False, **kwargs):
    """
    Modifies the specified controller filesystem, e.g. scratch, database, etc.

    Arguments:
    - kwargs - dict of name:value pair(s)
    - fail_ok(bool) - True if failure is expected.  False if not.
    """

    attr_values_ = ['{}="{}"'.format(attr, value) for attr, value in kwargs.items()]
    args_ = ' '.join(attr_values_)

    rc, out = cli.system("controllerfs-modify", args_, rtn_code=True, fail_ok=fail_ok)

    if not fail_ok:
        assert rc == 0, "Failed to update filesystem"
    else:
        assert rc != 0, "Filesystem update was expected to fail but instead succeeded"


