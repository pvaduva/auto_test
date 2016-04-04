from pytest import fixture, mark, skip, raises


from utils import cli, exceptions
from utils import table_parser
from utils.tis_log import LOG
from keywords import nova_helper,cinder_helper, glance_helper,vm_helper, host_helper, system_helper
from setup_consts import P1, P2, P3

_skip = False


@mark.skipif(True, reason="just because")
@mark.parametrize(('volume_name','delete_name','fail_ok','exp_output'), [
    ('test_volume1','test_volume1',True,[0,'']),
    ('test_volume1','wrong_volume',True,[-1,'']),
    ('test_volume1','wrong_volume',True,[1,])
])
def test_volume(volume_name, delete_name,fail_ok, exp_output):
    # create a volume
    new_volume2= cinder_helper.create_volume('test_volume2', size=2)
    new_volume= cinder_helper.create_volume(volume_name, size=2)
    assert new_volume[0]==0
    new_volume_id = new_volume[1]

    # verified its available after created
    vol_status = cinder_helper.get_volume_states(new_volume_id, "status")['status']
    assert vol_status == "available"

    bol = cinder_helper.delete_volume(delete_name)
    print ("output is:",bol)
    #nova_helper.delete_volume(new_volume_id)

    # verfied that a error is raised trying to show volume after it's deleted
    #with raises(Exception) as excinfo:
    #    vol_status = nova_helper.get_volume_states(new_volume_id,"status")['status']
    #assert excinfo.value.message == "CLI command is rejected."

@mark.skipif(True, reason="just because")
def test_vm():
    output = nova_helper.delete_vm('b6b3dd41-09c6-4038-862d-47aea1070685')
    print("output is:",output)

def test_vm():
    output = glance_helper.delete_image('344d9866-c28c-4b30-9d86-9b1ac5b96fb9')
    print("output is:",output)
