##############
Best Practices
##############


Naming Conventions
------------------

General Naming Conventions
^^^^^^^^^^^^^^^^^^^^^^^^^^

module_name, package_name, ClassName, method_name, ExceptionName, function_name, GLOBAL_CONSTANT_NAME, global_var_name, instance_var_name, function_parameter_name, local_var_name

Function Naming Conventions
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In general, function name should be Verb + Noun. (Some exceptions: test fixtures with return values, function with bool return value)
Naming convention for function with bool return value:

.. code-block:: python

 # Format: is_foo()
 is_small_footprint()	
 # Noun + Verb is okay if makes more sense
 vm_exists() 

Naming should indicate single or plural return value(s)

.. code-block:: python

 # Return single value in string, int, etc
 get_host()
 # Return iterable, such as list, tuple, dictionary, etc
 get_controllers()

Functions retrieving host(s) info by default should return hostname unless specified.

.. code-block:: python

 # Return HOSTNAMES if unspecified
 get_controllers() 
 # Return host id as specified in the func name
 get_host_id()

Functions retrieving info other than host(s) by default should return ID(s) unless specified.
This is due to 1) Duplicated name is allowed for most items, such as VM, Volume, Network, etc. 2) Some cli commands only accept ID as positional arg.

.. code-block:: python

 # Return a list of vm IDs if unspecified
 get_vms()
 # Return vm name as specified in the func name
 get_vm_name_from_id()


Imports
-------

Order for imports

.. code-block:: python

 #1. System imports
 # Typical keyword module imports:
 import re
 import time
 from contextlib import contextmanager

 #2. Third party imports
 # Typical test case module imports:
 from pytest import fixture, mark, skip
 from setup_consts import P1, P2, P3

 #3. CGCSAuto utils imports
 from utils import cli, exceptions, table_parser
 from utils.ssh import ControllerClient, SSHFromSSH
 from utils.tis_log import LOG

 #4. CGCSAuto consts and keywords
 from consts.auth import Tenant
 from consts.cgcs import HostAavailabilityState, HostAdminState
 from consts.timeout import HostTimeout
 from keywords import nova_helper, vm_helper, host_helper, system_helper
 from keywords.security_helper import LinuxUser


Test Function
-------------

 * Concept of test function: One Test Function can yield one or more Test Cases by parametrizing the test function using pytest
   
   * For example test_live_migrate_vms() test function generates 36 test cases in total handles different vm types and hosts storage backing.

Mandatory Doc Strings for a Test Function
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 * Test Summary: Describe what this test function covers in high level
 * Skip Conditions (if any): Overall skip conditions to skip the whole test function. e.g., Skip test function if it's small footprint lab.
 * Prerequisites (if any): Prerequisites of the system config. i.e., not configured by automated test.
 * Test case should be smart enough to discover the current system configs and skip one or more test cases that don't match the current system configs.
 * Test Setups (if any test fixture is used): Such as create a flavor, create a vm from flavor, etc. Test fixture(s) for specific test function(s) might need to be written to perform the setups.
 * Test Steps: Describe the test steps. Also use LOG.tc_step("descriptions of this step") inside the test function body to add step logs.
 * Test Teardown (if teardown is included in any test fixture): Describe the test teardown to clean up the created resources, etc. Such as delete created vms, volumes, flavors, etc

.. code-block:: python

 # Example doc strings for test_lock_with_vms() in testcases/functional/nova/test_lock_with_vms.py
 def test_lock_with_vms(self, target_hosts):
     """
     Test lock host with vms on it.  

     Args:
         target_hosts (list): targeted host(s) to lock that was prepared by the target_hosts test fixture.
     
     Skip Conditions: 
         - Less than 2 hypervisor hosts on the system

     Prerequisites: 
         - Hosts storage backing are pre-configured to storage backing under test 
             ie., 2 or more hosts should support the storage backing under test.
     Test Setups:
         - Set instances quota to 10 if it was less than 8
         - Determine storage backing(s) under test. i.e.,storage backings supported by at least 2 hosts on the system
         - Create flavors with storage extra specs set based on storage backings under test
         - Create vms_to_test that can be live migrated using created flavors
         - Determine target host(s) to perform lock based on which host(s) have the most vms_to_test
         - Live migrate vms to target host(s)
     Test Steps:
         - Lock target host
         - Verify lock succeeded and vms status unchanged
         - Repeat above steps if more than one target host
     Test Teardown:
         - Delete created vms and volumes
         - Delete created flavors
         - Unlock locked target host(s)

     """

