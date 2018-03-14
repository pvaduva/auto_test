from consts import build_server as build_server_consts
from consts.proj_vars import PatchingVars


def pytest_configure(config):
    patch_build_server = config.getoption('patch_build_server')
    patch_dir = config.getoption('patch_dir')
    patch_base_dir = config.getoption('patch_base_dir')

    if not patch_build_server:
        patch_build_server = build_server_consts.DEFAULT_BUILD_SERVER['name']
    PatchingVars.set_patching_var(patch_build_server=patch_build_server)

    if patch_base_dir is not None:
        PatchingVars.set_patching_var(patch_base_dir=patch_base_dir)
    else:
        PatchingVars.set_patching_var(patch_base_dir=PatchingVars.get_patching_var('def_patch_base_dir'))

    PatchingVars.set_patching_var(patch_dir=patch_dir)
