import datetime
import os.path
import random
import re
import threading
import time

from pytest import mark, fixture, skip

from consts.cgcs import MULTI_REGION_MAP
from consts.auth import HostLinuxCreds
from consts.proj_vars import ProjVar
from consts.timeout import HostTimeout
from keywords import mtc_helper, system_helper, host_helper
from utils import cli, table_parser
from utils.clients.ssh import SSHClient, ControllerClient
from utils.tis_log import LOG

_tested_procs = []
_final_processes_status = {}

DEF_RETRIES = 2
DEF_DEBOUNCE = 20
DEF_INTERVAL = 10
DEGRADED_TO_AVAILABLE_TIMEOUT = 150
SM_PROC_TIMEOUT = 90
KILL_WAIT_RETRIES = 30

DEF_PROCESS_RESTART_CMD = r'/etc/init.d/{} restart'
DEF_PROCESS_PID_FILE_PATH = r'/var/run/{}.pid'

INTERVAL_BETWEEN_SWACT = 300 + 10

IS_SIMPLEX = system_helper.is_simplex()

SKIP_PROCESS_LIST = ['postgres', 'open-ldap', 'lighttpd', 'ceph-rest-api', 'horizon', 'patch-alarm-manager', 'ntpd']

if IS_SIMPLEX:
    SKIP_PROCESS_LIST.append('haproxy')

