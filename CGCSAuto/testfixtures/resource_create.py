from pytest import fixture

from utils.tis_log import LOG
from consts.cgcs import GuestImages
from keywords import nova_helper, glance_helper, keystone_helper


# Session fixture to add affinitiy and anti-affinity server group
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


# Session fixture to add cgcsauto aggregate with cgcsauto availability zone
@fixture(scope='session')
def add_cgcsauto_zone(request):
    LOG.fixture_step("(session) Add cgcsauto aggregate and cgcsauto availability zone")
    nova_helper.create_aggregate(name='cgcsauto', avail_zone='cgcsauto', check_first=True)

    def remove_aggregate():
        LOG.fixture_step("(session) Delete cgcsauto aggregate")
        nova_helper.delete_aggregate('cgcsauto')
    request.addfinalizer(remove_aggregate)

    # return name of aggregate/availability zone
    return 'cgcsauto'


# Fixtures to add admin role to primary tenant
@fixture(scope='module')
def add_admin_role_module(request):
    __add_admin_role(scope='module', request=request)


@fixture(scope='class')
def add_admin_role_class(request):
    __add_admin_role(scope='class', request=request)


@fixture(scope='function')
def add_admin_role_func(request):
    __add_admin_role(scope='function', request=request)


def __add_admin_role(scope, request):
    LOG.fixture_step("({}) Add admin role to user under primary tenant".format(scope))
    code = keystone_helper.add_or_remove_role(add_=True, role='admin')[0]

    def remove_admin():
        if code != -1:
            LOG.fixture_step("({}) Remove admin role from user under primary tenant".format(scope))
            keystone_helper.add_or_remove_role(add_=False, role='admin')
    request.addfinalizer(remove_admin)


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


@fixture(scope='session', autouse=True)
def tis_centos_image():
    return __create_image('tis-centos-guest', 'session')


@fixture(scope='session', autouse=False)
def cgcs_guest_image():
    return __create_image('cgcs-guest', 'session')


def __create_image(img_os, scope):

    LOG.fixture_step("({}) Get or create a glance image with {} guest OS".format(scope, img_os))
    img_info = GuestImages.IMAGE_FILES[img_os]
    if img_info[0] is not None:
        image_path = glance_helper._scp_guest_image(img_os=img_os)
    else:
        image_path = "{}/{}".format(GuestImages.IMAGE_DIR, img_info[2])

    img_id = glance_helper.get_image_id_from_name(img_os, strict=True)
    if not img_id:
        disk_format = 'raw' if img_os in ['cgcs-guest', 'tis-centos-guest', 'vxworks'] else 'qcow2'
        img_id = glance_helper.create_image(name=img_os, source_image_file=image_path, disk_format=disk_format,
                                            container_format='bare')[1]

    return img_id
