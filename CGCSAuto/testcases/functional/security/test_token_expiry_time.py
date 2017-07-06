import time
import datetime
from pytest import fixture, mark
from keywords import system_helper, html_helper, common
from utils.tis_log import LOG


@fixture(scope='module')
def service_params(request):
    """
    Delete service parameter created in these tests
    """
    service = 'identity'
    section = 'config'
    name = 'token_expiration'

    def cleanup():
        LOG.fixture_step("Deleting service parameter {} {} {}".format(service, section, name))
        uuid = system_helper.get_service_parameter_values(rtn_value='uuid', service=service, section=section, name=name)
        if isinstance(uuid, list):
            uuid = uuid[0]
        res, out = system_helper.delete_service_parameter(uuid)
        if res == 0:
            LOG.info("Service parameter {} {} {} deleted".format(service, section, name))
            system_helper.apply_service_parameters(service=service, wait_for_config=True)

    request.addfinalizer(cleanup)
    return service, section, name


@mark.p2
def test_token_expiry(service_params):
    """
    Verify that token expiry time can be changed using service parameters

    Test Steps:
        - Set token expiry length to set values
        - Verify that the length is rejected if it is not between 1 and 4 hours
        - Create a token and ensure it expires after the expected expiry time


    """
    expire_times = [6000, 3600, 7200, 3000, 15500]
    service, section, name = service_params

    expire_time = expire_times.pop(0)
    LOG.tc_step("Set token expiration service parameter to {}".format(expire_time))
    system_helper.create_service_parameter(service, section, name, str(expire_time))
    system_helper.apply_service_parameters(service, wait_for_config=True)

    LOG.tc_step("Verify that tokens now expire after expected time")
    token_expire_time = html_helper.get_user_token(rtn_value='expires')
    expt_time = time.time() + expire_time
    expt_datetime = datetime.datetime.utcfromtimestamp(expt_time).isoformat()
    time_diff = common.get_timedelta_for_isotimes(expt_datetime, token_expire_time).total_seconds()

    LOG.info("Expect expiry time to be {}. Token expiry time is {}. Difference is {}."
             .format(token_expire_time, expt_datetime, time_diff))
    assert -300 < time_diff < 300, "Token expiry time is {}, but token expired {} seconds after expected time.".\
        format(expire_time, time_diff)

    for expire_time in expire_times:
        if expire_time > 14400 or expire_time < 3600:
            res, out = system_helper.modify_service_parameter(service, section, name, str(expire_time), fail_ok=True)
            assert 1 == res, "Modifying the expiry time to {} was not rejected".format(expire_time)
            assert "must be between 3600 and 14400 seconds" in out, "Unexpected rejection string"

            value = system_helper.get_service_parameter_values(service=service, section=section, name=name)
            assert expire_time != value, "Expiry time was changed to rejected value"
        else:
            LOG.tc_step("Set token expiration service parameter to {}".format(expire_time))
            system_helper.modify_service_parameter(service, section, name, str(expire_time))
            system_helper.apply_service_parameters(service, wait_for_config=True)

            LOG.tc_step("Verify that tokens now expire after expected time")
            token_expire_time = html_helper.get_user_token(rtn_value='expires')
            expt_time = time.time() + expire_time
            expt_datetime = datetime.datetime.utcfromtimestamp(expt_time).isoformat()
            time_diff = common.get_timedelta_for_isotimes(expt_datetime, token_expire_time).total_seconds()

            LOG.info("Expect expiry time to be {}. Token expiry time is {}. Difference is {}."
                     .format(token_expire_time, expt_datetime, time_diff))
            assert -5 < time_diff < 5, "Token is not set to expire after {} seconds".format(expire_time)
