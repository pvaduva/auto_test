########################
How to Write a Test Case
########################

Test Function Decorators
------------------------

Skip Conditions (if applicable)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add ``@pytest.mark.skipif()`` decorator to test function 
 * to skip the whole test function when skip condition met
 * E.g., Test function is only applicable to small system

.. code-block:: python

 # Example
 # In our example system_helper.is_small_footprint() return True
 @mark.skipif(not system_helper.is_small_footprint(), reason="Only test small footprint")
 def test_something():
 ...

 #when the above executed on the commandline using py.test. the test will be skipped.



System Verifications (if applicable)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Add ``@pytest.mark.<P1-P3,sanity,cpe_sanity>``
 * to set the specific type of test you are running. weither it's a P1,P2,P3,cpe_sanity or sanity testcases

.. code-block:: python

 # Example
 # this is a sanity testcase
 @mark.sanity
 def test_something():
 ...

 #when the above is executed with 'py.test -m sanity' this test will automatically be included

System Verifications (if applicable)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add ``@pytest.mark.usefixtures()`` decorator to test function 
 * for system verifications that are not directly related to the test case. E.g., check system alarms, check hosts are in good states.
 * All default fixtures are stored under :ref:`testfixtures-ref-label`.
 * How does it work: It trys to setup an eonvironment where a test can be run or verify certain critieria is same before and after the test. Test will be marked as fail if the post test check failed, e.g, A new alarm is raised only after the test case run but not before, then this test case will be marked as fail.

.. code-block:: python

 # Example
 # @fixture check_vms and check_hosts was defined under testfixtures/verify_fixtures.py
 # they verify the statue of the vms/hosts is same before and after the testcase. 
 # An error will be raised otherwise.
 @mark.usefixtures('check_vms', 'check_hosts')
 def test_something():
 ...

Add ``@pytest.fixture()`` to Test Function Specific Fixtures
 * A fixture can also be defined within the test.py itself. If it's only needed for specific testcases.
 * Defined in seperate test fixture function(s) with fixture decorator: @pytest.fixture()
 * A test fixture function can be parametrized by passing parameters via params argument to fixture function

.. code-block:: python

 # under testcase.py

 # a local fixture
 @pytest.fixture()
 def local_fixture(request):
    if a_condition_met() :
    return True

 #Do something with local fixture
 def test_something(local_fixture):
    if local_fixture:
    #do something...
 
Test parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add ``@pytest.mark.parametrize(test_data_matrix)`` to parametrize decorator to test function
 * Purpose: parametrize the test function to generate multiple test cases using the same test function

.. code-block:: python

 @mark.parametrize(('vcpus', 'cpu_policy', 'vcpu_id'),[
     mark.p2((4, 'shared', 3)),
     mark.p3((4, 'dedicated', 5)),
     mark.p3((4, 'dedicated', -1)),
     mark.p3((64, 'dedicated', 64)),
 ])
 def test_something(cpu_policy, vcpus, vcpu_id):
 ...

Components Inside Test Function
-------------------------------

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
-----

 * Try to avoid try/except in test function when possible

    * Action Keyword (such as live_migrate_vm) should have a fail_ok flag, and well defined return codes to assist for expected failures (i.e., negative tests)
 * Use helper keywords to write a test case

    * Try to avoid writing big long helper functions inside a test module, or even worse, inside a test function itself
    * Instead, create the helper function under automation/keywords, so it can be shared by other tests


Pytest
------
