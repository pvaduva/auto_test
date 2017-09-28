from consts import build_server as build_server_consts
from consts.proj_vars import ProjVar, PatchingVars


def pytest_addoption(parser):

    patch_build_server_help = "TiS Patch build server host name from where the upgrade release software is downloaded." \
                              "By default, it is: {}".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])

    patch_dir_help = "Directory or file on the Build Server where the patch files located. Because the version must " \
                     "match that of the system software on the target lab, hence by default, we will deduce " \
                     "the location of the patch files and their version, unless users specify an absolute path " \
                     "containing valid patch files. This directory is usually a symbolic link in the load-build " \
                     "directory."

    patch_base_dir_help = "Directory on the Build Server under which the patch files are located. By default, " \
                          "it is: {}".format('/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build')

    parser.addoption('--patch-build-server', '--patch_build_server',  dest='patch_build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=patch_build_server_help)

    parser.addoption('--patch-dir', '--patch_dir',  dest='patch_dir', default=None,
                     action='store', metavar='DIR',  help=patch_dir_help)

    parser.addoption('--patch-base-dir', '--patch_base_dir',  dest='patch_base_dir', default=None,
                     action='store', metavar='BASEDIR',  help=patch_base_dir_help)


def pytest_configure(config):
    patch_build_server = config.getoption('patch_build_server')
    patch_dir = config.getoption('patch_dir')
    patch_base_dir = config.getoption('patch_base_dir')

    if patch_build_server is not None:
        PatchingVars.set_patching_var(patch_build_server=patch_build_server)
    else:
        PatchingVars.set_patching_var(patch_build_server=PatchingVars.get_patching_var('def_patch_build_server'))

    if patch_base_dir is not None:
        PatchingVars.set_patching_var(patch_base_dir=patch_base_dir)
    else:
        PatchingVars.set_patching_var(patch_base_dir=PatchingVars.get_patching_var('def_patch_build_base_dir'))

    PatchingVars.set_patching_var(patch_dir=patch_dir)
