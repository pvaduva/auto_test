from pytest import fixture
from keywords import host_helper


@fixture(scope='module')
def config_host(request):

    def config_host_func(host, modify_func, revert_func=None, *args, **kwargs):
        host_helper.lock_host(host=host)
        try:
            modify_func(host, *args, **kwargs)
        except:
            # add unlock as teardown if modify failed.
            def _unlock():
                host_helper.unlock_host(host)
            request.addfinalizer(_unlock)
            raise

        host_helper.unlock_host(host=host)

        if revert_func is not None:
            def revert_host():
                host_helper.lock_host(host=host)
                revert_func(host)
                host_helper.unlock_host(host=host)

            request.addfinalizer(revert_host)

    return config_host_func
