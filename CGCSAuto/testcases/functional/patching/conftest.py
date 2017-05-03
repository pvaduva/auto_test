from consts import build_server as build_server_consts
from consts.proj_vars import ProjVar, PatchingVars


def pytest_addoption(parser):
    patch_build_server_help = "TiS Patch build server host name where the upgrade release software is downloaded from." \
                        " ( default: {})".format(build_server_consts.DEFAULT_BUILD_SERVER['name'])
    patch_dir_help = "Directory on the Build Server where the patch files located"

    parser.addoption('--patch-build-server', '--patch_build_server',  dest='patch_build_server',
                     action='store', metavar='SERVER', default=build_server_consts.DEFAULT_BUILD_SERVER['name'],
                     help=patch_build_server_help)

    parser.addoption('--patch-dir', '--patch_dir',  dest='patch_dir', default='latest_build',
                     action='store', metavar='DIR',  help=patch_dir_help)


def pytest_configure(config):
    patch_build_server = config.getoption('patch_build_server')
    patch_dir = config.getoption('patch_dir')

    if patch_dir is not None:
        PatchingVars.set_patching_var(patch_build_server=patch_build_server,
                                      patch_dir=patch_dir)

