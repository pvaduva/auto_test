import getpass
import os
import re
import socket
import sys
import time
import threading

import pexpect

from consts.auth import TestFileServer
from consts.filepaths import BuildServerPath
from consts.proj_vars import ProjVar
from consts.stx import PING_LOSS_RATE
from utils import exceptions
from utils.clients.ssh import SSHClient
from utils.tis_log import LOG

LOCAL_HOST = socket.gethostname()
LOCAL_USER = getpass.getuser()
LOCAL_PROMPT = re.escape('{}@{}$ '.format(LOCAL_USER, LOCAL_HOST.split(sep='.wrs.com')[0])).replace(r'\$ ', r'.*\$')
COUNT = 0


def get_unique_name(name_str):
    global COUNT
    COUNT += 1
    return '{}-{}'.format(name_str, COUNT)


class LocalHostClient(SSHClient):
    def __init__(self, initial_prompt=None, timeout=60, session=None, searchwindowsisze=None, name=None, connect=False):
        """

        Args:
            initial_prompt
            timeout
            session
            searchwindowsisze
            connect (bool)

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

        if connect:
            self.connect()

    def connect(self, retry=False, retry_interval=3, retry_timeout=300, prompt=None,
                use_current=True, timeout=None):
        # Do nothing if current session is connected and force_close is False:
        if use_current and self.is_connected():
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
                LOG.debug("Attempt to connect to localhost - {}".format(self.host))
                self.session = pexpect.spawnu(command='bash', timeout=timeout, maxread=100000)

                self.logpath = self._get_logpath()
                if self.logpath:
                    self.session.logfile = open(self.logpath, 'w+')

                # Set prompt for matching
                self.set_prompt(prompt)
                self.send(r'export PS1="\u@\h\$ "')
                self.expect()
                LOG.debug("Connected to localhost!")
                return

            except (OSError, pexpect.TIMEOUT, pexpect.EOF):
                if not retry:
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
            new_prompt = r'\({}\) {}'.format(venv_name, self.get_prompt())
            self.set_prompt(prompt=new_prompt)
            LOG.info('virtualenv {} activated successfully'.format(venv_name))

        time.sleep(3)
        code, output = self.exec_cmd('pip -V')
        if code != 0:
            LOG.warning('pip is not working properly. Listing env variables.')
            all_env = self.exec_cmd('declare -p')[1]
            LOG.info("declare -p: \n{}".format(all_env))

    def deactivate_virtualenv(self, venv_name, new_prompt=None):
        # determine on the new prompt
        if not new_prompt:
            if venv_name in self.prompt:
                new_prompt = self.prompt.split(r'\({}\) '.format(venv_name))[-1]
            else:
                new_prompt = self.initial_prompt

        LOG.info("Deactivating virtualenv {}".format(venv_name))
        self.set_prompt(new_prompt)
        code, output = self.exec_cmd('deactivate', fail_ok=True)
        if code == 0 or 'command not found' in output:
            LOG.info('virtualenv {} deactivated successfully'.format(venv_name))
        else:
            raise exceptions.LocalHostError("Unable to deactivate venv. Output: {}".format(output))

    def get_ssh_key(self, ssh_key_path=None):
        if not ssh_key_path:
            ssh_key_path = os.path.expanduser('~/.ssh/id_rsa_cgcsauto')
        # KNOWN_HOSTS_PATH = SSH_DIR + "/known_hosts"
        # REMOVE_HOSTS_SSH_KEY_CMD = "ssh-keygen -f {} -R {}"
        if not self.file_exists(ssh_key_path):
            self.exec_cmd("ssh-keygen -f {} -t rsa -N ''".format(ssh_key_path), fail_ok=False)
        ssh_key = self.exec_cmd("ssh-keygen -y -f {} -P ''".format(ssh_key_path), fail_ok=False)

        return ssh_key

    def ping_server(self, server, ping_count=5, timeout=60, fail_ok=False, retry=0):
        """

        Args:
            server (str): server ip to ping
            ping_count (int):
            timeout (int): max time to wait for ping response in seconds
            fail_ok (bool): whether to raise exception if packet loss rate is 100%
            retry (int):

        Returns (int): packet loss percentile, such as 100, 0, 25

        """
        output = packet_loss_rate = None
        for i in range(max(retry+1, 1)):
            cmd = 'ping -c {} {}'.format(ping_count, server)
            code, output = self.exec_cmd(cmd=cmd, expect_timeout=timeout, fail_ok=True)
            if code != 0:
                packet_loss_rate = 100
            else:
                packet_loss_rate = re.findall(PING_LOSS_RATE, output)[-1]

            packet_loss_rate = int(packet_loss_rate)
            if packet_loss_rate < 100:
                if packet_loss_rate > 0:
                    LOG.warning("Some packets dropped when ping from {} ssh session to {}. Packet loss rate: {}%".
                                format(self.host, server, packet_loss_rate))
                else:
                    LOG.info("All packets received by {}".format(server))
                break

            LOG.info("retry in 3 seconds")
            time.sleep(3)
        else:
            msg = "Ping from {} to {} failed.".format(self.host, server)
            if not fail_ok:
                raise exceptions.LocalHostError(msg)
            else:
                LOG.warning(msg)

        untransmitted_packets = re.findall(r"(\d+) packets transmitted,", output)
        if untransmitted_packets:
            untransmitted_packets = int(ping_count) - int(untransmitted_packets[0])
        else:
            untransmitted_packets = ping_count

        return packet_loss_rate, untransmitted_packets


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
        idx = 0 if curr_thread is threading.main_thread() else int(curr_thread.name.split('-')[-1])
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
            build_info = ProjVar.get_var('BUILD_INFO')
            source_path = '{}/{}/{}/export/cgts-sdk/wrs-remote-clients-*.tgz'. \
                format(BuildServerPath.DEFAULT_WORK_SPACE, build_info.get('JOB', ''), build_info.get('BUILD_ID', ''))
            dest_dir = os.path.dirname(remote_cli_dir)
            dest_path = os.path.join(dest_dir, '{}.tgz'.format(dest_name))
            localclient.scp_on_dest(source_user=TestFileServer.get_user(), source_ip=build_info.get('BUILD_SERVER'),
                                    source_pswd=TestFileServer.get_password(),
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
            except Exception:
                # Do the cleanup in case of remote cli clients install failure.
                if not ProjVar.get_var('NO_TEARDOWN'):
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
