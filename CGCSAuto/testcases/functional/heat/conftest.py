from testfixtures.resource_mgmt import *
from consts.cgcs import HEAT_FLAVORS, FlavorSpec


@fixture(scope='session', autouse=True)
def create_heat_flavors(heat_files_check):
    LOG.fixture_step("(session) Get or create a default heat flavor with 1 vcpu and dedicated cpu policy")
    for flv_name in HEAT_FLAVORS:
        if not nova_helper.get_flavors(name=flv_name, strict=True):
            flavor = nova_helper.create_flavor(name=flv_name, cleanup='session')[1]
            if 'ded' in flv_name:
                nova_helper.set_flavor(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})
