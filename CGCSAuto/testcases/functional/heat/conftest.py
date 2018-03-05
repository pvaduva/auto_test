from testfixtures.resource_mgmt import *
from consts.cgcs import HEAT_FLAVORS, FlavorSpec


@fixture(scope='session', autouse=True)
def create_heat_flavors(heat_files_check):
    LOG.fixture_step("(session) Get or create a default heat flavor with 1 vcpu and dedicated cpu policy")

    for flv_name in HEAT_FLAVORS:
        flavor = nova_helper.get_flavor_id(name=flv_name, strict=True)
        if not flavor:
            flavor = nova_helper.create_flavor(name=flv_name)[1]
            if 'ded' in flv_name:
                nova_helper.set_flavor_extra_specs(flavor, **{FlavorSpec.CPU_POLICY: 'dedicated'})

        ResourceCleanup.add('flavor', flavor, scope='session')
