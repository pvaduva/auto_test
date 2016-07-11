from pytest import fixture, mark
from keywords import host_helper


@mark.tryfirst
@fixture(scope='module')
def config_host(request):
    """
    Module level fixture to configure a host.

    Setup:
        - Lock a host
        - Configure host
        - Unlock host

    Teardown (if revert_func is given):
        - Lock host
        - Run revert_func
        - Unlock host

    Args:
        request: pytest param. caller of this func.

    Returns (function): config_host_func.
        Test or another fixture can execute it to pass the hostname, modify_func, and revert_func

    Examples:
        see 'add_shared_cpu' fixture in nova/test_shared_cpu_enabled.py for usage.

    """
    def config_host_func(host, modify_func=None, revert_func=None, *args, **kwargs):
        if modify_func is not None:
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

        if modify_func is not None:
            modify_func(host, *args, **kwargs)
            host_helper.unlock_host(host=host)

    return config_host_func


@mark.tryfirst
@fixture(scope='class')
def config_host_class(request):
    """
    Class level fixture to configure a host.

    Setup:
        - Lock a host
        - Configure host
        - Unlock host

    Teardown (if revert_func is given):
        - Lock host
        - Run revert_func
        - Unlock host

    Args:
        request: pytest param. caller of this func.

    Returns (function): config_host_func.
        Test or another fixture can execute it to pass the hostname, modify_func, and revert_func

    Examples:
        see 'add_shared_cpu' fixture in nova/test_shared_cpu_enabled.py for usage.

    """
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