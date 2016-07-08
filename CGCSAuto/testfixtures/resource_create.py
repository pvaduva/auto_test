from pytest import fixture

from utils.tis_log import LOG
from keywords import nova_helper


@fixture(scope='session')
def server_groups():

    def create_server_groups(best_effort=True, auth_info=None):
        srv_grps_tenant = []
        extra_str = 'besteffort' if best_effort else 'strict'

        LOG.fixture_step('(session) Creating affinity and anti-affinity server groups with best_effort set to {}'.
                         format(best_effort))
        for policy in ['affinity', 'anti-affinity']:
            name = 'srv_group_{}_{}'.format(policy, extra_str)
            srv_grp_id = nova_helper.create_server_group(name=name, policy=policy, best_effort=best_effort,
                                                         auth_info=auth_info, rtn_exist=True)[1]
            srv_grps_tenant.append(srv_grp_id)
        return srv_grps_tenant

    return create_server_groups
