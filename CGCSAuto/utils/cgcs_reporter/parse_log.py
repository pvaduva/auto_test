import re


write_command_pattern = "^(?!.*(show|list|echo \$\?|whoami|hostname|exit|stat|ls|Send '')).*"
test_steps_pattern = "^=+ (Setup|Test|Teardown) Step \d+"


def _get_failed_test_names(log_dir):
    """
        Parses test_results for names of failed tests

        Args:
            log_dir: directory the log is located

        Returns (list):
            [test_name, test_name, ...]

    """
    with open("{}/test_results.log".format(log_dir), 'r') as file:
        failed_tests = []

        for line in file:
            if line.startswith("FAIL"):
                test_name = 'test_' + line.split('::test_', 1)[1].replace('\n', '')
                failed_tests.append(test_name)

        return failed_tests


def get_parsed_failures(log_dir, traceback_lines=10, parse_full_error=False):
    """
        Parses pytestlog for the traceback of any failures up to a specified line count

        Args:
            log_dir: directory the log is located
            traceback_lines: Number of lines to record before the point of failure
            parse_full_error: False only parses up to first part of the error, True will parse until the very end

        Returns (dict):
            {test_name:traceback, test_name:traceback, ...}

    """
    failed_tests = _get_failed_test_names(log_dir)
    test_name = None
    temp_error = []
    errors = {}
    flags = {
        'error_found': False,
        'definition_found': False,
        'breakpoint_found': False  # Only used while parsing full error
    }

    with open("{}/pytestlog.log".format(log_dir), 'r') as file:
        for line in file:
            if flags['error_found'] is False:  # Find start of error/fail in log and set error_flag
                split_line = line.split('::test_', 1)  # Verify ::test_ exists in the line
                if len(split_line) is 2:
                    test_name = 'test_' + split_line[1].replace('\n', '')
                    if test_name in failed_tests:
                        flags['error_found'] = True
            else:
                # Fail safe in case log format is messed up. This prevents a failure from a test being associated with
                # the incorrect test in the test history database. Also required for parsing full error.
                if re.search("^[EFS.][ ](testcases)", line):
                    if flags['breakpoint_found'] is True:
                        errors[test_name] = errors[test_name] + ''.join('\n---SEPARATE FAILURE TRACEBACK---\n')
                    flags['error_found'] = False
                    flags['breakpoint_found'] = False

                if flags['definition_found'] is False:
                    # Find function definition and add line to list
                    if re.search("(def)[ ][^ ]", line):
                        flags['definition_found'] = True
                        temp_error.append(line)
                    if flags['breakpoint_found'] is True:
                        if re.search("^[ ][E]", line):  # Found end of error through whole trace
                            flags['breakpoint_found'] = False
                            flags['error_found'] = False
                            errors[test_name] = errors[test_name] + ''.join(line)

                else:
                    # Add lines to temp list until location error occurred is reached
                    temp_error.append(line)
                    if re.search("^[ ][>]", line):
                        if parse_full_error is True:
                            flags['breakpoint_found'] = True
                        else:
                            flags['error_found'] = False

                        flags['definition_found'] = False

                        # If number of lines exceeds traceback_lines, remove lines from beginning of temp list
                        lines_size = len(temp_error)
                        test = {}
                        test['testing'] = ''.join(temp_error)
                        if lines_size > traceback_lines:
                            del temp_error[0:lines_size-traceback_lines]

                        # Copy list into errors list
                        if str(test_name) not in errors:
                            errors[test_name] = '---FAILURE TRACEBACK---\n' + ''.join(temp_error)
                        else:
                            if parse_full_error is False:
                                errors[test_name] = errors[test_name] + '\n---SEPARATE FAILURE TRACEBACK---\n' + \
                                                    ''.join(temp_error)
                            else:
                                errors[test_name] = errors[test_name] + ''.join(temp_error)

                        del temp_error[:]
    return errors


def get_parsed_failure(traceback, traceback_lines=10):
    """
        Parses traceback for a failure up to a specified line count

        Args:
            traceback (string): traceback from log file / running test
            traceback_lines: Number of lines to record before the point of failure

        Returns (string): traceback trimmed to specified line count

    """
    error = ['---FAILURE TRACEBACK---\n']
    flags = {
        'error_found': False,
        'definition_found': False,
    }
    lines = traceback.splitlines()
    for line in lines:
        if flags['definition_found'] is False:
            # Find function definition and add line to list
            if re.search("(def)[ ][^ ]", line):
                flags['definition_found'] = True
                error.append(line + '\n')
        else:
            # Add lines to list until location error occurred is reached
            error.append(line + '\n')
            if re.search("^[>]", line):
                flags['error_found'] = False
                flags['definition_found'] = False

                # If number of lines exceeds traceback_lines, remove lines from beginning of list
                lines_size = len(error)
                if lines_size > traceback_lines:
                    del error[1:lines_size-traceback_lines]

    return ''.join(error)


def parse_test_steps(log_dir, failures_only=True):
    """
        Parses TIS_AUTOMATION for test steps

        Args:
            log_dir (str):          Directory the log is located
            failures_only (bool):   True  - Parses only failed tests
                                    False - Parses all tests

    """
    if failures_only:
        failed_tests = _get_failed_test_names(log_dir)
    test_found = False
    test_steps_length = 0
    test_steps = []

    with open("{}/TIS_AUTOMATION.log".format(log_dir), 'r') as file, \
            open("{}/test_steps.log".format(log_dir), 'w') as log:
        for line in file:

            if test_steps_length >= 1000:
                log.write(''.join(test_steps))
                test_steps_length = 0
                test_steps = []

            if not test_found:
                if "Setup started for:" in line:
                    if failures_only:
                        split_line = line.split('::test_', 1)
                        if len(split_line) is 2:
                            test_name = 'test_' + split_line[1].replace('\n', '')
                            if test_name in failed_tests:
                                test_found = True
                                test_steps.append(line)
                                test_steps_length += 1
                    else:
                        test_found = True
                        test_steps.append(line)
                        test_steps_length += 1
                continue

            if ":: Send " in line:
                if re.search(write_command_pattern, line):
                    test_steps.append(line)
                    test_steps_length += 1
                continue

            if " started for:" in line:
                test_steps.append("\n" + line)
                test_steps_length += 1
                continue

            if "***Failure at" in line:
                test_steps.append("\n" + line)
                test_steps_length += 1
                continue

            if re.search(test_steps_pattern, line):
                test_steps.append(line)
                test_steps_length += 1
                continue

            if "Test Result for:" in line:
                test_found = False
                test_steps.append("\n\n\n\n\n\n")
                test_steps_length += 6

        log.write(''.join(test_steps))
