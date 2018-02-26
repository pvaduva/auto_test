import time
import datetime
from pytest import fixture, mark
from keywords import system_helper, html_helper, common
from utils.tis_log import LOG


@fixture(scope='module')
def service_params(request):
    """
    Reset service parameter created in these tests to default value.
    """
    service = 'identity'
    section = 'config'
    name = 'token_expiration'
    exp_time = system_helper.get_service_parameter_values(rtn_value='value', service=service, section=section,
                                                          name=name)[0]

    def cleanup():
        LOG.fixture_step("Verifying service parameter {} {} {} is at default value".format(service, section, name))
        res = system_helper.get_service_parameter_values(rtn_value='value', service=service, section=section,
                                                         name=name)[0]
        if res != exp_time:
            LOG.fixture_step("Resetting service parameter {} {} {} to default of {}".format(service, section,
                                                                                            name, exp_time))
            system_helper.modify_service_parameter(service, section, name, str(exp_time), apply=True)

    request.addfinalizer(cleanup)
    return service, section, name


@mark.p2
def test_token_expiry(service_params):
    """
    Verify that token expiry time can be changed using service parameters

    Test Steps:
        - Verify that the token expiration is set by default.
        - Set token expiry length to set values
        - Verify that the length is rejected if it is not between 1 and 4 hours
        - Create a token and ensure it expires after the expected expiry time


    """
    expire_times = [6000, 7200, 3000, 15500, 3600]
    service, section, name = service_params
    LOG.tc_step("Verify that token_expiration parameter is defined")
    default_exp_time = system_helper.get_service_parameter_values(rtn_value='value', service=service, section=section,
                                                                  name=name)[0]
    assert int(default_exp_time) == 3600, "Default token_expiration value not 3600, actually {}".format(default_exp_time)

    LOG.tc_step("Verify that tokens now expire after expected time")
    token_expire_time = html_helper.get_user_token(rtn_value='expires')
    expt_time = time.time() + int(default_exp_time)
    expt_datetime = datetime.datetime.utcfromtimestamp(expt_time).isoformat()
    time_diff = common.get_timedelta_for_isotimes(expt_datetime, token_expire_time).total_seconds()

    LOG.info("Expect expiry time to be {}. Token expiry time is {}. Difference is {}."
             .format(token_expire_time, expt_datetime, time_diff))
    assert -150 < time_diff < 150, "Token expiry time is {}, but token expired {} seconds after expected time.".\
        format(expt_time, time_diff)

    for expire_time in expire_times:
        if expire_time > 14400 or expire_time < 3600:
            res, out = system_helper.modify_service_parameter(service, section, name, str(expire_time), fail_ok=True)
            assert 1 == res, "Modifying the expiry time to {} was not rejected".format(expire_time)
            assert "must be between 3600 and 14400 seconds" in out, "Unexpected rejection string"

            value = system_helper.get_service_parameter_values(service=service, section=section, name=name)
            assert expire_time != value, "Expiry time was changed to rejected value"
        else:
            LOG.tc_step("Set token expiration service parameter to {}".format(expire_time))
            system_helper.modify_service_parameter(service, section, name, str(expire_time), apply=True)

            LOG.tc_step("Verify that tokens now expire after expected time")
            token_expire_time = html_helper.get_user_token(rtn_value='expires')
            expt_time = time.time() + expire_time
            expt_datetime = datetime.datetime.utcfromtimestamp(expt_time).isoformat()
            time_diff = common.get_timedelta_for_isotimes(expt_datetime, token_expire_time).total_seconds()

            LOG.info("Expect expiry time to be {}. Token expiry time is {}. Difference is {}."
                     .format(token_expire_time, expt_datetime, time_diff))
            assert -150 < time_diff < 150, "Token is not set to expire after {} seconds".format(expire_time)
