from pytest import fixture

from utils.tis_log import LOG
from keywords import nova_helper, glance_helper


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


@fixture(scope='session')
def ubuntu14_image():
    return __create_image('ubuntu_14', 'session')


@fixture(scope='session')
def ubuntu12_image():
    return __create_image('ubuntu_12', 'session')


@fixture(scope='session')
def centos7_image():
    return __create_image('centos_7', 'session')


@fixture(scope='session')
def centos6_image():
    return __create_image('centos_6', 'session')


@fixture(scope='session')
def opensuse11_image():
    return __create_image('opensuse_11', 'session')


@fixture(scope='session')
def opensuse12_image():
    return __create_image('opensuse_12', 'session')


@fixture(scope='session')
def opensuse13_image():
    return __create_image('opensuse_13', 'session')


@fixture(scope='session')
def rhel6_image():
    return __create_image('rhel_6', 'session')


@fixture(scope='session')
def rhel7_image():
    return __create_image('rhel_7', 'session')


def __create_image(img_os, scope):

    LOG.fixture_step("({}) Get or create a glance image with {} guest OS".format(scope, img_os))
    image_path = glance_helper._scp_guest_image(img_os=img_os)

    img_id = glance_helper.get_image_id_from_name(img_os, strict=True)
    if not img_id:
        img_id = glance_helper.create_image(name=img_os, source_image_file=image_path, disk_format='qcow2',
                                            container_format='bare')[1]

    return img_id
