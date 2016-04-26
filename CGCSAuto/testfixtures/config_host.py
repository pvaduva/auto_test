from pytest import fixture, mark
from keywords import host_helper


@mark.tryfirst
@fixture(scope='module')
def config_host(request):

    def config_host_func(host, modify_func, revert_func=None, *args, **kwargs):
        host_helper.lock_host(host=host)

        # add teardown before running modify (as long as host is locked successfully) in case modify or unlock fails.
        if revert_func is not None:
            def revert_host():
                host_helper.lock_host(host=host)
                try:
                    revert_func(host)
                except:
                    raise
                finally:
                    # Put it in finally block in case revert_func fails - host will still be unlocked for other tests.
                    host_helper.unlock_host(host=host)

            request.addfinalizer(revert_host)

        modify_func(host, *args, **kwargs)
        host_helper.unlock_host(host=host)

    return config_host_func
