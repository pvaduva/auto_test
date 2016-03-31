from pytest import fixture, mark, skip, raises

from utils import cli, exceptions
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3

_skip = False


@mark.parametrize(('volume_name','delete_name'), [
    ('test_volume','test_volume'),
    ('test_volume','wrong_volume')
])
def test_volume(volume_name,delete_name):
    # create a volume
    new_volume= nova_helper.create_volume(volume_name, size=6)
    assert new_volume[0]==0
    new_volume_id = new_volume[1]

    # verified its available after created
    vol_status = nova_helper.get_volume_states(new_volume_id,"status")['status']
    assert vol_status == "available"

    bol = nova_helper.delete_volume(delete_name)
    print ("output is:",bol)
    #nova_helper.delete_volume(new_volume_id)

    # verfied that a error is raised trying to show volume after it's deleted
    #with raises(Exception) as excinfo:
    #    vol_status = nova_helper.get_volume_states(new_volume_id,"status")['status']
    #assert excinfo.value.message == "CLI command is rejected."


