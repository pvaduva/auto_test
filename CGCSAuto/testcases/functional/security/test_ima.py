from pytest import mark, fixture, skip
from utils.tis_log import LOG
from utils.ssh import ControllerClient
from keywords import system_helper, common
from consts.cgcs import EventLogID
from consts.auth import HostLinuxCreds


@fixture()
def ima_precheck():
    """
    This tests if the system is enabled with IMA.  If not, we
    should skip IMA-related tests.
    """

    LOG.info("Checking if IMA is enabled")

    con_ssh = ControllerClient.get_active_controller()

    exitcode, output = con_ssh.exec_cmd("cat /proc/cmdline")
    if "extended" not in output:
        skip("IMA must be enabled in order to run this test")
    else:
        LOG.info("IMA is enabled")


@fixture()
def delete_files(request):
    def teardown():
        """
        Delete any created files on teardown.
        """

        global files_to_delete

        for filename in files_to_delete:
            delete_file(filename)

    request.addfinalizer(teardown)


def checksum_compare(source_file, dest_file):
    """
    This does a checksum comparison of two files.  It returns True if the
    checksum matches, and False if it doesn't.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Compare checksums on source file and destination file")
    cmd = "getfattr -m . -d {}"

    exitcode, source_sha = con_ssh.exec_cmd(cmd.format(source_file))
    LOG.info("Raw source file checksum is: {}".format(source_sha))
    source_sha2 = source_sha.split("\n")
    print("This is source_sha2: {}".format(source_sha2))
    assert source_sha2 != [''], "No signature on source file"

    if source_file.startswith("/"):
        source_sha = source_sha2[2] + " " + source_sha2[3]
    else:
        source_sha = source_sha2[1] + " " + source_sha2[2]

    LOG.info("Extracted source file checksum: {}".format(source_sha))

    exitcode, dest_sha = con_ssh.exec_cmd(cmd.format(dest_file))
    LOG.info("Raw symlink checksum is: {}".format(dest_sha))
    dest_sha2 = dest_sha.split("\n")

    if dest_file.startswith("/"):
        dest_sha = dest_sha2[2] + " " + dest_sha2[3]
    else:
        dest_sha = dest_sha2[1] + " " + dest_sha2[2]

    LOG.info("Extracted destination file checksum: {}".format(dest_sha))

    if source_sha == dest_sha:
        return True
    else:
        return False


def create_symlink(source_file, dest_file, user_type="root"):
    """
    This creates a symlink given a source filename and a destination filename.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Creating symlink to {} called {}".format(source_file, dest_file))
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("ln -sf {} {}".format(source_file, dest_file))
    else:
        exitcode, msg = con_ssh.exec_cmd("ln -sf {} {}".format(source_file, dest_file))

    assert exitcode == 0, "Symlink creation was expected to succeed but instead failed"


def delete_file(filename, user_type="root"):
    """
    This deletes a file.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Deleting file {}".format(filename))
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("rm {}".format(filename))
    else:
        exitcode, msg = con_ssh.exec_cmd("rm {}".format(filename))

    assert exitcode == 0, "Unable to delete file"


def chmod_file(filename, permissions, user_type="root"):
    """
    This modifies permissions of a file
    """

    con_ssh = ControllerClient.get_active_controller()

    # Should we be more pythonic?
    LOG.info("Changing file permissions for {}".format(filename))
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("chmod {} {}".format(permissions, filename))
    else:
        exitcode, msg = con_ssh.exec_cmd("chmod {} {}".format(permissions, filename))

    assert exitcode == 0, "Failed to change file permissions"


def chgrp_file(filename, group, user_type="root"):
    """
    This modifies the group ownership of a file
    """

    con_ssh = ControllerClient.get_active_controller()

    # Should we be more pythonic?
    LOG.info("Changing file permissions for {}".format(filename))
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("chgrp {} {}".format(group, filename))
    else:
        exitcode, msg = con_ssh.exec_cmd("chgrp {} {}".format(group, filename))

    assert exitcode == 0, "Failed to change file group ownership"


def chown_file(filename, file_owner, user_type="root"):
    """
    This modifies the user that owns the file
    """

    con_ssh = ControllerClient.get_active_controller()

    # Should we be more pythonic?
    LOG.info("Changing the user that owns {}".format(filename))
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("chown {} {}".format(file_owner, filename))
    else:
        exitcode, msg = con_ssh.exec_cmd("chown {} {}".format(file_owner, filename))

    assert exitcode == 0, "Failed to change file group ownership"


def copy_file(source_file, dest_file, user_type="root"):
    """
    This creates a copy of a file and preserves the attributes.
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Copy file and preserve attributes")
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("cp {} --preserve=all {}".format(source_file, dest_file))
    else:
        exitcode, msg = con_ssh.exec_cmd("cp {} --preserve=all {}".format(source_file, dest_file))

    assert exitcode == 0, "File copy unexpectedly failed"