Keywords
--------

Action Keywords to Perform An Action
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 * Examples of action keywords: swact_host(), boot_vm(), set_flavor_extra_specs(), etc
 * Returns:

   * Always return a list composed of return code and extra info. Format: [return_code(int), extra_info(normally a string)]
   * Return code should indicate whether the action is successful

     * -1 (optional): Action was already done, return without doing anything
     * 0: Action is successfully performed, and post action check passed
     * 1: Action is rejected (and it is expected rejection)
     * .... Other failure scenarios. .Such as Action is accepted, but post action check failed. e.g., live migrate vm cli is performed without any error, but vm is still on the same host after running the cli.
   * Extra info is either the ID(s) of the newly created item(s), or error messages descriping the failure.
 * Mandatory Arguments:

   * fail_ok (bool):

     * when True: always return the list to let the test case decide what to do with the failures
     * when False (default): raise Exception when failure encounters. e.g., only scenarios with return code -1 and 0 should be returned, if other failure scenarios encoutered, keyword should raise an exception instead.
   * check_first (bool) --- This is required if scenario with -1 return code is handled by the keyword:

     * when True (default): Check whether Action is already performed before attempt it. e.g., check if a host is already locked before trying to lock it.
     * when False: Perform the action regardless. This is needed for some negative test case, e.g., verify lock request will be rejected for a host that's already locked
   * con_ssh (SSHClient):

     * Default value: None Pass this param to applicable CLI commands ran by the keyword.
   * auth_info (dict): Auth info for running the cli commands

     * default value: None or Tenant.get('admin')
     * When None, the Primary Tenant that was set for the whole test session will be used to run the CLI command
     * Some cli will have to be run by admin, thus default value will be set to Tenant.get('admin'). But we should still add the auth_info flag to Action Keyword to allow negative test with non-admin tenant.

Info Keywords to Retrieve Info
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 * Examples of info keywords: get_controllers(), get_vms(), get_flavor_extra_specs(), is_small_footprint(), etc
 * Returns whatever make sense. No mandatory return values.
 * Mandatory Arguments:

   * con_ssh (SSHClient):

     * Default value: None Pass this param to applicable CLI commands ran by the keyword
   * auth_info (dict):

     * Optional if all CLIs used in the keyword has to be run by admin. i.e., keyword can hardcode Tenant.get('admin') to run all the CLI
     * Mandatory if any CLI(s) used in the keyword should be run by a tenant.

Other Conventions
-----------------

 * Max characters in one line: 120

   * PEP-8 uses 80 which benefits mobile users, but it seems to be a bit too limited with our wide screen monitors
 * Use string.format() to format a string. Reason: variable type is handled automatically.

.. code-block:: python
 
  >>> print ("{} has {} hosts: {}".format('R720_1_2', 4, ['controller-0', 'controller-1']))
  R720_1_2 has 4 hosts: ['controller-0', 'controller-1']


Things to Avoid
---------------

 * Avoid using **TAB** unless it's set to 4 spaces in your editor
 * Avoid ``from my_package.my_module import *.`` Reasons:

   * Hides the origin of the imported variables/functions
   * Might unintentionally override the variable/function
   * Messes up global variables
 * Avoid catching exception in a test function

   * Action Keywords should define proper return code, with a **fail_ok** flag
 * Avoid writing very long function

   * Usually should be within the height of your computer monitor excluding doc strings, i.e., 55 - 60 lines. Or page-down once should bring you to the end of the function.
   * Extract some contents out to reduce the length and increase the readability of a function
 * Avoid nested function (func inside a func)

   * Except ``@pytest.fixture()``. Test teardown should be written as a nested function of a ``@pytest.fixture()``.
   * For keyword function, create another assisting function instead, such as:

     * _func_name(): Similar to public func - can be used by any other functions.
     * _func_name() : Similar to protected func - can still be used by other module but not encouraged to use
     * __func_name(): Similar to private func - cannot be used by other module
   * For test function:

     * Create a new keyword or update existing keyword if possible
     * See if any content can/should be extracted out to test setups by creating a test fixture function (fuction decorated with ``@pytest.fixture()``)