PROCESSES = {
    'sm': {
        'cmd': 'sm', 'impact': 'disabled-failed', 'severity': 'critical', 'process_type': 'pmon',
        'node_type': 'controller'},

    'rmond': {
        'cmd': 'rmon', 'impact': 'enabled-degraded', 'severity': 'major',
        'interval': 10, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/rmon.conf'},

    'kubelet': {
        'cmd': 'kubelet', 'impact': 'enabled-degraded', 'severity': 'critical','debounce': 20,
        'interval': 5, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/kubelet.conf'},

    'docker': {
        'cmd': 'docker', 'impact': 'enabled-degraded', 'severity': 'critical','debounce': 20,
        'interval': 5, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/docker.conf'},

    'fsmond': {
        'cmd': 'fsmon', 'impact': 'enabled-degraded', 'severity': 'major',
        'interval': 5, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/fsmon.conf'},

    'hbsClient': {
        'cmd': 'hbsClient', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 3,
        'interval': 1, 'process_type': 'pmon'},

    'mtcClient': {
        'cmd': 'mtcClient', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 3,
        'interval': 1, 'process_type': 'pmon'},

    'mtcalarmd': {
        'cmd': 'mtcalarmd', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 3,
        'interval': 1, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/mtcalarm.conf'},

    'sm-api': {'cmd': 'sm-api', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
               'interval': 5, 'process_type': 'pmon', 'node_type': 'controller'},

    'sm-watchdog': {
        'cmd': 'sm-watchdog', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'process_type': 'pmon', 'node_type': 'controller'},

    'sysinv-agent': {
        'cmd': 'sysinv-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'process_type': 'pmon'},

    'sw-patch-controller-daemon': {
        'cmd': 'sw-patch-controller-daemon', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'process_type': 'pmon', 'node_type': 'controller'},

    'sw-patch-agent': {
        'cmd': 'sw-patch-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'process_type': 'pmon'},

    'acpid': {
        'cmd': 'acpid', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 5, 'retries': 10, 'process_type': 'pmon'},

    'ceilometer-polling': {
        'cmd': '/usr/bin/python2 /usr/bin/ceilometer-polling', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 10, 'retries': 5, 'process_type': 'pmon'},

    'mtclogd': {
        'cmd': 'mtclogd', 'impact': 'log', 'severity': 'minor', 'debounce': 3,
        'interval': 1, 'retries': 3, 'process_type': 'pmon'},

    'ntpd': {
        'cmd': 'ntpd', 'impact': 'log', 'severity': 'minor', 'debounce': 0,
        'interval': 0, 'retries': 0, 'process_type': 'pmon'},

    'sm-eru': {
        'cmd': 'sm-eru', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 5, 'retries': 3, 'process_type': 'pmon'},

    'sshd': {
        'cmd': 'sshd', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 5, 'retries': 10, 'process_type': 'pmon'},

    # Note: name differs from cmd
    'syslog-ng': {
        'cmd': 'syslog', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 10, 'retries': 10, 'process_type': 'pmon', 'override': True},

    'io-monitor-manager': {
        'cmd': 'io-monitor-manager', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 10, 'retries': 5, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/io-monitor.conf',
        'node_type': 'controller'},

    'logmgmt': {
        'cmd': 'logmgmt', 'impact': 'log', 'severity': 'minor', 'debounce': 20,
        'interval': 5, 'retries': 5, 'process_type': 'pmon', 'conf_file': '/etc/pmon.d/logmgmt'},

    # compute-only processes
    'guestServer': {
        'cmd': 'guestServer', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 10,
        'interval': 3, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'host_agent': {
        'cmd': 'guestServer', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 1, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'libvirtd': {
        'cmd': 'libvirtd', 'impact': 'disabled-failed', 'severity': 'critical', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'neutron-avr-agent': {
        'cmd': 'neutron-avr-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'neutron-avs-agent': {
        'cmd': 'neutron-avs-agent', 'impact': 'disabled-failed', 'severity': 'critical', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'neutron-dhcp-agent': {
        'cmd': 'neutron-dhcp-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'neutron-metadata-agent': {
        'cmd': 'neutron-metadata-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'neutron-sriov-nic-agent': {
        'cmd': 'neutron-sriov-nic-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    # Note: name differs from cmd
    'nova-compute': {
        'cmd': 'nova-startup', 'impact': 'disabled-failed', 'severity': 'critical', 'debounce': 20,
        'interval': 5, 'retries': 3, 'node_type': 'compute', 'process_type': 'pmon'},

    'vswitch': {
        'cmd': 'vswitch', 'impact': 'disabled-failed', 'severity': 'critical', 'debounce': 20,
        'interval': 3, 'retries': 0, 'node_type': 'compute', 'process_type': 'pmon'},

    # the following are SM managed services
    # active-controller only processes
    'postgres': {
        'cmd': '/usr/bin/postgres', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    # {'rabbitmq-server': {
    # rabbit in sm-dump
    'rabbit': {
        'cmd': '/usr/lib/rabbitmq/bin/rabbitmq-server', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # {'sysinv-api': {
    # sysinv-inv in sm-dump
    'sysinv-inv': {
        'cmd': '/usr/bin/python /bin/sysinv-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'sysinv-conductor': {
        'cmd': '/usr/bin/python /bin/sysinv-conductor', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # {'mtcAgent': {
    'mtc-agent': {
        'cmd': '/usr/local/bin/mtcAgent', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    # {'hbsAgent': {
    'hbs-agent': {
        'cmd': '/usr/local/bin/hbsAgent', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    # {'hwmond': {
    'hw-mon': {
        'cmd': '/usr/local/bin/hwmond', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    'dnsmasq': {
        'cmd': '/usr/sbin/dnsmasq', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    # {'fmManager': {
    'fm-mgr': {
        'cmd': '/usr/local/bin/fmManager', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    # {'keystone-all': {
    'keystone': {
        'cmd': '/usr/bin/python2 /bin/keystone-all', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    'glance-registry': {
        'cmd': '/usr/bin/python2 /bin/glance-registry', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'glance-api': {
        'cmd': '/usr/bin/python2 /bin/glance-api', 'impact': 'swact',
        'severity': 'major', 'node_type': 'active'},

    'neutron-server': {
        'cmd': '/usr/bin/python2 /bin/neutron-server', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'nova-api': {
        'cmd': '/usr/bin/python2 /bin/nova-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'nova-scheduler': {
        'cmd': '/usr/bin/python2 /bin/nova-scheduler', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'nova-conductor': {
        'cmd': '/usr/bin/python2 /bin/nova-conductor', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # 'nova-cert': {
    #     'cmd': '/usr/bin/python2 /bin/nova-cert', 'impact': 'swact',
    #     'severity': 'critical', 'node_type': 'active'},

    # {'nova-consoleauth': {
    'nova-console-auth': {
        'cmd': '/usr/bin/python2 /bin/nova-consoleaut', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # {'nova-novncproxy': {
    'nova-novnc': {
        'cmd': '/usr/bin/python2 /bin/nova-novncproxy', 'impact': 'enabled-warning',
        'severity': 'major', 'node_type': 'active'},

    'cinder-api': {
        'cmd': '/usr/bin/python2 /bin/cinder-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'cinder-scheduler': {
        'cmd': '/usr/bin/python2 /bin/cinder-scheduler', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'cinder-volume': {
        'cmd': '/usr/bin/python2 /bin/cinder-volume', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active', 'retries': 32},

    # 'ceilometer-collector': {
    #     'cmd': '/usr/bin/python2 /bin/ceilometer-collector', 'impact': 'swact',
    #     'severity': 'critical', 'node_type': 'active'},

    # 'ceilometer-api': {
    #     'cmd': '/usr/bin/python2 /bin/ceilometer-api', 'impact': 'swact',
    #     'severity': 'critical', 'node_type': 'active'},

    'gnocchi-metricd': {
        'cmd': '/usr/bin/python2 /bin/gnocchi-metricd', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'ceilometer-collector': {
        'cmd': '/usr/bin/python2 /bin/ceilometer-collector', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'gnocchi-api': {
        'cmd': '/usr/bin/python2 /bin/gnocchi-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'ceilometer-agent-notification': {
        'cmd': '/usr/bin/python2 /bin/ceilometer-agent-notification', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'heat-engine': {
        'cmd': '/usr/bin/python2 /bin/heat-engine', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'heat-api': {
        'cmd': '/usr/bin/python2 /bin/heat-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'heat-api-cfn': {
        'cmd': '/usr/bin/python2 /bin/heat-api-cfn', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'heat-api-cloudwatch': {
        'cmd': '/usr/bin/python2 /bin/heat-api-cloudwatch', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # {'slapd': {
    'open-ldap': {
        'cmd': '/usr/sbin/slapd', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},

    # {'snmpd': {
    # note: retries for snmp is 32
    'snmp': {
        'cmd': '/usr/sbin/snmpd', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active', 'retries': 32},

    'lighttpd': {
        'cmd': '/usr/sbin/lighttpd', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # non-sm process
    # 'gunicorn': {
    'horizon': {
        'cmd': '/usr/bin/gunicorn', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'patch-alarm-manager': {
        'cmd': 'python /usr/bin/patch-alarm-manager start', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # on active-controller of a storage-lab
    'ceph-rest-api': {
        'cmd': 'python /usr/bin/ceph-rest-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active', 'lab_type': 'storage'},

    'ceph-manager': {
        'cmd': 'python /usr/bin/ceph-manager', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active', 'lab_type': 'storage'},

    # {'nfv-vim-api': {
    'vim-api': {
        'cmd': '/usr/bin/python /bin/nfv-vim-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'vim': {
        'cmd': '/usr/bin/python /bin/nfv-vim', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    # {'nfv-vim-webserver': {
    'vim-webserver': {
        'cmd': '/usr/bin/python /bin/nfv-vim-webserver', 'impact': 'enabled-warning',
        'severity': 'minor', 'node_type': 'active'},

    'guest-agent': {
        'cmd': '/usr/local/bin/guestAgent', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'nova-api-proxy': {
        'cmd': '/usr/bin/python /usr/bin/nova-api-proxy', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active', 'retries': 2, 'interval': 10},

    'haproxy': {
        'cmd': '/usr/sbin/haproxy', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'aodh-api': {
        'cmd': '/usr/bin/python2 /bin/aodh-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'aodh-evaluator': {
        'cmd': '/usr/bin/python2 /bin/aodh-evaluator', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'aodh-listener': {
        'cmd': '/usr/bin/python2 /bin/aodh-listener', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},

    'aodh-notifier': {
        'cmd': '/usr/bin/python2 /bin/aodh-listener', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
}


class MonitoredProcess:

    def __init__(self, name, cmd=None, impact=None, severity='major', node_type='all', **kwargs):
        self.name = name

        self.cmd = cmd
        self.impact = impact
        self.severity = severity
        self.node_type = node_type

        self.pid_file = kwargs.get('pid_file', None)

        self.retries = int(kwargs.get('retries', DEF_RETRIES))
        self.debounce = int(kwargs.get('debounce', DEF_DEBOUNCE))
        self.interval = int(kwargs.get('interval', DEF_INTERVAL))
        self.process_type = kwargs.get('process_type', 'sm')
        self.host = kwargs.get('host', 'controller-0')

        self.lab_type = kwargs.get('lab_type', 'any')
        self.conf_file = kwargs.get('conf_file', None)
        self.override = kwargs.get('override', False)

        self.prev_stats = None
        self.con_ssh = ControllerClient.get_active_controller()

        if IS_SIMPLEX:
            if self.impact == 'swact':
                self.impact = 'enabled-degraded'
            if self.node_type == 'controller':
                self.node_type = 'active'

        if cmd:
            main_cmd = cmd.split()[0]

            if main_cmd == self.cmd and not os.path.abspath(self.cmd):
                self.cmd = DEF_PROCESS_RESTART_CMD.format(cmd)

        if self.pid_file is None:
            self.pid_file = DEF_PROCESS_PID_FILE_PATH.format(self.name)

        elif not os.path.abspath(self.pid_file):
            self.pid_file = DEF_PROCESS_PID_FILE_PATH.format(os.path.splitext(os.path.basename(self.pid_file))[0])

        self.update_process_info()

        self.check_process_settings()

    def check_process_settings(self):
        LOG.debug('retries:{}, debounce:{}, interval:{}, process_type:{}, \npid_file:{}'.format(
            self.retries, self.debounce, self.interval, self.process_type, self.pid_file))
        pass

    def is_supported_lab(self):
        lab_type = self.lab_type
        if lab_type in ('any', ):
            return True

        elif lab_type in ('storage', ):
            return len(system_helper.get_storage_nodes(con_ssh=self.con_ssh)) > 0

        return True

    def update_process_info(self):
        self.host = self.select_host_to_test_on()[0]

        if self.process_type == 'sm':
            pid = -1
            process_info = None
            for _ in range(3):
                process_info = tuple(mtc_helper.get_process_from_sm(self.name, con_ssh=self.con_ssh))
                pid = process_info[0]
                if pid != -1 and len(process_info) != 5:
                    break

            if pid != -1 and len(process_info) == 5:
                self.pid = process_info[0]
                self.name = process_info[1]
                if self.severity != process_info[2]:
                    LOG.warn('Severity differs from sm-dump, expected:{}, from-sm-dump:{} for process:{}'.format(
                        self.severity, process_info[2], self.name))
                    LOG.warn('Use Severity from sm-dump instead, severity:{}, process:{}'.format(
                        process_info[2], self.name))
                    self.severity = process_info[2]

                self.proc_status = process_info[3]
                self.sm_pid_file = process_info[4]
            else:
                LOG.error('Failed to get process information from sm-dump for process:{}, got:{}'.format(
                    self.name, process_info))

        elif self.process_type == 'pmon':
            self.process = self.name
            settings = mtc_helper.get_pmon_process_info(self.name, self.host, self.conf_file, con_ssh=self.con_ssh)
            if not settings:
                LOG.warn('Cannot read conf file for process:{} on host:{}, conf-file {} does not exist?'.format(
                    self.name, self.host, self.con_ssh))
                skip('Cannot read conf file for process:{} on host:{}, conf-file {} does not exist?'.format(
                    self.name, self.host, self.con_ssh))

            for attr in ('process', 'severity', 'interval', 'debounce'):
                if attr in settings and settings[attr] != getattr(self, attr, None):
                    LOG.warn('{}:{} from conf-file:{} differs from expected:{}'.format(
                        attr, settings[attr], self.conf_file, getattr(self, attr, None)))

            for k, v in settings.items():
                setattr(self, k, v)

            # if 'restarts' in settings and not self.override:
            if 'restarts' in settings:
                self.retries = int(settings['restarts'].strip())
                LOG.debug('retries (Not override):{}'.format(self.retries))
            else:
                self.retries = getattr(self, 'retries', None)
                if self.retries is None:
                    self.retries = 3
                LOG.debug('retries:{}'.format(self.retries))

            self.interval = getattr(self, 'interval', None)
            if self.interval is None:
                self.interval = 10
            else:
                self.interval = int(self.interval)

            self.debounce = getattr(self, 'debounce', None)
            if self.debounce is None:
                self.debounce = 20
            else:
                self.debounce = int(self.debounce)
            if self.debounce < 1:
                msg = 'Debounce time is too small! Skip the test! debounce=<{}>'.format(self.debounce)
                LOG.warn(msg)
                skip(msg)

            if 'pidfile' in settings:
                self.pid_file = settings['pidfile']
        else:
            LOG.error('Process-type:{} is not supported yet'.format(self.process_type))

    def select_host_to_test_on(self):
        active_controller, standby_controller = system_helper.get_active_standby_controllers()
        self.active_controller = active_controller
        self.standby_controller = standby_controller

        if self.node_type == 'active':
            self.host = active_controller
            LOG.info('Choose the active-controller:{} to test on, node-type:{}'.format(self.host, self.node_type))

        elif self.node_type == 'controller':
            self.host = standby_controller
            LOG.info('Choose the standby-controller:{} to test on, node-type:{}'.format(self.host, self.node_type))

        elif self.node_type in ('compute', 'all'):
            if IS_SIMPLEX:
                self.host = active_controller
                LOG.info("Choose controller-0 for simplex system")
            else:
                computes = host_helper.get_hypervisors()
                self.host = random.choice([h for h in computes if h != active_controller])
                LOG.info('Choose a non-active hypervisor:{} to test on, node-type:{}'.format(self.host, self.node_type))

        else:
            # should never reach here
            LOG.info('Unknow node_type:{}'.format(self.node_type))
            assert False, 'Unknow node-type:{}, fail the test case'.format(self.node_type)

        if not self.host:
            skip('Cannot find a host to test on?, skip the test')

        return self.host, self.node_type, self.active_controller

    @staticmethod
    def matched_pmon_event_reason(reason, reason_pattern, host, process, severity):
        m = re.match(reason_pattern, reason)

        if not m:
            LOG.warn('Reason text of event not matching.')
            return {}

        if severity == 'minor':
            if len(m.groups()) != 3:
                LOG.debug('Reason format not matching, expecting 3 matching, but got:{}'.format(len(m.groups())))
                return {}

            matched_host, matched_process, matched_status = m.groups()
            if matched_host != host:
                LOG.debug('Reason HOST not matching, expecting {} but in-event:{}, pattern:{}, reason-text'.format(
                    host, matched_host, reason_pattern, reason))
                return {}

            if matched_process != process:
                LOG.debug('Reason Process not matching, expecting {} but in-event:{}, pattern:{}, '
                          'reason-text:{}'.format(process, matched_process, reason_pattern, reason))
                return {}

            status = 'failed'
            if matched_status != status:
                LOG.debug('Reason Status not matching, expecting {} but in-event:{}, pattern:{}, reason-text:{}'.format(
                    status, matched_status, reason_pattern, reason))
                return {}

            return dict(zip(('host', 'service', 'status'), m.groups()))

        elif severity == 'major':
            if len(m.groups()) != 4:
                LOG.debug('Reason format not matching, expecting 4 matching, but got:{}'.format(len(m.groups())))
                return {}

            matched_host, matched_status, matched_process, matched_severity = m.groups()
            if matched_host != host:
                LOG.debug('Reason Process not matching, expecting {} but in-event:{}, pattern:{}, '
                          'reason-text:{}'.format(process, matched_process, reason_pattern, reason))
                return {}

            status = 'degraded'
            if matched_status != status:
                LOG.debug('Reason Status not matching, expecting {} but in-event:{}, pattern:{}, '
                          'reason-text:{}'.format(status, matched_status, reason_pattern, reason))
                return {}

            if matched_process != process:
                LOG.debug('Reason Process not matching, expecting {} but in-event:{}, pattern:{}, '
                          'reason-text:{}'.format(process, matched_process, reason_pattern, reason))
                return {}

            if matched_severity != severity:
                LOG.debug('Reason SEVERITY not matching, expecting {} but in-event:{}, pattern:{}, '
                          'reason-text:{}'.format(severity, matched_severity, reason_pattern, reason))
                return {}

            return dict(zip(('host', 'status', 'service', 'severity'), m.groups()))

        elif severity == 'critical':
            if len(m.groups()) != 4:
                return {}

            matched_host, matched_severity, matched_process, matched_status = m.groups()

            if matched_host != host:
                return {}

            if matched_severity != severity:
                return {}

            if matched_process != process:
                return {}

            if matched_status != 'failed':
                return {}

            return dict(zip(('host', 'severity', 'service', 'status'), m.groups()))

        else:
            LOG.error('unknown PMON SERVERIY:{}'.format(severity))

        return {}

    def matched_pmon_event(self, process, event, host, process_type, severity, impact='', headers=None):
        event_log_id = mtc_helper.KILL_PROC_EVENT_FORMAT[process_type]['event_id']
        reason_pattern, entity_id_pattern = mtc_helper.KILL_PROC_EVENT_FORMAT[process_type][severity][0:2]

        matched_event = {}
        event_log_id_index = list(headers).index('Event Log ID')
        state_index = headers.index('State')
        severity_index = headers.index('Severity')
        reason_index = headers.index('Reason Text')
        uuid_index = headers.index('UUID')

        try:
            actual_event_id = event[event_log_id_index].strip()
            if actual_event_id != event_log_id:
                LOG.debug('Event ID not matching: expected ID:{}, in-event:{}, event:{}'.format(
                    event_log_id, actual_event_id, event))
                return {}

            actual_state = event[state_index]
            if actual_state not in ('set', 'clear'):
                LOG.debug('Event State not set/clear: state in-event:{}, event:{}'.format(
                    actual_state, event))
                return {}

            actual_severity = event[severity_index].strip()
            if actual_severity != severity:
                LOG.debug('Event Severity not matching: expected severity:{} in-event:{}, event:{}'.format(
                    severity, actual_severity, event))
                return {}

            matched = self.matched_pmon_event_reason(event[reason_index].strip(), reason_pattern, host,
                                                     process, severity)
            if not matched:
                LOG.debug('Event Reason not matching: event:{}'.format(event))
                return {}

            matched_event.update(dict(
                uuid=event[uuid_index],
                event=event,
                severity=actual_severity
            ))
            matched_event.update(matched)

        except IndexError:
            LOG.warn('ill-formated event:{}, process:{}, host:{}, process_type:{}, severity:{}, impact:{}'.format(
                event, process, host, process_type, severity, impact))
            return {}

        return matched_event

    def wait_for_pmon_process_events(self, service, host, target_status, expecting=True, severity='major',
                                     last_events=None, process_type='pmon', timeout=60, interval=3, con_ssh=None):

        if process_type not in mtc_helper.KILL_PROC_EVENT_FORMAT:
            LOG.error('unknown type of process:{}'.format(process_type))

        event_log_id = mtc_helper.KILL_PROC_EVENT_FORMAT[process_type]['event_id']
        reason_pattern, entity_id_pattern = mtc_helper.KILL_PROC_EVENT_FORMAT[process_type][severity][0:2]

        start_time = None
        if last_events and last_events.get('values', None):
            start_time = table_parser.get_column(last_events, 'Time Stamp')[0]

        search_keys = {
            'Event Log ID': event_log_id,
            'Reason Text': reason_pattern,
            'Entity Instance ID': entity_id_pattern,
        }

        matched_events = []
        stop_time = time.time() + timeout
        retry = 0
        while time.time() < stop_time:
            retry += 1
            if matched_events:
                matched_events[:] = []
            events_table = system_helper.get_events_table(
                show_uuid=True, event_log_id=event_log_id,
                start=start_time, limit=10, con_ssh=con_ssh, regex=True, **search_keys)

            if not events_table or not events_table['values']:
                LOG.warn('run{:02d} for process:{}: Empty event table?!\nevens_table:{}\nevent_id={}, '
                         'start={}\nkeys={}, severify={}'.format(retry, service, events_table, event_log_id,
                                                                 start_time, search_keys, severity))
                continue

            headers = events_table['headers']
            state_index = headers.index('State')
            for event in events_table['values']:
                matched_event = self.matched_pmon_event(service, event, host, process_type, severity, headers=headers)
                if not matched_event:
                    continue

                matched_events.append(matched_event)

                if len(matched_events) > 1:
                    if matched_events[0]['event'][state_index] == 'clear' and \
                            matched_events[1]['event'][state_index] == 'set':
                        LOG.info('OK, found matched events:{}'.format(matched_events))
                        return 0, tuple(matched_events)
                        # return True, tuple(matched_events)
                    else:
                        LOG.debug('State is not "clear",\n{}'.format(event))
                        LOG.debug('matched-events:\n\n{}\n\n'.format(matched_events))

            if len(matched_events) == 1:
                LOG.warn('Only 1 event recorded? matched_event:\n{}\n'.format(matched_events[0]))
                if service in ('ntpd', ):
                    event = matched_events[0]['event']
                    if event[state_index] == 'set':
                        LOG.warn('Treat NTP specially, pass since it is set')
                        return 0, tuple(matched_events)

            LOG.warn('No matched event found at try:{}, will sleep {} seconds and retry'
                     '\nmatched events:\n{}, host={}, expected status={}, expecting={}'.
                     format(retry, interval, matched_events, host, target_status, expecting))

            time.sleep(interval)

            continue

        LOG.info('No matched events:\n{}'.format(matched_events))

        return -1, ()

    def kill_pmon_process_and_verify_impact(self, name, impact, process_type, host, severity='major', pid_file='',
                                            retries=2, interval=1, debounce=20, wait_recover=True, con_ssh=None):
        LOG.debug('Kill process and verify system behavior for PMON process:{}, impact={}, process_type={}'.format(
            name, impact, process_type))
        last_events = system_helper.get_events_table(
            event_log_id=mtc_helper.KILL_PROC_EVENT_FORMAT[process_type]['event_id'],
            limit=2, con_ssh=con_ssh)
        if not pid_file:
            LOG.error('No pid-file provided')
            return -1

        if 0 <= interval <= debounce:
            # wait_after_each_kill = max(random.randint(interval, debounce - 1), 1)
            wait_after_each_kill = debounce
        else:
            msg = 'Debounce time period is smaller than interval? Error in configuration. Skip the test! ' \
                  'interval={} debounce={}'.format(interval, debounce)
            LOG.warn(msg)
            skip(msg)
            return -1

        quorum = int(getattr(self, 'quorum', 0))
        if quorum > 0:
            retries += 1
            mode = getattr(self, 'mode', 'passive')
            if 'active' == mode:
                wait_after_each_kill += 5

        # have to kill 1 more time for mtcClient
        retries += 2

        LOG.info('retries={}, interval={}, debounce={}, wait_each_kill={}'.format(
            retries, interval, debounce, wait_after_each_kill))

        cmd = '''true; n=1; last_pid=''; pid=''; for((;n<{};)); do pid=\$(cat {} 2>/dev/null); date;
                if [ "x\$pid" = "x" -o "\$pid" = "\$last_pid" ]; then echo "stale or empty PID:\$pid, last_pid=\$last_pid";
                sleep 0.5; continue; fi; echo "{}" | sudo -S kill -9 \$pid &>/dev/null;
                if [ \$? -eq 0 ]; then echo "OK \$n - \$pid killed"; ((n++)); last_pid=\$pid; pid=''; sleep {};
                else sleep 0.5; fi; done; echo \$pid'''.format(
                    retries, pid_file, HostLinuxCreds.get_password(), wait_after_each_kill)

        LOG.info('Attempt to kill process:{} on host:{}, cli:\n{}\n'.format(name, host, cmd))
        cmd_2 = 'cat >/home/wrsroot/test_process.sh  <<EOL\n{}\nEOL'.format(cmd)

        wait_time = max(wait_after_each_kill * retries + 60, 60)

        self.pid = -1
        for _ in range(2):
            try:
                with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con:

                    con.exec_cmd(cmd_2)
                    con.exec_cmd("chmod 755 ./test_process.sh")

                    full_cmd = "nohup ./test_process.sh > ./results.txt 2>&1 &"

                    code, output = con.exec_cmd(full_cmd, fail_ok=True, expect_timeout=wait_time)
                    # code, output = con.exec_sudo_cmd( full_cmd, fail_ok=True, expect_timeout=wait_time)
                    if 0 != code:
                        LOG.warn('Failed to kill process:{} on host:{}, cli:\n{}\noutput:\n{}'.format(
                            name, host, cmd, output))
                        time.sleep(debounce)
                        continue
                    if output:
                        LOG.info('Last PID of PMON process is:{}, process:{}'.format(output, name))
                        # self.pid = int(output)
            except Exception as e:
                LOG.warn('Caught exception when running:{}, exception:{}, '
                         'but assuming the process {} was killed'.format(cmd, e, name))

            check_event = True
            quorum = 0
            expected = {'operational': 'enabled', 'availability': 'available'}

            wait_time_for_host_status = 90

            if impact in ('log',):
                check_event = True

            elif impact in ('enabled-degraded', 'disabled-failed'):
                quorum = getattr(self, 'quorum', None)
                
                if quorum == '1':
                    LOG.warn('Killing quorum process:{}, the impacted node should reboot'.format(name))
                    wait_time_for_host_status = HostTimeout.REBOOT
                    expected = {'operational': 'Disabled', 'availability': 'Offline'}

                elif impact in ('disabled-failed',):
                    LOG.debug('wait host getting into status:disabled-failed')
                    wait_time_for_host_status = HostTimeout.REBOOT
                    expected = {'operational': 'Disabled', 'availability': ['Failed', 'Offline']}
                    # check_event = True

                elif impact in ('enabled-degraded',):
                    wait_time_for_host_status = 90

                    expected = {'operational': 'Enabled', 'availability': 'Degraded'}
                    check_event = True
            else:
                LOG.error('unknown IMPACT:{}'.format(impact))
                assert False, 'Unknown IMPACT:{}'.format(impact)

            sleep_time = (retries + 1) * wait_after_each_kill
            if IS_SIMPLEX and expected['operational'] == 'Disabled':
                LOG.info("Simplex system - check ssh disconnected")
                reached = host_helper.wait_for_ssh_disconnect(fail_ok=True, timeout=sleep_time + 300)

                if reached:
                    host_helper.recover_simplex(fail_ok=True)

            else:

                LOG.info("Sleep for some time after each kill: {}".format(sleep_time))
                time.sleep(sleep_time)

                LOG.info("After process:{} been killed {} times, wait for {} to reach: {}".format(name, retries,
                                                                                                  host, expected))
                reached = host_helper.wait_for_host_values(host, timeout=wait_time_for_host_status, con_ssh=con_ssh,
                                                           fail_ok=True, **expected)

            if not reached:
                LOG.warn('Host:{} failed to get into status:{} after process:{} been killed {} times'.format(
                    host, expected, name, retries))

            found_event = False
            if check_event:
                code, events = self.wait_for_pmon_process_events(
                    name, host, expected, process_type=process_type, severity=severity,
                    last_events=last_events, expecting=True, con_ssh=con_ssh)

                if 0 != code:
                    LOG.error('No event/alarm raised for process:{}, process_type:{}, host:{}'.format(
                        name, process_type, host))
                else:
                    found_event = True
                    LOG.info('found events {} after been killed {} times on host {}'.format(events, retries, host))

            if not reached and not found_event:
                LOG.error('host {} did not reach expected status:{} after been killed {} times on host {}, '
                          'and there is no relevant alarms/events found neither'.format(host, expected, name, retries))
            else:
                if wait_recover:
                    operational = impact.split('-')[0]
                    if operational == 'disabled' or quorum == '1':
                        wait_time = HostTimeout.REBOOT + DEGRADED_TO_AVAILABLE_TIMEOUT
                    else:
                        wait_time += 60

                    expected = {'operational': 'enabled', 'availability': 'available'}
                    reached = host_helper.wait_for_host_values(
                        host, timeout=wait_time, con_ssh=con_ssh, fail_ok=True, **expected)
                    if not reached:
                        LOG.error('host {} did not recoverd to enabled-available status from status:{} '
                                  'after been killed {} times'.format(host, expected, retries))
                        return -1

                if check_event:
                    code, events = self.wait_for_pmon_process_events(
                        name, host, expected, process_type=process_type, severity=severity,
                        last_events=last_events, expecting=True, con_ssh=con_ssh)

                    if 0 != code:
                        LOG.error('No event/alarm raised for process:{}, process_type:{}, host:{}'.format(
                            name, process_type, host))
                    else:
                        found_event = True
                        LOG.info('found events {} after been killed {} times on host {}'.format(events, retries, host))

                if reached and not found_event:
                    LOG.error('No event/alarm raised for process:{}, process_type:{}, host:{}, '
                              'although host reached expected status:{}'.format(name, process_type, host, expected))
                    return -1

                elif not reached and found_event:
                    LOG.warn('Host failed to reach expected status:{}, although event/alarm raised for process:{}, '
                             'process_type:{}, host:{}'.format(expected, name, process_type, host))
                    return -1

                self.pid = -1
                try:
                    with host_helper.ssh_to_host(host, con_ssh=con_ssh) as con:
                        raw_pid = con.exec_cmd('tail /home/wrsroot/results.txt | tail -n1', fail_ok=True)[1]
                        self.pid = int(raw_pid)
                except ValueError as e:
                    LOG.warn('Unknown pid:{} from cmd:{}'.format(cmd, e))
                except Exception as e:
                    LOG.warn('Unknown error:{}, cmd:{}'.format(e, cmd))

                LOG.debug('OK, either host in expected status or events found for process: {}'.format(name))
                return 0

            LOG.debug('Try again after wait {} seconds (debounce)'.format(debounce))
            time.sleep(debounce)

        if -1 == self.pid:
            LOG.warn('Unknown from cmd:{}'.format(cmd))

        return -1

    def kill_process_and_verify_impact(self, con_ssh=None):
        host = self.host
        node_type = self.node_type
        active_controller = self.active_controller
        name = self.name
        cmd = self.cmd
        impact = self.impact
        process_type = self.process_type
        retries = self.retries
        interval = self.interval
        pid_file = self.pid_file
        severity = self.severity
        debounce = self.debounce

        on_active_controller = (node_type == 'active' and self.host == active_controller)

        LOG.info('name:{} cmd:{} impact:{} process_type:{} node_type:{}'.format(
            name, cmd, impact, process_type, node_type))

        if process_type == 'pmon':
            code = self.kill_pmon_process_and_verify_impact(name, impact, process_type, host, severity=severity,
                                                            pid_file=pid_file, retries=retries,
                                                            interval=interval, debounce=debounce, con_ssh=con_ssh)

        else:
            pid, host = mtc_helper.kill_sm_process_and_verify_impact(
                name, cmd=cmd, pid_file=self.pid_file, impact=impact, host=host,
                process_type=process_type, retries=retries, interval=interval/3,
                on_active_controller=on_active_controller)

            code = 0 if pid > 1 else -1

            if self.impact == 'swact':
                self.prev_active_controller = active_controller
                self.active_controller = host
                self.prev_host = host
                self.host = host

        self.success = (code == 0)

        global _tested_procs
        _tested_procs.append(self)

        return code


@mark.parametrize('process_name', [
    mark.p1('sm'),
    # TODO CGTS-6451
   # mark.p1('rmond'),
    mark.p0('docker'),
    mark.p0('kubelet'),
    mark.p1('fsmond'),
    mark.priorities('p1', 'sx_nightly')('hbsClient'),
    mark.p1('mtcClient'),
    mark.p1('mtcalarmd'),
    mark.p1('sm-api'),
    mark.p1('sm-watchdog'),
    mark.p1('sysinv-agent'),
    mark.p1('sw-patch-controller-daemon'),
    mark.p1('sw-patch-agent'),
    mark.p1('acpid'),
    mark.p1('ceilometer-polling'),
    mark.p1('mtclogd'),
    mark.p1('ntpd'),
    mark.p1('sm-eru'),
    mark.p1('sshd'),
    mark.p1('syslog-ng'),
    mark.p1('io-monitor-manager'),
    mark.p1('logmgmt'),
    mark.p1('guestServer'),
    mark.p1('host_agent'),
   # mark.p1('libvirtd'),
    mark.p1('neutron-avr-agent'),
    mark.p1('neutron-avs-agent'),
    mark.p1('neutron-dhcp-agent'),
    mark.p1('neutron-metadata-agent'),
    mark.p1('neutron-sriov-nic-agent'),
   # mark.p1('nova-compute'),
    mark.p1('vswitch'),

    # mark.p1(('postgres')),    # Bin recommend not to test this. Whole system down when kill this.
    # mark.p1(('rabbitmq-server')), # rabbit in SM don't test as per CGTS-6336
    mark.p1('rabbit'),
    mark.p1('sysinv-inv'),    # sysinv-inv in SM
    mark.p1('sysinv-conductor'),
    mark.p1('mtc-agent'),
    # mark.p1('hbs-agent'),     # obsoleted
    mark.p1('hw-mon'),
    mark.p1('dnsmasq'),
    mark.p1('fm-mgr'),
    mark.p1('keystone'),
    #mark.p1('glance-registry'),
    # major
   # mark.p1('glance-api'),
  #  mark.p1('neutron-server'),
  # mark.p1('nova-api'),
  # mark.p1('nova-scheduler'),
  # mark.p1('nova-conductor'),
  # mark.p1(('nova-cert')),       # Removed in pike
 #   mark.p1('nova-console-auth'),
  # minor
  #  mark.p1('nova-novnc'),
  # major
  #  mark.p1('cinder-api'),
  #  mark.p1('cinder-scheduler'),
  #  mark.p1('cinder-volume'),   # retries = 32
    # mark.p1('ceilometer-collector'),
    # mark.p1('ceilometer-api'),
  #  mark.p1('ceilometer-agent-notification'),
  #  mark.p1('gnocchi-metricd'),
  #  mark.p1('gnocchi-api'),
   # mark.p1('ceilometer-api'),
   # mark.priorities('p1', 'sx_nightly')('heat-api'),
   # mark.p1('heat-api-cfn'),
   # mark.p1('heat-api-cloudwatch'),
   # mark.p1('heat-engine'),
    mark.p1('snmp'),

    # TODO CGTS-6426
    # mark.p1(('open-ldap')),, active/active
    # mark.p1(('lighttpd')),, active/active
    # mark.p1('horizon'),, active/active
    # mark.p1(('ceph-rest-api')),
    mark.p1('ceph-manager'),

    # mark.p1(('gunicorn')), changed to horizon
    # mark.p1(('patch-alarm-manager')),     ???

 #   mark.p1('vim-api'),
 #   mark.p1('vim'),
    # minor
 #   mark.p1('vim-webserver'),
    mark.p1('guest-agent'),
 #  mark.p1('nova-api-proxy'),
    mark.p1('haproxy'),
 #   mark.p1('aodh-api'),
 #   mark.p1('aodh-evaluator'),
 #   mark.p1('aodh-listener'),
 #   mark.p1('aodh-notifier'),
])
def test_process_monitoring(process_name, con_ssh=None):
    """
    Test system behaviors when processes monitored by TiS are killed

    User Stories:
        US61041 US66951 US18629

    Test Steps:
        - get process settings for the specified process name, from pre-defined information, configuration files and
            running processes on applicable hosts
        - kill the process up time 'retries' times, verify the system behaviors or the expected IMPACT at:
            -- each kills (before the process been killed up to 'retries'):  no IMPACT should NOT happen
            -- after kills 'retries' times: IMPACT should happen
        - or kill the process consecutively 'retries' times (in case of PMOND process) and verify IMPACT
        - wait for IMPACTed hosts been recovered

    Teardown:
        - monitor the process (with the specified name) running for a period (while waiting for the system stabilizes)


    Note:
        Avoid to run test case for now for the following processes:

            open-ldap       CGTS-6426:  in active/active redundancy model, required to be active on both controllers
            lighttpd        CGTS-6426:  in active/active redundancy model, required to be active on both controllers
            ceph-rest-api   CGTS-6426:  in active/active redundancy model, required to be active on both controllers
            horizon         CGTS-6426:  in active/active redundancy model, required to be active on both controllers

            postgres        SKIPPED, ‘killing postgres process may cause data damage which could destabilize the system’
            patch-alarm-manager    SKIPPED, differently might running on either of the controllers

            ntpd            SKIPPED, 'ntpd is not a restartable process'
    """
    region = ProjVar.get_var('REGION')
    if region != 'RegionOne' and region in MULTI_REGION_MAP and re.search('keystone|glance', process_name):
        skip("Keystone and Glance services are on primary region only for multi-region system")

    LOG.tc_step('Start testing SM/PM Process Monitoring')

    assert process_name in PROCESSES, \
        'Unknown process with name:{}'.format(process_name)

    proc = MonitoredProcess(process_name, **PROCESSES[process_name])

    if not proc.is_supported_lab():
        skip('Not supported lab')

    if proc.name in SKIP_PROCESS_LIST:
        LOG.info('{} in skip-list, skip testing'.format(proc.name))
        skip('Process:{} is in skip-list:{}'.format(process_name, SKIP_PROCESS_LIST))

    else:
        code = proc.kill_process_and_verify_impact(con_ssh=con_ssh)

        hosts = table_parser.table(cli.system('host-list', ssh_client=con_ssh))
        LOG.debug('hosts:\n{}'.format(hosts))

        assert 0 == code, \
            'failed in killing process and verifying impact for process:{}'.format(process_name)

    LOG.info('OK, testing killing process:{} completed successfully, will continue monitoring the process'.format(
        process_name))


def _monitor_process(process, total_time, interval=5):
    name = getattr(process, 'name', None)
    cmd = getattr(process, 'cmd', None)
    pid = getattr(process, 'pid', None)
    host = getattr(process, 'host', None)
    pid_file = getattr(process, 'pid_file', None)
    process_type = getattr(process, 'process_type', 'sm')

    LOG.info('Starting monitoring process:{}'.format(name))

    global _final_processes_status

    con_ssh = SSHClient(ProjVar.get_var('lab')['floating ip'])
    con_ssh.connect(use_current=False)
    ControllerClient.set_active_controller(con_ssh)

    used_pids = []
    died_pids = []
    stop_time = time.time() + total_time

    while time.time() < stop_time:
        cur_pid, proc_name = mtc_helper.get_process_info(
            name, cmd=cmd, host=host, process_type=process_type, pid_file=pid_file, con_ssh=con_ssh)[0:2]

        _final_processes_status[name].update({'used_pids': used_pids})

        if pid != cur_pid:
            LOG.warn('Got new PID for process:{}, no new process should be created after impact. '
                     'pid={}, new-pid={}'.format(name, pid, cur_pid))

            used_pids.append(cur_pid)
            pid = cur_pid

        else:
            LOG.info('OK, PID not changed:{} for process:{}'.format(pid, name))

        running, msg = mtc_helper.is_process_running(cur_pid, host, con_ssh=con_ssh)

        if not running:
            died_pids.append(cur_pid)

            LOG.warn('Process died: pid:{} at {}, msg:{}'.format(
                pid, datetime.datetime.utcnow().isoformat(), msg))
        else:
            LOG.info('OK, process:{} is running, name:{}'.format(pid, name))

        _final_processes_status[name].update({'died_pids': died_pids})

        time.sleep(interval)


def monitor_process(process, total_time):
    LOG.info('monitoring process:{} for {} seconds'.format(process, total_time))

    name = getattr(process, 'name', None)
    pid = getattr(process, 'pid', None)

    global _final_processes_status
    _final_processes_status[name] = {'used_pids': [], 'died_pids': []}

    if name is not None and pid is not None:
        thread = threading.Thread(
            target=_monitor_process,
            args=(process, total_time),
            name='Monitor-{}-{}'.format(name, pid))
        # thread.setDaemon(True)
    else:
        LOG.info('Process Name or PID is None, proc={}'.format(process))
        thread = None

    return thread


@fixture(scope='function', autouse=True)
def wait_and_monitor_tested_processes(request):

    global _tested_procs, _final_processes_status
    _tested_procs[:] = []
    _final_processes_status.clear()

    def _wait_and_monitor_tested_processes():

        total_time = INTERVAL_BETWEEN_SWACT + 60
        pre_wait = INTERVAL_BETWEEN_SWACT / 5

        if not _tested_procs:
            LOG.info('No processes completed the whole procedure? Wait for system recovered in {} seconds'.format(
                total_time/10))
            time.sleep(total_time/10)
        else:
            last_impact = getattr(_tested_procs[-1], 'impact', 'swact')
            if last_impact != 'swact':
                total_time = INTERVAL_BETWEEN_SWACT / 4
                pre_wait = INTERVAL_BETWEEN_SWACT / 20

            LOG.info('Wait for {} seconds after potential killing process testing'.format(pre_wait))
            time.sleep(pre_wait)

            monitors = []
            for proc in _tested_procs:
                if not getattr(proc, 'success', False):
                    LOG.info('Process:{} failed, so skip monitoring its process status'.format(proc.name))
                    continue

                LOG.info('Monitoring process:{} for {} seconds'.format(proc.name, total_time - pre_wait))

                monitor = monitor_process(proc, total_time - pre_wait)
                if monitor is not None:
                    monitors.append(monitor)
            if not monitors:
                LOG.info('No processes monitored?')

            [proc.start() for proc in monitors]
            [proc.join() for proc in monitors]

        global _final_processes_status
        for name, pids_info in _final_processes_status.items():
            LOG.info('monitoring process:{}'.format(name))

            total = len(pids_info['used_pids'])
            died = len(pids_info['died_pids'])

            if died > 0:
                # this should never happen but it does occasionally, just flag an error for now
                LOG.error('Really?\t{}/{} processes died, {}'.format(died, total, pids_info['died_pids']))

            assert total == 1, \
                'Should have only 1 new process. Used pids:{}'.format(pids_info['used_pids'])

            LOG.info('OK, the new process for service:{} is running stable, pid:{}'.format(
                name, pids_info['used_pids'][-1]))

    request.addfinalizer(_wait_and_monitor_tested_processes)
