import getpass
import os
import re
import socket
import sys
import time
import threading

import pexpect

from consts.auth import SvcCgcsAuto
from consts.filepaths import BuildServerPath
from consts.proj_vars import ProjVar
from utils import exceptions
from utils.clients.ssh import SSHClient
from utils.tis_log import LOG

LOCAL_HOST = socket.gethostname()
LOCAL_USER = getpass.getuser()
LOCAL_PROMPT = re.escape('{}@{}$ '.format(LOCAL_USER, LOCAL_HOST))
COUNT = 0


def get_unique_name(name_str):
    global COUNT
    COUNT += 1
    return '{}-{}'.format(name_str, COUNT)


class LocalHostClient(SSHClient):
    def __init__(self, initial_prompt=None, timeout=60, session=None, searchwindowsisze=None, name=None):
        """

        Args:
            initial_prompt
            timeout
            session
            searchwindowsisze

        Returns:

        """
        if not initial_prompt:
            initial_prompt = LOCAL_PROMPT
        if not name:
            name = 'localclient'
        self.name = get_unique_name(name)
        super(LocalHostClient, self).__init__(host=LOCAL_HOST, user=LOCAL_USER, password=None, force_password=False,
                                              initial_prompt=initial_prompt, timeout=timeout, session=session,
                                              searchwindownsize=searchwindowsisze)

    def connect(self, retry=False, retry_interval=3, retry_timeout=300, prompt=None,
                use_current=True, timeout=None):
        # Do nothing if current session is connected and force_close is False:
        if use_current and self._is_connected():
            LOG.debug("Already connected to {}. Do nothing.".format(self.host))
            # LOG.debug("ID of the session: {}".format(id(self)))
            return

        # use original prompt instead of self.prompt when connecting in case of prompt change during a session
        if not prompt:
            prompt = self.initial_prompt
        if timeout is None:
            timeout = self.timeout

        # Connect to host
        end_time = time.time() + retry_timeout
        while time.time() < end_time:
            try:
                LOG.info("Attempt to connect to host - {}".format(self.host))
                self._session = pexpect.spawnu(command='bash', timeout=timeout, maxread=100000)

                self.logpath = self._get_logpath()
                if self.logpath:
                    self._session.logfile = open(self.logpath, 'w+')

                # Set prompt for matching
                self.set_prompt(prompt)
                self.send("PS1={}".format(prompt))
                self.expect()
                LOG.info("Login successful!")
                return

            except (OSError, pexpect.TIMEOUT, pexpect.EOF):
                # fail login if retry=False
                # LOG.debug("Reset session.after upon ssh error")
                # self._session.after = ''
                if not retry:
                    raise

            except:
                LOG.error("Failed to spawn pexpect object due to unknown exception!")
                raise

            self.close()
            LOG.debug("Retry in {} seconds".format(retry_interval))
            time.sleep(retry_interval)

        else:
            raise exceptions.LocalHostError("Unable to spawn pexpect object on {}. Expected prompt: {}".format(
                    self.host, self.prompt))

    def remove_virtualenv(self, venv_name=None, venv_dir=None, fail_ok=False, deactivate_first=True,
                          python_executable=None):

        if not python_executable:
            python_executable = sys.executable

        if not venv_name:
            venv_name = ProjVar.get_var('RELEASE')
        venv_dir = _get_virtualenv_dir(venv_dir)

        if deactivate_first:
            self.deactivate_virtualenv(venv_name=venv_name)

        LOG.info("Removing virtualenv {}/{}".format(venv_dir, venv_name))
        cmd = "export WORKON_HOME={}; export VIRTUALENVWRAPPER_PYTHON={}; source virtualenvwrapper.sh".\
            format(venv_dir, python_executable)
        code, output = self.exec_cmd(cmd=cmd, fail_ok=fail_ok)
        if code == 0:
            code = self.exec_cmd("rmvirtualenv {}".format(venv_name), fail_ok=fail_ok)[0]
            if code == 0:
                # Remove files generated by virtualwrapper
                for line in output.splitlines():
                    if 'user_scripts creating ' in line:
                        new_file = output.split('user_scripts creating ')[-1].strip()
                        self.exec_cmd('rm -f {}'.format(new_file))
                LOG.info('virtualenv {} removed successfully'.format(venv_name))
                return True

        return False

    def create_virtualenv(self, venv_name=None, venv_dir=None, activate=True, fail_ok=False, check_first=True,
                          python_executable=None):
        if not venv_name:
            venv_name = ProjVar.get_var('RELEASE')
        venv_dir = _get_virtualenv_dir(venv_dir)

        if check_first:
            if self.file_exists(os.path.join(venv_dir, venv_name, 'bin', 'activate')):
                if activate:
                    self.activate_virtualenv(venv_name=venv_name, venv_dir=venv_dir, fail_ok=fail_ok)
                return

        if not python_executable:
            python_executable = sys.executable

        LOG.info("Creating virtualenv {}/{}".format(venv_dir, venv_name))
        os.makedirs(venv_dir, exist_ok=True)
        cmd = "cd {}; virtualenv --python={} {}".format(venv_dir, python_executable, venv_name)
        code = self.exec_cmd(cmd=cmd, fail_ok=fail_ok)[0]
        if code == 0:
            LOG.info('virtualenv {} created successfully'.format(venv_name))
            if activate:
                self.activate_virtualenv(venv_name=venv_name, venv_dir=venv_dir, fail_ok=fail_ok)

        return venv_name, venv_dir, python_executable

    def activate_virtualenv(self, venv_name=None, venv_dir=None, fail_ok=False):
        if not venv_name:
            venv_name = ProjVar.get_var('RELEASE')
        venv_dir = _get_virtualenv_dir(venv_dir)
        assert os.path.exists(venv_dir)

        LOG.info("Activating virtualenv {}/{}".format(venv_dir, venv_name))
        code = self.exec_cmd('cd {}; source {}/bin/activate'.format(venv_dir, venv_name), fail_ok=fail_ok)[0]
        if code == 0:
            new_prompt = '\({}\) {}'.format(venv_name, self.get_prompt())
            self.set_prompt(prompt=new_prompt)
            LOG.info('virtualenv {} activated successfully'.format(venv_name))

    def deactivate_virtualenv(self, venv_name, new_prompt=None):
        # determine on the new prompt
        if not new_prompt:
            if venv_name in self.prompt:
                new_prompt = self.prompt.split('\({}\) '.format(venv_name))[-1]
            else:
                new_prompt = self.initial_prompt

        LOG.info("Deactivating virtualenv {}".format(venv_name))
        self.set_prompt(new_prompt)
        code, output = self.exec_cmd('deactivate', fail_ok=True)
        if code == 0 or 'command not found' in output:
            LOG.info('virtualenv {} deactivated successfully'.format(venv_name))
        else:
            raise exceptions.LocalHostError("Unable to deactivate venv. Output: {}".format(output))


