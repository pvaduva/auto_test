# import time
# import os
#
# from pytest import mark, fixture
#
# from utils.tis_log import LOG
# from utils.cli import ControllerClient
# from utils import cli
#
# from consts.filepaths import MuranoPath
# from consts.auth import Tenant, HostLinuxCreds
# from consts.cgcs import MuranoEnvStatus
# from keywords import murano_helper, host_helper, system_helper, glance_helper, common, network_helper
#
#
# @fixture(scope='module', autouse=True)
# def configure_murano(request):
#
#     def _disable_murano_service():
#
#         results = system_helper.get_service_parameter_values(service="murano", section="engine",
#                                                              name='disable_murano_agent')
#         if len(results) > 0:
#             if results[0] == 'false':
#                 env_ids = murano_helper.get_environment_list_table()
#                 for i in env_ids:
#                     murano_helper.delete_env(i)
#                 pk_ids = murano_helper.get_package_list()
#                 for p in pk_ids:
#                     murano_helper.delete_package(p)
#
#                 ret, out = murano_helper.enable_disable_murano(enable=False, enable_disable_agent=True,
#                                                                fail_ok=True)
#                 assert ret == 0, "Murano disable failed"
#
#     request.addfinalizer(_disable_murano_service)
#
#     # enable Murano and murano agent
#     LOG.fixture_step("Enable Murano and Murano aget... ")
#     ret, out = murano_helper.enable_disable_murano(enable_disable_agent=True)
#     assert ret == 0, "Murano enable failed"
#
#
# def test_murano(configure_murano):
#     """
#         Murano feature test cases
#
#         Test Steps:
#             - Enable murano and verify
#             - Get images, set and update
#             - Get murano applications
#             - import base packages
#             - Create Env
#             - Create Session
#             - Add app to env
#             - Deploy env
#             - Delete Env
#             - Disable Murano
#
#         Test Teardown:
#             - None
#
#         """
#
#     base_pkgs = ["/var/cache/murano/meta/io.murano.zip", "/var/cache/murano/meta/io.murano.applications.zip"]
#
#     # import and create murano image
#     LOG.tc_step("Importing and Creating Murano image... ")
#     img_id = glance_helper.get_guest_image('debian-8-m-agent', cleanup="module")
#     LOG.info('Image with name debian-8-m-agent with id {} has been created'.format(img_id))
#
#     # set and update image
#     LOG.tc_step("Setting and Updating  Murano image... ")
#     properties = '{\"title\": \"Debain 8 image with murano agent\", \"type\": \"linux\"}'
#     args = '--property murano_image_info=\'{}\' {}'.format(properties, img_id)
#     cli.openstack('image set', args, auth_info=Tenant.get('admin'))
#
#     LOG.info('Image properties have been updated')
#
#     # getting tenant mgmt subnet id
#     tenant = Tenant.get_primary()['tenant']
#     mgmt_net_name = "{}-mgmt-net".format(tenant)
#     LOG.tc_step("Getting {} network id ... ".format(mgmt_net_name))
#     mgmt_id = network_helper.get_net_id_from_name(mgmt_net_name)
#     assert mgmt_id, "Fail to get {} Tenant mgmt net id".format(mgmt_net_name)
#     LOG.info("Tenant mgmt id {}".format(mgmt_id))
#
#     # import base packages
#     LOG.tc_step("Importing base packages... ")
#     pkg_ids = []
#     for pkg in MuranoPath.BASE_PACKAGES:
#         out = murano_helper.import_package(pkg=pkg)[1]
#         pkg_ids.append(out)
#
#
#     # standby = system_helper.get_standby_controller_name()
#     # if standby:
#     #     LOG.tc_step("Swact active controller and ensure active controller is changed")
#     #     host_helper.swact_host()
#     #
#     #     LOG.tc_step("Check all services are up on active controller via sudo sm-dump")
#     #     host_helper.wait_for_sm_dump_desired_states(controller=standby, fail_ok=False)
#     # else:
#     #     if not system_helper.is_simplex():
#     #         assert False, "Unable to get the standby controller hostname"
#
#     # create Environment
#     name = 'Test_env2'
#     LOG.tc_step("Creating Murano environment {} ...".format(name))
#     code, env_id = murano_helper.create_env(mgmt_net_id=mgmt_id, name=name)
#     LOG.info('Murano enviroment {} has been created successfully'.format(env_id))
#
#     # create Session
#     LOG.tc_step("Creating Murano session ...")
#     session_id = murano_helper.create_session(env_id)[1]
#     LOG.info('Murano session {} has been created successfully'.format(session_id))
#
#     # add application to environment
#     LOG.tc_step("Adding application to  Murano enviroment ...")
#     app_info = add_app_to_env(env_id, session_id, img_id, mgmt_id)
#     assert app_info,  "Fail to add application to Murano enviroment: env_id {}; session_id {} img_id {}"\
#         .format(env_id, session_id, img_id)
#     LOG.info('Application added to murano environment:\n {}'.format(app_info))
#
#     # Deploy Environment
#     LOG.tc_step("Deploying Murano enviroment ...")
#     code, deployment_id = murano_helper.deploy_env(env_id, session_id)
#     LOG.tc_step("Waiting for Murano enviroment to be deployed ...")
#     murano_helper.wait_for_environment_status(env_id, [MuranoEnvStatus.READY])
#     LOG.info('Evnironment with ID {} has been deployed'.format(deployment_id))
#
#     time.sleep(30)
#     # delete Environment
#     LOG.tc_step("Deleting Murano enviroment ...")
#     murano_helper.delete_env(env_id=env_id)
#     murano_helper.wait_for_environment_delete(env_id)
#     LOG.info('Murano Evnironment with ID {} has been deleted successfully'.format(env_id))
#
#     LOG.tc_step("Deleting Murano packages ...")
#     for pkg_id in pkg_ids:
#         murano_helper.delete_package(package_id=pkg_id)
#         LOG.info("Murano package deleted {}".format(pkg_id))
#
#
# def add_app_to_env(env_id, session_id, image_id, mgmt_id):
#     if env_id is None:
#         env_id = murano_helper.create_env('test_env', mgmt_net_id=mgmt_id)[1]
#     if session_id is None:
#         session_id = murano_helper.create_session(env_id)[1]
#
#     demo_app = os.path.basename(MuranoPath.APP_DEMO_PATH)
#     common.scp_from_test_server_to_active_controller(MuranoPath.APP_DEMO_PATH, HostLinuxCreds.get_home())
#     ssh_conn = ControllerClient.get_active_controller()
#     rc = ssh_conn.exec_cmd("test -f " + HostLinuxCreds.get_home() + demo_app)[0]
#     assert rc == 0, "The Murano application demo file  {} not found".format(HostLinuxCreds.get_home() + demo_app)
#
#     # Deploy application package
#     code, pkg_id = murano_helper.import_package(pkg=HostLinuxCreds.get_home() + demo_app, fail_ok=True)
#     LOG.info("Murano Application package {} imported successfully. code = {}".format(pkg_id, code))
#
#     demo_app_file = os.path.splitext(demo_app)[0]
#
#     file = ('\n'
#             '[\n'
#             '    {{ "op": "add", "path": "/-", "value":\n'
#             '        {{\n'
#             '            "instance": {{\n'
#             '                "availabilityZone": "nova",\n'
#             '                "name": "xwvupifdxq27t1",\n'
#             '                "image": "{}",\n'
#             '                "keyname": "",\n'
#             '                "flavor": "medium.dpdk",\n'
#             '                "assignFloatingIp": false,\n'
#             '                "?": {{\n'
#             '                    "type": "io.murano.resources.LinuxMuranoInstance",\n'
#             '                    "id": "===id1==="\n'
#             '                }}\n'
#             '            }},\n'
#             '            "name": "Titanium Murano Demo App",\n'
#             '            "enablePHP": true,\n'
#             '            "?": {{\n'
#             '                "type": "{}",\n'
#             '                "id": "===id2==="\n'
#             '            }}\n'
#             '        }}\n'
#             '    }}\n'
#             ']').format(image_id, demo_app_file)
#
#     object_model = murano_helper.edit_environment_object_mode(env_id, session_id=session_id, object_model_file=file,
#                                                               delete_file_after=True)[1]
#
#     return object_model
