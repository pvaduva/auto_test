from keywords import system_helper, keystone_helper
from consts.cgcs import ExtLdap
from utils.tis_log import LOG
from pytest import mark, fixture

service_param_restore_dic = []


@fixture(scope='module', autouse=True)
def router_info(request):
    global service_param_restore_dic

    def teardown():
        for dict_ in service_param_restore_dic:
            if dict_['action'] == 'delete':
                code, msg = system_helper.delete_service_parameter(uuid=dict_['uuid'])
                assert code == 0, "Couldn't delete service param {}".format(dict_['uuid'])
                system_helper.apply_service_parameters(service='identity')
            elif dict_['action'] == 'modify':
                system_helper.modify_service_parameter(service=dict_['service'], section=dict_['section'],
                                                       name=dict_['name'], value=dict_['val'], apply=True)
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
    global service_param_restore_dic
    service = 'identity'
    LOG.info("Add Ext LDAP service params")
    system_helper.create_service_parameter(service=service, section='ldap', name='url', value=ExtLdap.LDAP_SERVER)
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='ldap', name='url')[0]
    dict_ = {'uuid': uuid, 'action': 'delete', 'val': None}
    service_param_restore_dic.append(dict_)

    suffix = "\"" + ExtLdap.LDAP_DC + "\""
    system_helper.create_service_parameter(service=service, section='ldap', name='suffix', value=suffix)
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='ldap',
                                                      name='suffix')[0]
    dict_ = {'uuid': uuid, 'action': 'delete', 'val': None}
    service_param_restore_dic.append(dict_)
    system_helper.create_service_parameter(service=service, section='identity', name='driver',
                                           value=ExtLdap.LDAP_DRIVER)
    dict_ = {'uuid': uuid, 'action': 'modify', 'service': 'identity', 'section': 'identity',
             'name': 'driver', 'val': 'sql'}

    service_param_restore_dic.append(dict_)
    user = "\"" + ExtLdap.LDAP_USER + "\""
    system_helper.create_service_parameter(service=service, section='ldap', name='user', value=user, verify=False)
    uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section='ldap',
                                                      name='user')[0]
    dict_ = {'uuid': uuid, 'action': 'delete', 'val': None}
    service_param_restore_dic.append(dict_)

    code, msg = system_helper.apply_service_parameters(service=service)
    assert code == 0, "Expected service params apply to pass"

    LOG.info("Verify ext ldap connectivity via openstack user list")
    user_id = keystone_helper.get_user_ids(user_name='ldap1')

    assert user_id is not None, "Expected ldap1 user user to be there"
