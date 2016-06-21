from pytest import fixture

from keywords import nova_helper


@fixture(scope='session')
def server_groups():

    def create_server_groups(auth_info=None):
        srv_grps_tenant = []
        for policy in ['affinity', 'anti-affinity']:
            srv_grp_id = nova_helper.create_server_group(name='srv_group_' + policy, policy=policy, auth_info=auth_info,
                                                         rtn_exist=True)[1]
            srv_grps_tenant.append(srv_grp_id)
        return srv_grps_tenant

    return create_server_groups
