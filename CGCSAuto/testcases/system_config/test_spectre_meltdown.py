from pytest import mark
from keywords import system_helper
from utils.tis_log import LOG


@mark.parametrize('version', [
    'all',
    'v1'
])
def test_set_spectre_meltdown_version(version):
    version = 'spectre_meltdown_{}'.format(version)

    LOG.tc_step('Set spectre_meltdown security_feature to {} is not already done.'.format(version))
    system_helper.modify_spectre_meltdown_version(version=version)