def _get_virtualenv_dir(venv_dir=None):
    if not venv_dir:
        if ProjVar.get_var('LOG_DIR'):
            lab_logs_dir = os.path.dirname(ProjVar.get_var('LOG_DIR'))  # e.g., .../AUTOMATION_LOGS/ip_18_19/
            venv_dir = os.path.join(lab_logs_dir, '.virtualenvs')
        else:
            venv_dir = os.path.expanduser('~')
    return venv_dir


class RemoteCLIClient:
    """
    Note: this should only be used on test server due to sudo permission needed to install/uninstall remote cli clients.
    """
    REMOTE_CLI_FOLDER = 'wrs-remote-clients'
    __remote_cli_info = {'remote_cli_dir': None, 'venv_dir': None}
    __lab_remote_clients_map = {}

    @staticmethod
    def _get_python_executable(client):
        python_executable = client.exec_cmd('which /usr/bin/python2')[1]
        if not python_executable:
            python_executable = client.exec_cmd('which python2')[1]
            if not python_executable:
                raise ValueError('python2 is not installed on system. Please install python2 first.')
        return python_executable

    @classmethod
    def get_remote_cli_client(cls, lab_name=None, create_new=True):
        """
        Get a localhost client with remote cli clients installed in virtualenv
        Args:
            lab_name (str):  lab short_name
            create_new (bool): whether to return None or create new client when no existing client

        Returns:

        """
        if not lab_name:
            lab = ProjVar.get_var('LAB')
            lab_name = lab.get('short_name')
        lab_name = lab_name.lower()

        curr_thread = threading.current_thread()
        idx = 0 if isinstance(curr_thread, threading._MainThread) else int(curr_thread.name.split('-')[-1])
        local_clients_for_lab = cls.__lab_remote_clients_map.get(lab_name, [])
        if local_clients_for_lab:
            if len(local_clients_for_lab) > idx:
                LOG.debug("Getting remote cli client for {}".format(lab_name))
                remote_cli_client = cls.__lab_remote_clients_map[lab_name][idx]
                if isinstance(remote_cli_client, LocalHostClient):
                    return remote_cli_client
        else:
            cls.__lab_remote_clients_map[lab_name] = []

        if not create_new:
            return None

        # no existing client or name mismatch, create new client
        # venv shared for same lab. Assuming only one remote cli test session should be run on same lab.
        # remote cli install script should be able to auto remove the old clients if exist in the venv
        localclient = LocalHostClient()
        localclient.connect(use_current=False)

        dest_name = cls.REMOTE_CLI_FOLDER
        remote_cli_dir = cls.__remote_cli_info['remote_cli_dir']
        venv_dir = cls.__remote_cli_info['venv_dir']
        venv_name = ProjVar.get_var('RELEASE')
        if not remote_cli_dir:
            remote_cli_dir = '{}/{}'.format(ProjVar.get_var('LOG_DIR'), dest_name)
            LOG.info("SCP wrs-remote-clients sdk to localhost...")
            source_path = '{}/{}/{}/export/cgts-sdk/wrs-remote-clients-*.tgz'. \
                format(BuildServerPath.DEFAULT_WORK_SPACE, ProjVar.get_var('JOB'), ProjVar.get_var('BUILD_ID'))
            dest_dir = os.path.dirname(remote_cli_dir)
            dest_path = os.path.join(dest_dir, '{}.tgz'.format(dest_name))
            localclient.scp_on_dest(source_user=SvcCgcsAuto.USER, source_ip=ProjVar.get_var('BUILD_SERVER'),
                                    source_pswd=SvcCgcsAuto.PASSWORD,
                                    source_path=source_path,
                                    dest_path=dest_path, timeout=300)

            localclient.exec_cmd('cd {}; tar xvf {}.tgz'.format(dest_dir, dest_name), fail_ok=False)
            localclient.exec_cmd('rm -f {}'.format(dest_path))
            localclient.exec_cmd('mv {}* {}'.format(dest_name, dest_name))

            if not venv_dir:
                venv_dir = _get_virtualenv_dir()
                LOG.info("Creating and activating virtual environment...")
                python_executable = cls._get_python_executable(client=localclient)
                localclient.create_virtualenv(venv_name=venv_name, activate=True, venv_dir=venv_dir,
                                              python_executable=python_executable)
                cls.__remote_cli_info['venv_dir'] = venv_dir

            try:
                LOG.info("Installing remote cli clients in virtualenv...")
                localclient.exec_cmd('cd {}'.format(os.path.join(dest_dir, dest_name)), fail_ok=False)
                localclient.exec_cmd('./install_clients.sh', fail_ok=False, expect_timeout=600)
                cls.__remote_cli_info['remote_cli_dir'] = remote_cli_dir
            except:
                # Do the cleanup in case of remote cli clients install failure.
                cls.remove_remote_cli_clients(remote_cli_dir=remote_cli_dir, venv_dir=venv_dir)
                raise
        else:
            localclient.activate_virtualenv(venv_dir=venv_dir, venv_name=venv_name)

        LOG.info("Remote cli client opened successfully")
        if len(cls.__lab_remote_clients_map[lab_name]) < idx:
            # fill with copy of new ssh session until list is correct length
            # (only when a different lab or ip address has also been added)
            new_client = LocalHostClient()
            new_client.connect(use_current=False)
            while len(cls.__lab_remote_clients_map[lab_name]) < idx:
                cls.__lab_remote_clients_map[lab_name].append(new_client)
            cls.__lab_remote_clients_map[lab_name].append(localclient)
        else:
            cls.__lab_remote_clients_map[lab_name].append(localclient)

        return localclient

    @classmethod
    def remove_remote_cli_clients(cls, remote_cli_dir=None, venv_dir=None, lab_name=None):
        # if not clients:
        #     if not lab_name:
        #         lab = ProjVar.get_var('LAB')
        #         lab_name = lab.get('short_name')
        #     lab_name = lab_name.lower()
        #     clients = cls.__lab_remote_clients_map.get(lab_name, [])
        if not venv_dir:
            venv_dir = cls.__remote_cli_info['venv_dir']
        if not remote_cli_dir:
            remote_cli_dir = cls.__remote_cli_info['remote_cli_dir']

        # for client in clients:
        #     client.close()
        if lab_name:
            cls.__lab_remote_clients_map.pop(lab_name)

        if not venv_dir and not remote_cli_dir:
            LOG.info("No venv or remote_cli_clients to remove")
            return

        localclient = LocalHostClient()
        localclient.connect(use_current=False)
        try:
            if remote_cli_dir:
                # assume venv_dir must be set if remote_cli_dir is set
                localclient.activate_virtualenv(venv_dir=venv_dir)
                LOG.info("Uninstall remote cli clients in virtualenv...")
                localclient.exec_cmd('cd {}'.format(remote_cli_dir), fail_ok=False)
                localclient.exec_cmd('./uninstall_clients.sh', fail_ok=False, expect_timeout=600)
                LOG.info("Remote cli clients successfully uninstalled")
        finally:
            # Remove virtualenv and non-txt files in remote cli directory to save disk space on localhost
            LOG.info("Cleanup remote client files")
            localclient.exec_cmd('rm -rf $(ls -I "*.log")')
            cls.__remote_cli_info['remote_cli_dir'] = None
            if venv_dir:
                python_executable = cls._get_python_executable(client=localclient)
                localclient.remove_virtualenv(venv_dir=venv_dir, python_executable=python_executable,
                                              deactivate_first=True)
                cls.__remote_cli_info['venv_dir'] = None
            localclient.close()
