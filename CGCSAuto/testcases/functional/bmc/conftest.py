def pytest_generate_tests(metafunc):
    if 'bmc_targets' in metafunc.fixturenames:
        metafunc.parametrize("bmc_targets", metafunc.config.getoption("bmc_target"))

    if 'bmc_password' in metafunc.fixturenames:
        metafunc.parametrize("bmc_password", metafunc.config.getoption("bmc_password"))
