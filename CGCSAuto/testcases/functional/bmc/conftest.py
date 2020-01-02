def pytest_generate_tests(metafunc):
    if 'bmc_targets' in metafunc.fixturenames:
        metafunc.parametrize("bmc_targets", metafunc.config.getoption("bmc_target"))
