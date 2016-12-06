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


@fixture(scope='module', params=['fix1_1', 'fix1_2'])
def fix1(request):
    LOG.info('fix1 setup. param: {}'.format(request.param))

    def td():
        LOG.info('fix1 teardown. param: {}'.format(request.param))
    request.addfinalizer(td)
    return


@fixture(scope='module', params=['fix2_1', 'fix2_2'])
def fix2(request, fix1):
    LOG.info('fix2 setup. param: {}'.format(request.param))

    def td():
        LOG.info('fix2 teardown. param: {}'.format(request.param))

    request.addfinalizer(td)
    return


def test_fixtures(fix2):
    LOG.info("in test")


@fixture(scope='module', autouse=True)
def fix_autouse(request):
    LOG.fixture_step("I'm a autouse fixture step")

    def fix_teardown():
        LOG.fixture_step("I'm a autouse fixture teardown")
    request.addfinalizer(fix_teardown)


@fixture(scope='function')
def fix_usefixture(request):
    LOG.fixture_step("I'm a usefixture fixture step")

    def fix_teardown():
        LOG.fixture_step("I'm a usefixture teardown")

    request.addfinalizer(fix_teardown)


@fixture(scope='function')
def fix_testparam(request):
    LOG.fixture_step("I'm a testparam fixture step")

    def fix_teardown():
        LOG.fixture_step("I'm a testparam teardown")

    request.addfinalizer(fix_teardown)
    return "testparam returned"

test_iter = 0
@mark.usefixtures('fix_usefixture')
def test_stress(fix_testparam):
    LOG.tc_step("Hey i'm a test step")
    LOG.tc_step(str(fix_testparam))

    global test_iter
    if test_iter > 0:
        assert 0, "Test function failed"

    test_iter += 1

