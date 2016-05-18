from pytest import fixture, mark, skip
from time import sleep

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

    volume_type_id = cinder_helper.create_volume_type("test_volume_type")[1]

    volume_type = {'id': volume_type_id
                   }

    def delete_volume_type():
        cinder_helper.delete_volume_type(volume_type_id)
    request.addfinalizer(delete_volume_type)

    return volume_type


@fixture(scope='module')
def create_qos_specs(request):

    qos_specs_id = cinder_helper.create_qos_specs("test_qos_specs", a=123)[1]

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


@fixture(scope='module')
def create_volume_with_type(request, create_qos_association):

    volume_type_id = create_qos_association['volume_type_id']
    volume_id = cinder_helper.create_volume("test_volume", vol_type=volume_type_id)

    table_ = table_parser.table(cli.cinder('type-list', auth_info=Tenant.ADMIN))
    volume_type_name = table_parser.get_values(table_, 'Name', ID=volume_type_id)
    volume = {'id': volume_id,
              'volume_type_id': volume_type_id,
              'volume_type_name': volume_type_name
              }

    #def delete_volume():
    #    cinder_helper.delete_volumes(volume_id)
    #request.addfinalizer(delete_volume)

    return volume


def test_verify_volume_type(create_volume_type):
    # use cinder type list find the newly create volume id exist
    vol_type_id_list = cinder_helper.get_type_list()

    volume_type_id = create_volume_type['id']

    assert volume_type_id in vol_type_id_list, "expected volume type ID {} to be created. Actual ID is not in " \
                                               "cinder type-list: {}.".format(volume_type_id, vol_type_id_list)


def test_verify_qos_specs(create_qos_specs):

    qos_spec_id_list = cinder_helper.get_qos_list()
    qos_spec_id = create_qos_specs['id']

    assert qos_spec_id in qos_spec_id_list, "expected QOS specs ID to be {}. Actual ID is not in " \
                                            "cinder qos-list: {}.".format(qos_spec_id, qos_spec_id_list)


def test_associate_qos_spec_to_volume_type(create_qos_association):

    volume_type_id = create_qos_association['volume_type_id']
    qos_spec_id = create_qos_association['qos_id']

    table_ = cinder_helper.get_qos_association(qos_spec_id)

    match_volume_type_id = table_parser.get_values(table_, 'ID', ID=volume_type_id)[0]

    assert volume_type_id == match_volume_type_id, "After QOS Association with volume type, expect associated volume " \
                                                   "ID to be {}. Actual volume ID is {} instead.".\
        format(volume_type_id, match_volume_type_id)


def test_create_volume_with_volume_type(create_volume_with_type):
    volume_id = create_volume_with_type['id']
    volume_type_id = create_volume_with_type['volume_type_id']
    volume_type_name = create_volume_with_type['volume_type_name']

    table_ = table_parser.table(cli.cinder('list', auth_info=Tenant.ADMIN))

    match_vol_type_name = table_parser.get_values(table_, 'Volume Type', ID=volume_id)

    assert volume_type_name == match_vol_type_name, "After create a volume with ID {} use volume type name: {}. " \
                                                    "Actual create volume contain volume type name: {}" \
                                                    "".format(volume_id, volume_type_name, match_vol_type_name)