from pytest import mark
from keywords import system_helper, keystone_helper
from consts.cgcs import ExtLdap
from utils.tis_log import LOG
from pytest import mark, fixture, skip

srvice_param_restore_dic = []


@fixture(scope='module', autouse=True)
def router_info(request):
    global srvice_param_restore_dic

    def teardown():
        for dict in srvice_param_restore_dic:
            if dict['action'] == 'delete':
                code, msg = system_helper.delete_service_parameter(uuid=dict['uuid'])
                assert code == 0, "Couldn't delete service param {}".format(dict['uuid'])
            elif dict['action'] == 'modify':
                code, msg = system_helper.modify_service_parameter(service=dict['service'],section=dict['section'],
                                                                   name=dict['name'],value=dict['val'])
                assert code == 0, "Couldn't modify service param {}".format(dict['uuid'])

        code, msg = system_helper.apply_service_parameters(service='identity')
        assert code == 0, "Expected service params apply to pass"

    request.addfinalizer(teardown)

    return 0


@mark.usefixtures('check_alarms')
def test_ext_ldap():
    """
    Test the external ldap connectivity

    Test Steps:
        - Set the service params for the external ldap
        - do a openstack user list to verify the user that is in external ldap
        - Restore the system

    """
    global srvice_param_restore_dic
    service = 'identity'
    LOG.info("Add Ext LDAP service params")
    code, msg = system_helper.create_service_parameter(service=service, section='ldap', name='url',
                                                       value=ExtLdap.LDAP_SERVER)
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='ldap', name='url')[0]
    dict = {'uuid':uuid, 'action':'delete', 'val':None}
    srvice_param_restore_dic.append(dict)

    suffix = "\"" + ExtLdap.LDAP_DC + "\""
    code, msg = system_helper.create_service_parameter(service=service, section='ldap', name='suffix', value=suffix)
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='ldap',
                                                      name='suffix')[0]
    dict = {'uuid': uuid, 'action': 'delete', 'val': None}
    srvice_param_restore_dic.append(dict)
    code, msg = system_helper.create_service_parameter(service=service,section='identity', name='driver',
                                                       value=ExtLdap.LDAP_DRIVER)
    dict = {'uuid': uuid, 'action': 'modify', 'service':'identity', 'section':'identity', 'name':'driver', 'val': 'sql'}
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='identity',
                                                      name='driver')[0]
    srvice_param_restore_dic.append(dict)
    user = "\"" + ExtLdap.LDAP_USER + "\""
    code, msg = system_helper.create_service_parameter(service=service,section='ldap', name='user', value=user,
                                                       verify=False)
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='ldap',
                                                      name='user')[0]
    dict = {'uuid': uuid, 'action': 'delete', 'val': None}
    srvice_param_restore_dic.append(dict)

    code, msg = system_helper.apply_service_parameters(service=service)
    assert code == 0, "Expected service params apply to pass"

    LOG.info("Verify ext ldap connectivity via openstack user list")
    user_id = keystone_helper.get_user_ids(user_name='ldap1')

    assert user_id is not None, "Expected ldap1 user user to be there"
