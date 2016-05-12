from pytest import fixture, mark, skip

from utils import cli
from utils import table_parser
from consts.auth import Tenant
from utils.tis_log import LOG
from keywords import nova_helper, vm_helper, host_helper, system_helper,cinder_helper
from setup_consts import P1, P2, P3

#set flavor
#verfiy that flavour is created and the extra spec is set
#delete the specs and verfiy its deleted



@fixture(scope='module')
def create_volume_type(request):

    volume_type_id = cinder_helper.create_volume_type("test_volume_type")[0]

    volume_type = {'id': volume_type_id
                   }

    def delete_volume_type():
        cinder_helper.delete_volume_type(volume_type_id)
    request.addfinalizer(delete_volume_type)

    return volume_type


@fixture(scope='module')
def create_qos_specs(request):

    qos_specs_id = cinder_helper.create_qos_specs("test_qos_specs", a=123)[0]

    qos_specs = {'id': qos_specs_id
                 }

    # associate qos specs to volume_type

    def delete_qos_specs():
        cinder_helper.delete_qos_specs(qos_specs_id)
    request.addfinalizer(delete_qos_specs)

    return qos_specs


@fixture(scope='module')
def create_qos_association(request,create_volume_type, create_qos_specs):

    volume_type_id = create_volume_type['id']
    qos_specs_id = create_qos_specs['id']

    cinder_helper.associate_qos_to_volume_type(qos_specs_id, volume_type_id)

    qos_association = {'qos_id': qos_specs_id,
                       'volume_type_id': volume_type_id
                       }

    def delete_qos_association():
        cinder_helper.disassociate_qos_to_volume_type(qos_specs_id, volume_type_id)
    request.addfinalizer(delete_qos_association)

    return qos_association


def test_verify_volume_type(create_volume_type):
    # use cinder type list find the newly create volume id exist
    table_ = cinder_helper.get_type_list()
    volume_type_id = create_volume_type['id']

    match_vol_type_id = table_parser.get_values(table_, 'ID', ID=volume_type_id)[0]

    assert volume_type_id == match_vol_type_id,"expected volume type ID to be {}. Actual ID is {} instead.".format(
        volume_type_id, match_vol_type_id)


def test_verify_qos_specs(create_qos_specs):

    table_ = cinder_helper.get_qos_list()
    qos_spec_id = create_qos_specs['id']

    match_qos_spec_id = table_parser.get_values(table_, 'ID', ID=qos_spec_id)[0]

    assert qos_spec_id == match_qos_spec_id, "expected QOS specs ID to be {}. Actual ID is {} instead.".format(
        qos_spec_id, match_qos_spec_id)


def test_associate_qos_spec_to_volume_type(create_qos_association):

    volume_type_id = create_qos_association['volume_type_id']
    qos_spec_id = create_qos_association['qos_id']

    print(volume_type_id, qos_spec_id)

    table_ = cinder_helper.get_qos_association(qos_spec_id)

    match_volume_type_id = table_parser.get_values(table_, 'ID', ID=volume_type_id)[0]

    assert volume_type_id == match_volume_type_id, "After QOS Association with volume type, expect associated volume " \
                                                   "ID to be {}. Actual volume ID is {} instead.".\
        format(volume_type_id, match_volume_type_id)


