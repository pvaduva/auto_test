from pytest import fixture, skip, mark

from utils import cli
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient
from consts.proj_vars import ProjVar
from consts.auth import Tenant, HostLinuxUser
from consts.filepaths import TestServerPath
from consts.stx import Container
from keywords import dc_helper, system_helper, common, container_helper

EXTFILE = "extfile.cnf"


@fixture(scope='module')
def copy_extfile():
    con_ssh = ControllerClient.get_active_controller(name='RegionOne')
    home_dir = HostLinuxUser.get_home()
    extfile_source_path = TestServerPath.TEST_FILES + EXTFILE
    LOG.info("Copy {} from test server:{} to system controller:{}".format(EXTFILE, extfile_source_path, home_dir))

    extfile_path = common.scp_from_test_server_to_active_controller(extfile_source_path, home_dir, con_ssh=con_ssh)
    assert extfile_path, "scp_from_test_server_to_active_controller failed"

    if not system_helper.is_aio_simplex():
        dest_host = 'controller-1' if con_ssh.get_hostname() == 'controller-0' else 'controller-0'
        con_ssh.rsync(source=extfile_path, dest_server=dest_host, dest=extfile_path, timeout=60)


@fixture(scope='module')
def subclouds_to_test(request):
    LOG.info("Gather subcloud management info")
    subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')

    def revert():
        LOG.fixture_step("Manage {} if unmanaged".format(subcloud))
        dc_helper.manage_subcloud(subcloud)

    request.addfinalizer(revert)

    managed_subclouds = dc_helper.get_subclouds(mgmt='managed', avail='online')
    if subcloud in managed_subclouds:
        managed_subclouds.remove(subcloud)

    ssh_map = ControllerClient.get_active_controllers_map()
    managed_subclouds = [subcloud for subcloud in managed_subclouds if subcloud in ssh_map]

    return subcloud, managed_subclouds


@fixture()
def ensure_synced(subclouds_to_test, copy_extfile, check_central_alarms):
    primary_subcloud, managed_subclouds = subclouds_to_test

    LOG.fixture_step("Ensure {} is managed and certificate is synced with central cloud".format(primary_subcloud))
    sc_auth = Tenant.get('admin_platform', dc_region='RegionOne')
    prev_central_certificate = system_helper.get_certificate_signature(auth_info=sc_auth)

    subcloud_auth = Tenant.get('admin_platform', dc_region=primary_subcloud)
    prev_subcloud_certificate = system_helper.get_certificate_signature(auth_info=subcloud_auth)
    LOG.info("Certificate signature on central region {} and subcloud {}"
             .format(prev_central_certificate, prev_subcloud_certificate))
    assert prev_central_certificate == prev_subcloud_certificate, \
        "Certificate signature on central region {} and subcloud {} are different."\
        .format(prev_central_certificate, prev_subcloud_certificate)

    LOG.fixture_step("Ensure Central region access to external docker registry success")
    con_ssh = ControllerClient.get_active_controller(name='RegionOne')
    external_docker_registry = "tis-lab-registry.cumulus.wrs.com:9001"
    test_image = "hellokitty"
    tag = "v1.0"
    image_addr = "{}/gwaines/{}".format(external_docker_registry, test_image)
    code, out = container_helper.pull_docker_image(image_addr, tag=tag, con_ssh=con_ssh)
    assert 0 == code, "Central Region failed to access {} by {}".format(primary_subcloud, image_addr, out)

    LOG.fixture_step("Ensure on primary subcloud, access to both registry.central and registry.local success")
    registry_local = Container.LOCAL_DOCKER_REG
    registry_central = Container.CENTRAL_DOCKER_REG
    LOG.info("Verify {} access to registry.local should pass".format(primary_subcloud))
    code, out = verify_access_to_registry(subcloud=primary_subcloud, registry_addr=registry_local)
    assert 0 == code, "{} failed to access {} by {}".format(primary_subcloud, registry_local, out)

    LOG.info("Verify {} access to registry.central should pass".format(primary_subcloud))
    code, out = verify_access_to_registry(subcloud=primary_subcloud, registry_addr=registry_central)
    assert 0 == code, "{} failed to access {} by {}".format(primary_subcloud, registry_central, out)

    return primary_subcloud, managed_subclouds, prev_central_certificate


