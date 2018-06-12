from consts import build_server as build_server_consts
from consts.proj_vars import PatchingVars


def pytest_configure(config):
    patch_build_server = config.getoption('patch_build_server')
    patch_dir = config.getoption('patch_dir')
    patch_base_dir = config.getoption('patch_base_dir')
    controller_apply_strategy = config.getoption('controller_strategy')
    storage_apply_strategy = config.getoption('storage_strategy')
    compute_apply_strategy = config.getoption('compute_strategy')
    max_parallel_computes = config.getoption('max_parallel_computes')
    if not max_parallel_computes:
        max_parallel_computes = 2
    instance_action = config.getoption('instance_action')
    alarm_restrictions = config.getoption('alarm_restrictions')


    if not patch_build_server:
        patch_build_server = build_server_consts.DEFAULT_BUILD_SERVER['name']
    #PatchingVars.set_patching_var(patch_build_server=patch_build_server)


    if not patch_base_dir:
        #PatchingVars.set_patching_var(patch_base_dir=patch_base_dir)
        patch_base_dir=PatchingVars.get_patching_var('def_patch_base_dir')

    PatchingVars.set_patching_var(patch_dir=patch_dir,
                                  patch_build_server=patch_build_server,
                                  patch_base_dir=patch_base_dir,
                                  controller_apply_strategy=controller_apply_strategy,
                                  storage_apply_strategy=storage_apply_strategy,
                                  compute_apply_strategy=compute_apply_strategy,
                                  max_parallel_computes=max_parallel_computes,
                                  instance_action=instance_action,
                                  alarm_restrictions=alarm_restrictions)
