from pytest import mark, fixture
from utils.tis_log import LOG


def test_foo_pass():
    LOG.tc_step("I'm a step hahaha")
    assert 1


def test_foo_fail():
    LOG.tc_step("I'm a step hahaha")
    assert 0


@fixture(scope='function')
def fail_teardown(request):
    LOG.info("In setup now")

    def teardown():
        LOG.info("In teardown now")
        assert 0, 'teardown fail here'
    request.addfinalizer(teardown)
    return

def test_foo_multifail(fail_teardown):
    LOG.tc_step("I'm a step hahaha")
    assert 0, 'test call fail here'


@mark.skipif(True, reason="i'm testing skip")
def test_foo_skip():
    LOG.tc_step("I'm a step hahaha")
