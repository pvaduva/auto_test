Automation Best Practices
===============================================

Test Function Decorators
-----------------------------------------------

Test Function Level Skip Conditions (if applicable)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add ``@pytest.mark.skipif()`` decorator to test function to skip the whole test function when skip condition met
 * E.g., Test function is only applicable to small system

::

 # Example
 @mark.skipif(not system_helper.is_small_footprint(), reason="Only applies to small footprint lab.")
 def test_something():
 ...

System Verifications (if applicable)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Definition of System Verifiy Fixtures: system verifications that are not directly related to the test case. E.g., check system alarms, check hosts are in good states.
 * Add ``@pytest.mark.usefixtures()`` decorator to test function
 * Choose system verify fixtures from keywords/verify_fixtures.py
 * How does it work: compare results before and after running the test case. Test will be marked as fail if the post test check failed, e.g, If a new alarm is raised after the test case run, then this test case will be marked as fail.

::

 # Example
 @mark.usefixtures('check_vms', 'check_hosts')
 def test_something():
 ...

Test Function Arguments
-----------------------------------------------

Test params
 * Add parametrize decorator to test function: @pytest.mark.parametrize(test_data_matrix)
 * Purpose: parametrize the test function to generate multiple test cases using the same test function
Test Function Specific Fixtures
 * Defined in seperate test fixture function(s) with fixture decorator: @pytest.fixture
 * A test fixture function can be parametrized by passing parameters via params argument to fixture function

Components Inside Test Function
-----------------------------------------------

 * Doc strings: Summary, Test Args (Test Data or Test Fixtures), Skip Conditions, Prerequisites, Test Setups, Test Steps, Test Teardown

    * Doc strings are mandatory for a test case. Which will help identify what the test function covers, especially when parametrizing is used, it could be time consuming to find out what a test function do at a later time.
 * Test Case level skip conditions

    * This echos to Prerequisites in doc string.
    * Check the system to see if it meets the requirements of a specific test case. Skip a specific test cases if not met.
 * Log Test Steps

    * Use LOG.tc_step("desc of step")
 * Verify Test Result

    * Use assert to verify the test results
    * If assert failed, the test case result will be FAIL

        * Should catch the actual product issue
    * If an exception was thrown, the test result will be ERROR

        * Indicate test case or helper functions might need update, or
        * Indicate a product issue that is unrelated to this specific test case. NOTE: try to reduce this type of scenario by check the system conditions before running a test case. e.g., skip live     
    * migrate test case when number of hypervisors are less than 2 on the system.
    * Multiple assert can be used for multiple point of failures

        * Test will end right away upon the first assert failure.
        * Break into two tests if you want the test to continue to execute
    * In general, a test case should not throw an exception

Other
-----------------------------------------------

 * Try to avoid try/except in test function when possible

    * Action Keyword (such as live_migrate_vm) should have a fail_ok flag, and well defined return codes to assist for expected failures (i.e., negative tests)
 * Use helper keywords to write a test case

    * Try to avoid writing big long helper functions inside a test module, or even worse, inside a test function itself
    * Instead, create the helper function under automation/keywords, so it can be shared by other tests


