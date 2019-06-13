from pytest import mark, skip, fixture

from consts.cgcs import FlavorSpec
from consts.reasons import SkipHypervisor
from keywords import vm_helper, network_helper, nova_helper, glance_helper, cinder_helper, system_helper, host_helper
from keywords import kube_helper
from testfixtures.fixture_resources import ResourceCleanup
from utils.tis_log import LOG

@fixture(scope='module')
def assign_label_sriovdp():
    internal_net_id = network_helper.get_internal_net_id()
    mgmt_net_id = network_helper.get_mgmt_net_id()
    tenant_net_id = network_helper.get_tenant_net_id()

    labels = host_helper.assign_host_labels(labels='sriovdp')[1]

    return labels


def test_cni_plugins(assign_label_sriovdp):

    labels = assign_label_sriovdp
    LOG.info("Label assing {}".format(labels))