def test_create_new_certificate(ensure_synced):
    """
    Update certificate on central region and subcloud to check it is propagated to subclouds
    Args:
        ensure_synced: test fixture

    Setups:
        - Ensure primary subcloud is managed and certificate is valid and synced
        - ensure Central region access to external docker registry success
        - check docker login to registry.local and registry.central success

    Test Steps:
        - Un-manage primary subcloud
        - Create new pair of certificates (ssl_ca & docker_registry) on central region
        - install docker_registry certificate on central region
        - Wait for docker_registry certificate to sync over to managed online subclouds
        - Ensure docker_registry certificate is not updated on unmanaged primary subcloud
        - verify on subcloud, docker login registry.central failed and login registry.local success
        - install new ssl_ca certificate on central region
        - Wait for new ssl_ca certificate to sync over to managed online subclouds
        - Ensure new ssl_ca certificate is not updated on unmanaged primary subcloud
        - verify on subcloud, docker login both registry.central and registry.local success
        - Re-manage primary subcloud and ensure all certificates syncs over
        - Verify on subcloud, docker login both registry.central and registry.local success on primary subcloud
        - ensure Central region access to external docker registry success

    Teardown:
        - manage unmanaged subcloud

    """
    primary_subcloud, managed_subclouds, prev_central_signature = ensure_synced
    LOG.info("{} central signature is {}".format(primary_subcloud, prev_central_signature))

    LOG.tc_step("Unmanage {}".format(primary_subcloud))
    dc_helper.unmanage_subcloud(subcloud=primary_subcloud, check_first=True)

    LOG.tc_step("Create new pair of certificates:ssl_ca & docker_registry on central region")
    con_ssh = ControllerClient.get_active_controller(name='RegionOne')
    send_cmds = ['openssl genrsa -out ca-key.pem 2048',
                 'openssl req -x509 -new -nodes -key ca-key.pem -days 1024 -out ca-cert.pem -outform PEM '
                 '-subj "/C=CA/ST=ON/L=Ottawa/O=WindRiver/OU=Titanium/CN=example.com"',
                 'openssl genrsa -out server-key.pem 2048',
                 'openssl req -new -key server-key.pem -out server.csr '
                 '-subj "/C=CA/ST=ON/L=Ottawa/O=WindRiver/OU=Titanium/CN=example.com"',
                 'openssl x509 -req -in server.csr -CA ca-cert.pem -CAkey ca-key.pem '
                 '-CAcreateserial -out server.pem -days 365',
                 'openssl x509 -req -days 365 -in server.csr -CA ca-cert.pem -CAkey '
                 'ca-key.pem -CAcreateserial -out server.pem -extfile extfile.cnf',
                 'cat server-key.pem server.pem > server-with-key.pem'
                 ]
    for cmd in send_cmds:
        LOG.info("send openssl cmd: {}".format(cmd))
        code, out = con_ssh.exec_cmd(cmd)
        assert 0 == code, "openssl cmd error: {}".format(out)

    LOG.tc_step("install docker_registry certificate on central region")
    sc_auth = Tenant.get('admin_platform', dc_region='RegionOne')
    code, out = cli.system("certificate-install -m docker_registry server-with-key.pem",
                           ssh_client=con_ssh, auth_info=sc_auth)
    assert 0 == code, "certificate-install cmd error: {}".format(out)

    LOG.tc_step("Get new central region signature")
    new_central_signature = system_helper.get_certificate_signature(auth_info=sc_auth)

    LOG.tc_step("Wait for new certificate {} to sync over to managed online subclouds".format(new_central_signature))
    for managed_sub in managed_subclouds:
        subcloud_auth = Tenant.get('admin_platform', dc_region=managed_sub)
        code, out = dc_helper.wait_for_subcloud_certificate(subcloud=managed_sub, subcloud_auth_info=subcloud_auth,
                                                            expected_certificate=new_central_signature)
        assert 0 == code, "Actual return code: {}, {} signature is {}".format(code, managed_sub, out)

    LOG.tc_step("Ensure new docker_registry certificate is not updated on unmanaged subcloud: {}"
                .format(primary_subcloud))
    subcloud_auth = Tenant.get('admin_platform', dc_region=primary_subcloud)
    code, out = dc_helper.wait_for_subcloud_certificate(subcloud=primary_subcloud, subcloud_auth_info=subcloud_auth,
                                                        expected_certificate=new_central_signature,
                                                        timeout=60, fail_ok=True)
    assert 0 != code, "Actual return code: {}, {} signature is {}".format(code, primary_subcloud, out)

    LOG.tc_step("verify on managed subclouds, docker login to registry.local success and to registry.central failed")
    registry_local = Container.LOCAL_DOCKER_REG
    registry_central = Container.CENTRAL_DOCKER_REG
    for subcloud in managed_subclouds:
        LOG.info("Verify {} access to registry.local should pass".format(subcloud))
        code, out = verify_access_to_registry(subcloud=subcloud, registry_addr=registry_local)
        assert 0 == code, "{} failed to access {} by {}".format(subcloud, registry_local, out)

        LOG.info("Verify {} access to registry.central should failed".format(subcloud))
        code, out = verify_access_to_registry(subcloud=subcloud, registry_addr=registry_central)
        assert 0 != code, "{} accessed {} by {}, the access should fail".format(subcloud, registry_central, out)

    LOG.tc_step("install new ssl_ca certificate on central region")
    code, out = cli.system("certificate-install -m ssl_ca ca-cert.pem", ssh_client=con_ssh, auth_info=sc_auth)
    assert 0 == code, "certificate-install cmd error: {}".format(out)

    new_central_signature = system_helper.get_certificate_signature(auth_info=sc_auth)
    LOG.tc_step("Wait for new certificate {} sync over to managed online subclouds".format(new_central_signature))
    for managed_sub in managed_subclouds:
        subcloud_auth = Tenant.get('admin_platform', dc_region=managed_sub)
        code, out = dc_helper.wait_for_subcloud_certificate(subcloud=managed_sub, subcloud_auth_info=subcloud_auth,
                                                            expected_certificate=new_central_signature)
        assert 0 == code, "Actual return code: {}, {} signature is {}".format(code, managed_sub, out)

    LOG.tc_step("verify on subcloud, docker login both registry.central and registry.local success")
    for subcloud in managed_subclouds:
        LOG.info("Verify {} access to registry.local should pass".format(subcloud))
        code, out = verify_access_to_registry(subcloud=subcloud, registry_addr=registry_local)
        assert 0 == code, "{} failed to access {} by {}".format(subcloud, registry_local, out)

        LOG.info("Verify {} access to registry.central should pass".format(subcloud))
        code, out = verify_access_to_registry(subcloud=subcloud, registry_addr=registry_central)
        assert 0 == code, "{} failed to access {} by {}".format(subcloud, registry_central, out)

    LOG.tc_step("Re-manage primary subcloud {} and ensure all certificates syncs over".format(primary_subcloud))
    dc_helper.manage_subcloud(subcloud=primary_subcloud, check_first=False)
    subcloud_auth = Tenant.get('admin_platform', dc_region=primary_subcloud)
    code, out = dc_helper.wait_for_subcloud_certificate(subcloud=primary_subcloud, subcloud_auth_info=subcloud_auth,
                                                        expected_certificate=new_central_signature, fail_ok=True)
    # two signatures may not be updated simultaneously, so check it twice
    if 2 == code:
        code, out = dc_helper.wait_for_subcloud_certificate(subcloud=primary_subcloud, subcloud_auth_info=subcloud_auth,
                                                            expected_certificate=new_central_signature)
    assert 0 == code, "Actual return code: {}, {} signature is {}".format(code, primary_subcloud, out)

    LOG.tc_step("Verify on primary subcloud, docker login both registry.central and registry.local success")
    LOG.info("Verify {} access to registry.local should pass".format(primary_subcloud))
    code, out = verify_access_to_registry(subcloud=primary_subcloud, registry_addr=registry_local)
    assert 0 == code, "{} failed to access {} by {}".format(primary_subcloud, registry_local, out)

    LOG.info("Verify {} access to registry.central should pass".format(primary_subcloud))
    code, out = verify_access_to_registry(subcloud=primary_subcloud, registry_addr=registry_central)
    assert 0 == code, "{} failed to access {} by {}".format(primary_subcloud, registry_central, out)

    LOG.tc_step("Ensure Central region access to external docker registry success")
    con_ssh = ControllerClient.get_active_controller(name='RegionOne')
    external_docker_registry = "tis-lab-registry.cumulus.wrs.com:9001"
    test_image = "hellokitty"
    tag = "v1.0"
    image_addr = "{}/gwaines/{}".format(external_docker_registry, test_image)
    code, out = container_helper.pull_docker_image(image_addr, tag=tag, con_ssh=con_ssh)
    assert 0 == code, "Central Region failed to access {} by {}".format(primary_subcloud, image_addr, out)


def verify_access_to_registry(subcloud, registry_addr, test_image="pause", tag="3.1"):
    LOG.info("Verify on {} docker access to {}".format(subcloud, registry_addr))
    con_ssh = ControllerClient.get_active_controller(name=subcloud)
    code, out = container_helper.login_to_docker(registry=registry_addr, con_ssh=con_ssh, fail_ok=True)
    if 0 != code:
        LOG.info("{} login to {} failed with args {}".format(subcloud, registry_addr, out))
        return code, out

    image_addr = "{}/k8s.gcr.io/{}".format(registry_addr, test_image)
    code, out = container_helper.pull_docker_image(image_addr, tag=tag, con_ssh=con_ssh, fail_ok=True)
    if 0 != code:
        LOG.info("{} pull test image {} failed".format(subcloud, image_addr))
        return code, out

    code, out = container_helper.exec_docker_cmd(sub_cmd='logout', args=registry_addr, con_ssh=con_ssh, fail_ok=True)
    if 0 != code:
        LOG.info("{} logout from {} failed".format(subcloud, registry_addr))
        return code, out
    return code, out