def move_file(source_file, dest_file, user_type="root"):
    """
    This moves a file from source to destination
    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Copy file and preserve attributes")
    if user_type == "root":
        exitcode, msg = con_ssh.exec_sudo_cmd("mv {} {}".format(source_file, dest_file))
    else:
        exitcode, msg = con_ssh.exec_cmd("mv {} {}".format(source_file, dest_file))

    assert exitcode == 0, "Failed to move file from {} to {}".format(source_file, dest_file)


@mark.usefixtures("ima_precheck", "delete_files")
def test_ima_create_symlink():
    """
    This test validates symlink behaviour on an IMA-enabled system

    Test Steps:
        - Create a symlink
        - Confirm that source file and symlink checksum match
        - Confirm symlink creation does not trigger an IMA violation alarm
        - Remove the symlink

    Maps to TC_17684/T_15793 from US105523 (Symlink should work as
    expected)

    """

    global files_to_delete
    files_to_delete = []

    start_time = common.get_date_in_format()

    source_file = "/usr/sbin/ntpq"
    dest_file = "my_symlink"
    create_symlink(source_file, dest_file)

    files_to_delete.append(dest_file)

    checksum_match = checksum_compare(source_file, dest_file)
    assert checksum_match, "SHA256 checksum should match source file and the symlink but didn't"

    LOG.info("Ensure no unexpected events are raised")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA events found"


@mark.usefixtures("ima_precheck", "delete_files")
def test_ima_edit_monitored_file():
    """
    This test alters a monitored file and ensures the signature is lost.

    Test Steps:
    - Copy a file with attributes
    - Edit the file with vi and save it
    - This results in the IMA signature being lost
    - Try to execute the file
    - Ensure there is an event generated saying 'IMA-signature-required'

    Maps to TC_17642/T_15809 from US105523 Alter a monitored file by editing
    with vi, signature is lost

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """

    global files_to_delete
    files_to_delete = []

    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()
    host = system_helper.get_hostname()

    source_file = "/usr/sbin/ntpq"
    dest_file = "/usr/sbin/TEMP"
    copy_file(source_file, dest_file)

    LOG.info("Open copy of monitored file and save")
    cmd = "vim {} '+:wq!'".format(dest_file)
    exitcode, msg = con_ssh.exec_sudo_cmd(cmd)

    files_to_delete.append(dest_file)

    LOG.info("Execute monitored file")
    exitcode, msg = con_ssh.exec_sudo_cmd("{} -p".format(dest_file))

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found != [], "Expected IMA event not found"


@mark.usefixtures("ima_precheck", "delete_files")
def test_ima_append_monitored_file():
    """
    This test appends some data to a monitored file.  This should trigger a
    changing of the hash, and result in alarm.

    Test Steps:
    - Copy monitored file and preserve options
    - Echo data to append to the end of the file
    - Execute file via root user
    - Check the alarms for IMA violation

    Maps to TC_17641/T_15808 from US105523 (Alter a monitored file by adding a
    line to it)

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """


    global files_to_delete
    files_to_delete = []

    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()
    host = system_helper.get_hostname()

    source_file = "/usr/sbin/logrotate"
    dest_file = "/usr/sbin/TEMP"
    copy_file(source_file, dest_file)

    LOG.info("Append to copy of monitored file")
    cmd = 'echo "output" | sudo -S tee -a /usr/sbin/TEMP'.format(HostLinuxCreds.get_password())
    exitcode, msg = con_ssh.exec_cmd(cmd)

    files_to_delete.append(dest_file)

    LOG.info("Execute monitored file")
    exitcode, msg = con_ssh.exec_sudo_cmd("{}".format(dest_file))

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found != [], "Expected IMA event not found"


@mark.usefixtures("ima_precheck", "delete_files")
def test_ima_copy_file_noalarm():
    """
    This test validates that copying a root file with the proper IMA signature,
    makes its execution to work without appraisal.

    Test Steps:
    - Copy a monitored file
    - Execute the copy
    - Check for alarms (there should be none)

    Maps to TC_17644 from US105523.

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """

    global files_to_delete
    files_to_delete = []

    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()

    LOG.info("Copy a monitored file and preserve attributes")
    source_file = "/usr/sbin/ntpq"
    dest_file = "/usr/sbin/TEMP"
    copy_file(source_file, dest_file)

    files_to_delete.append(dest_file)

    LOG.info("Execute the copied file")
    exitcode, msg = con_ssh.exec_sudo_cmd("{} -p".format(dest_file))

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA events found"


@mark.usefixtures("ima_precheck")
def test_ima_dynamic_library_change():
    """
    This test validates that dynamic library changes are detected by the IMA
    code.

    Test Steps:
    - Backup library with attributes
    - Copy library without SHA checksum
    - Replace original library with unsigned one
    - After IMA appraisal has been detected, backup original library.

    Maps to TC_17662 from US105523.

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """


    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()

    source_file = "/lib64/libcrypt.so.1"
    dest_file = "/root/libcrypt.so.1"
    dest_file_nocsum = "/root/TEMP"

    LOG.info("Backup source file {} to {}".format(source_file, dest_file))
    copy_file(source_file, dest_file)

    LOG.info("Copy the library without the checksum")
    exitcode, msg = con_ssh.exec_sudo_cmd("cp {} {}".format(source_file, dest_file_nocsum))
    assert exitcode == 0, "File copy failed"

    LOG.info("Replace the library with the unsigned one")
    move_file(dest_file_nocsum, source_file)

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found != [], "Expected IMA event not found"

    LOG.info("Restore original library")
    move_file(dest_file, source_file)


@mark.usefixtures("ima_precheck", "delete_files")
def test_create_and_execute_new_root_file():
    """
    This test creates a new file owned by root and executes it, resulting in an
    IMA violation.

    Test Steps:
    - Create an executable script owned by root
    - Add exec permission
    - Execute it
    - Look for IMA violations

    This test maps to TC_17643/T_15803 from US105523 (Create a new file owned
    by root and execute it)

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """

    global files_to_delete
    files_to_delete = []

    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()

    dest_file = "/home/wrsroot/TEMP"

    LOG.info("Create new file")
    cmd = "touch {}".format(dest_file)
    exitcode, msg = con_ssh.exec_sudo_cmd(cmd)

    LOG.info("Set file to be executable")
    chmod_file(dest_file, "755")

    files_to_delete.append(dest_file)

    LOG.info("Append to file")
    cmd = 'echo "ls" | sudo -S tee -a {}'.format(dest_file)
    exitcode, msg = con_ssh.exec_cmd(cmd)
    assert exitcode == 0, "Failed to append to file"

    LOG.info("Execute file")
    exitcode, msg = con_ssh.exec_sudo_cmd("{}".format(dest_file))

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found != [], "Expected IMA event not found"


@mark.usefixtures("ima_precheck", "delete_files")
def test_create_new_file_and_execute_as_non_root_user():
    """
    This creates a new file owned by the wrsroot user and attempts to execute
    it.  This should not result in an IMA violation.

    Test Steps:
    - Create an executable script owned by root
    - Add exec permission
    - Execute it
    - Ensure there are no IMA violations

    This maps to TC_17902/T_17144 from US105523 (Create a new file owned by
    wrsroot user and execute it (non-root)

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """

    global files_to_delete
    files_to_delete = []

    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()

    dest_file = "/home/wrsroot/TEMP"

    LOG.info("Create new file")
    cmd = "touch {}".format(dest_file)
    exitcode, msg = con_ssh.exec_cmd(cmd)

    LOG.info("Set file to be executable")
    chmod_file(dest_file, "755", user_type="wrsroot")

    # Should I make this more pythonic?
    LOG.info("Append to copy of monitored file")
    cmd = 'echo "ls" | tee -a {}'.format(dest_file)
    exitcode, msg = con_ssh.exec_cmd(cmd)
    assert exitcode == 0, "Failed to append to file"

    files_to_delete.append(dest_file)

    LOG.info("Execute file")
    exitcode, msg = con_ssh.exec_cmd("{}".format(dest_file))

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA event found"


# CHECK TEST PROCEDURE - FAILS in the middle
@mark.usefixtures("ima_precheck")
def _test_dynamic_library_change_via_ld_preload_envvar_assignment():
    """
    This test attempts to execute a signed/protected binary by pointing to a
    modified library via the LD_PRELOAD environment variable.  This should not
    result in an IMA violation.

    Test Steps:
    - Execute a signed/protected library binary via the LD_PRELOAD environment
      variable.
    - Confirm there is no IMA violation.

    This maps to TC_17664/T_16353 from US105523 (Dynamic library change via
    LD_PRELOAD assignment)

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """

    con_ssh = ControllerClient.get_active_controller()
    start_time = common.get_date_in_format()

    LOG.info("Make a copy of a library used by 'ls'")
    source_file = "/lib64/ld-linux-x86-64.so.2"
    dest_file = "/lib64/temp.so"
    copy_file(source_file, dest_file)

    ls_cmd = "/usr/bin/ls"

    LOG.info("Execute signed binary via LD_PRELOAD")
    exitcode, msg = con_ssh.exec_sudo_cmd("LD_PRELOAD={} ldd {}".format(dest_file, ls_cmd))
    # Getting seg fault

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA event found"

    delete_file(dest_file)


@mark.usefixtures("ima_precheck", "delete_files")
def test_file_attribute_changes_ima_detection():
    """
    This test confirms that the user can make file attribute changes without
    triggering IMA violations.  These changes include: chgrp, chown, chmod.

    Test Steps:
    - Modify group ownership of a file
    - Ensure an IMA event is not triggered
    - Modify permissions of a file
    - Ensure an IMA event is not triggered
    - Modify file ownership
    - Ensure an IMA event is not triggered

    This test maps to TC_17640/T_15806 from US105523 (File attribute changes
    are not detected by IMA)

    This test also covers TC_17665/T_16397 from US105523 (FM Event Log Updates)
    """

    global files_to_delete
    files_to_delete = []

    start_time = common.get_date_in_format()

    LOG.info("Copy monitored file")
    source_file = "/usr/sbin/ntpq"
    dest_file = "/usr/sbin/TEMP"
    copy_file(source_file, dest_file)

    LOG.info("Change permission of copy")
    chmod_file(dest_file, "777")

    files_to_delete.append(dest_file)

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA event found"

    LOG.info("Changing group ownership of file")
    chgrp_file(dest_file, "wrs")

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA event found"

    LOG.info("Changing file ownership")
    chown_file(dest_file, "wrsroot:wrs")

    LOG.info("Check for IMA event")
    events_found = system_helper.wait_for_events(start=start_time, timeout=60, num=10,
                                                 event_log_id=EventLogID.IMA,
                                                 state='log', severity='major',
                                                 fail_ok=True, strict=False)
    assert events_found == [], "Unexpected IMA event found"


@mark.usefixtures("ima_precheck")
def test_ima_keyring_user_attacks():
    """
    This test validates that the IMA keyring is safe from user space attacks.

    Test Steps:
    - Attempt to add new keys to the keyring
    - Extract key ID and save
    - Attempt to change the key timeout
    - Attempt to change the group and ownership of the key
    - Attempt to delete the key

    This test maps to TC_17667/T_16387 from US105523 (IMA keyring is safe from
    user space attacks)

    """

    con_ssh = ControllerClient.get_active_controller()

    LOG.info("Extract key ID")
    exitcode, msg = con_ssh.exec_sudo_cmd("cat /proc/keys")
    raw_key_id = msg.split(" ")[0]
    key_id = "0x{}".format(raw_key_id)
    LOG.info("Extracted key is: {}".format(key_id))

    LOG.info("Attempting to add new keys to keyring")
    exitcode, msg = con_ssh.exec_sudo_cmd("keyctl add keyring TEST stuff {}".format(key_id))
    assert exitcode != 0, "Key addition should have failed but instead succeeded"

    LOG.info("Attempt to change the timeout on a key")
    exitcode, msg = con_ssh.exec_sudo_cmd("keyctl timeout {} 3600".format(key_id))
    assert exitcode != 0, "Key timeout modification should be rejected but instead succeeded"

    LOG.info("Attempt to change the group of a key")
    exitcode, msg = con_ssh.exec_sudo_cmd("keyctl chgrp {} 0".format(key_id))
    assert exitcode != 0, "Key group modification should be rejected but instead succeeded"

    LOG.info("Attempt to change the ownership of a key")
    exitcode, msg = con_ssh.exec_sudo_cmd("keyctl chown {} 1875".format(key_id))
    assert exitcode != 0, "Key ownership modification should be rejected but instead succeeded"

    LOG.info("Attempt to delete a key")
    exitcode, msg = con_ssh.exec_sudo_cmd("keyctl clear {}".format(key_id))
    assert exitcode != 0, "Key ownership deletion should be rejected but instead succeeded"

