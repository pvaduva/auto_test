
import os.path
import time

from utils.tis_log import LOG
from pytest import mark
from utils.ssh import ControllerClient
from keywords import mtc_helper
from keywords import system_helper


DEF_RETRIES = 2
DEF_DEBOUNCE = 20
#DEF_INTERVAL = 20
DEF_INTERVAL = 10
DEF_PROCESS_RESTART_CMD = r'/etc/init.d/{} restart'
DEF_PROCESS_PID_FILE_PATH = r'/var/run/{}.pid'

INTERVAL_BETWEEN_SWACT = 300 + 200
IMPACTS = ['swact', 'log', 'enabled-degraded', 'disabled-failed', 'alarm', 'warn']

SKIP_PROCESS_LIST = ['postgres']
PROCESSES = {
    'sm': {'cmd': 'sm', 'impact': 'disabled-failed', 'severity': 'critical'},
    'rmond': {'cmd': 'rmon', 'impact': 'enabled-degraded', 'severity': 'major', 'interval': 10},
    'fsmond': {'cmd': 'fsmon', 'impact': 'enabled-degraded', 'severity': 'major', 'interval': 5},
    'hbsClient': {'cmd': 'hbsClient', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 3, 'interval': 1},
    'mtcClient': {'cmd': 'mtcClient', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 3, 'interval': 1},
    'mtcalarmd': {'cmd': 'mtcalarmd', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 3, 'interval': 1},
    'sm-api': {'cmd': 'sm-api', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20, 'interval': 5},
    'sm-watchdog': {'cmd': 'sm-watchdog', 'impact': 'enabled-degraded', 
                    'severity': 'major', 'debounce': 20, 'interval': 5},
    'sysinv-agent': {
        'cmd': 'sysinv-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20, 'interval': 5},
    'sw-patch-controller-daemon': {'cmd': 'sw-patch-controller-daemon', 'impact': 'enabled-degraded',
                                   'severity': 'major', 'debounce': 20, 'interval': 5},

    'sw-patch-agent': {
        'cmd': 'sw-patch-agent', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 20, 'interval': 5},
    'acpid': {'cmd': 'acpid', 'impact': 'log', 'severity': 'minor', 'debounce': 20, 'interval': 5, 'retries': 10},
    'ceilometer-polling': {
        'cmd': '/usr/bin/python2 /usr/bin/ceilometer-polling',
        'impact': 'log', 'severity': 'minor', 'debounce': 20, 'interval': 10, 'retries': 5},
    'mtclogd': {'cmd': 'mtclogd', 'impact': 'log', 'severity': 'minor', 'debounce': 3, 'interval': 1, 'retries': 3},
    'ntpd': {'cmd': 'ntpd', 'impact': 'log', 'severity': 'minor', 'debounce': 0, 'interval': 0, 'retries': 0},
    'sm-eru': {'cmd': 'sm-eru', 'impact': 'log', 'severity': 'minor', 'debounce': 20, 'interval': 5, 'retries': 3},
    'sshd': {'cmd': 'sshd', 'impact': 'log', 'severity': 'minor', 'debounce': 20, 'interval': 5, 'retries': 10},

    # Note: name differs from cmd
    'syslog-ng': {'cmd': 'syslog', 'impact': 'log', 'severity': 'minor', 'debounce': 20, 'interval': 10, 'retries': 10},
    'io-monitor-manager': {'cmd': 'io-monitor-manager', 'impact': 'log',
                           'severity': 'minor', 'debounce': 20, 'interval': 10, 'retries': 5},
    'logmgmt': {'cmd': 'logmgmt', 'impact': 'log', 'severity': 'minor', 'debounce': 20, 'interval': 5, 'retries': 5},
    # compute-only processes
    'guestServer': {'cmd': 'guestServer', 'impact': 'enabled-degraded', 'severity': 'major', 'debounce': 10,
                    'interval': 3, 'retries': 3, 'node_type': 'compute'},
    'host_agent': {'cmd': 'guestServer', 'impact': 'enabled-degraded',
                   'severity': 'major', 'debounce': 20, 'interval': 1, 'retries': 3, 'node_type': 'compute'},
    'libvirtd': {'cmd': 'libvirtd', 'impact': 'disabled-failed',
                 'severity': 'critical', 'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    'neutron-avr-agent': {'cmd': 'neutron-avr-agent', 'impact': 'enabled-degraded',
                          'severity': 'major', 'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    'neutron-avs-agent': {'cmd': 'neutron-avs-agent', 'impact': 'disabled-failed',
                          'severity': 'critical', 'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    'neutron-dhcp-agent': {'cmd': 'neutron-dhcp-agent', 'impact': 'enabled-degraded',
                           'severity': 'major', 'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    'neutron-metadata-agent': {'cmd': 'neutron-metadata-agent', 'impact': 'enabled-degraded', 'severity': 'major',
                               'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    'neutron-sriov-nic-agent': {'cmd': 'neutron-sriov-nic-agent', 'impact': 'enabled-degraded', 'severity': 'major',
                                'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    # Note: name differs from cmd
    'nova-compute': {'cmd': 'nova-startup', 'impact': 'disabled-failed',
                     'severity': 'critical', 'debounce': 20, 'interval': 5, 'retries': 3, 'node_type': 'compute'},
    'vswitch': {'cmd': 'vswitch', 'impact': 'disabled-failed',
                'severity': 'critical', 'debounce': 20, 'interval': 3, 'retries': 0, 'node_type': 'compute'},

    # the following are SM managed services
    # active-controller only processes
    # kwargs : dict'node_type': 'active', pid_file:None, 'debounce':None, 'interval':None, 'retries':None},
    'postgres': {'cmd': '/usr/bin/postgres', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
    # {'rabbitmq-server': {
    # rabbit in sm-dump
    'rabbit': {'cmd': '/usr/lib/rabbitmq/bin/rabbitmq-server', 'impact': 'swact',
               'severity': 'critical', 'node_type': 'active'},
    # {'sysinv-api': {
    # sysinv-inv in sm-dump
    'sysinv-inv': {'cmd': '/usr/bin/python /bin/sysinv-api', 'impact': 'swact',
                   'severity': 'critical', 'node_type': 'active'},
    'sysinv-conductor': {
        'cmd': '/usr/bin/python /bin/sysinv-conductor', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    # {'mtcAgent': {
    'mtc-agent': {'cmd': '/usr/local/bin/mtcAgent', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
    # {'hbsAgent': {
    'hbs-agent': {'cmd': '/usr/local/bin/hbsAgent', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
    # {'hwmond': {
    'hw-mon': {'cmd': '/usr/local/bin/hwmond', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
    'dnsmasq': {'cmd': '/usr/sbin/dnsmasq', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
    # {'fmManager': {
    'fm-mgr': {'cmd': '/usr/local/bin/fmManager', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
    # {'keystone-all': {
    'keystone': {'cmd': '/usr/bin/python2 /bin/keystone-all', 'impact': 'swact',
                 'severity': 'critical', 'node_type': 'active'},
    'glance-registry': {'cmd': '/usr/bin/python2 /bin/glance-registry', 'impact': 'swact',
                        'severity': 'critical', 'node_type': 'active'},
    'glance-api': {
        # 'cmd': '/usr/bin/python2 /bin/glance-api', 'impact': 'swact',
        'cmd': '/usr/bin/python2 /bin/glance-api', 'impact': 'enabled-degraded',
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
    'nova-cert': {
        'cmd': '/usr/bin/python2 /bin/nova-cert', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    # {'nova-consoleauth': {
    'nova-console-auth': {
        'cmd': '/usr/bin/python2 /bin/nova-consoleaut', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    # {'nova-novncproxy': {
    'nova-novnc': {
        # 'cmd': '/usr/bin/python2 /bin/nova-novncproxy', 'impact': 'swact',
        'cmd': '/usr/bin/python2 /bin/nova-novncproxy', 'impact': 'log',
        'severity': 'major', 'node_type': 'active'},
    'cinder-api': {'cmd': '/usr/bin/python2 /bin/cinder-api', 'marjor': 'enabled-degraded',
                   'severity': 'major', 'node_type': 'active'},
    # {'cinder-schedule': {
    'cinder-scheduler': {
        'cmd': '/usr/bin/python2 /bin/cinder-scheduler', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    # note: retries for cinder-volume is 32
    'cinder-volume': {
        'cmd': '/usr/bin/python2 /bin/cinder-volume', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active', 'retries': 32},
    'ceilometer-collector': {
        'cmd': '/usr/bin/python2 /bin/ceilometer-collector', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    'ceilometer-api': {
        'cmd': '/usr/bin/python2 /bin/ceilometer-api', 'impact': 'swact',
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
    'open-ldap': {'cmd': '/usr/sbin/slapd', 'impact': 'swact', 'severity': 'critical', 'node_type': 'active'},
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

    # no such process existing any more on the active-controller?
    # controller-0:~# ps aux |grep ceph-rest-api
    # MonitoredProcess'ceph-rest-api', '', 'swact', 'severity': 'critical'},
    # on active-controller of a storage-lab
    'ceph-rest-api': {
        'cmd': 'python /usr/bin/ceph-rest-api', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    'ceph-manager': {
        'cmd': 'python /usr/bin/ceph-manager', 'impact': 'swact',
        'severity': 'critical', 'node_type': 'active'},
    # {'nfv-vim-api': {
    'vim-api': {
        'cmd': '/usr/bin/python /bin/nfv-vim-api', 'impact': 'enabled-degraded',
        'severity': 'major', 'node_type': 'active'},
    # {'nfv-vim-webserver': {
    'vim-webserver': {
        'cmd': '/usr/bin/python /bin/nfv-vim-webserver', 'impact': 'log',
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

    # no more porcess named 'ceilometer-mem-*'
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

        self.retries = kwargs.get('retries', DEF_RETRIES)
        self.debounce = kwargs.get('debounce', DEF_DEBOUNCE)
        self.interval = kwargs.get('interval', DEF_INTERVAL)

        self.prev_stats = None
        self.con_ssh = ControllerClient.get_active_controller()

        main_cmd = cmd.split()[0]

        if main_cmd == self.cmd and not os.path.abspath(self.cmd):
            self.cmd = DEF_PROCESS_RESTART_CMD.format(cmd)

        if self.pid_file is None:
            self.pid_file = DEF_PROCESS_PID_FILE_PATH.format(self.name)
        elif not os.path.abspath(self.pid_file):
            self.pid_file = DEF_PROCESS_PID_FILE_PATH.format(os.path.basename(os.path.split(self.pid_file))[0])

    def show(self):
        for attr in dir(self):
            if not attr.startswith('_'):
                LOG.info('{}={}\n'.format(attr, getattr(self, attr)))

    def kill_process_on_compute(self, node=None, retries=2, msg='', con_ssh=None):
        LOG.info('kill process:{} on compute:{} {}, retries={}\n'.format(
            self.name, node or 'randomly chosen compute', msg, retries))
        _ = con_ssh

        return 0

    def kill_process_on_storage(self, node=None, msg='', retries=2, con_ssh=None):
        LOG.info('kill process:{} on storage:{} {}, retries={}\n'.format(
            self.name, node or 'any storage-node', msg, retries))
        _ = con_ssh
        return 0

    def kill_process_and_verify_impact(self, con_ssh=None):

        node_type = self.node_type

        if node_type in ['all']:
            # in this case, will randomly chose one compute (or the standby controller in case of CPE)
            LOG.info('for node-type:{}, kill on compute'.format(node_type))
            code = self.kill_process_on_compute(msg='for any type of host("all")', con_ssh=con_ssh)

        elif node_type in ['controller', 'active']:
            LOG.info('for node-type:{}, kill on controller'.format(node_type))
            code = mtc_helper.kill_controller_process_verify_impact(
                self.name,
                cmd=self.cmd,
                impact=self.impact,
                retries=self.retries,
                # TODO
                interval=self.interval,
                on_active_controller=(node_type == 'active'),
                con_ssh=self.con_ssh)
            assert 0 == code, \
                'Fail in killing process:{} and expecting impact: {}'.format(self.name, self.impact)

        elif node_type in ['compute']:
            LOG.info('for node-type:{}, kill on compute'.format(node_type))
            code = self.kill_process_on_compute(msg='for compute node', retries=self.retries, con_ssh=con_ssh)

        elif node_type in ['storage']:
            LOG.info('for node-type:{}, kill on storage'.format(node_type))
            code = self.kill_process_on_storage(msg='for controller node', retries=self.retries, con_ssh=con_ssh)

        else:
            LOG.error('unknown node-type:{}, will try to kill the process:{} on a randomly choosen compute'.format(
                node_type, self.name))
            code = -1

        return code


@mark.parametrize(('process_name'), [
    # mark.p1(('postgres')),
    # mark.p1(('rabbitmq-server')), # rabbit in sm-dump list
    mark.p1(('rabbit')),
    # mark.p1(('sysinv-api')),
    mark.p1(('sysinv-inv')),
    mark.p1(('sysinv-conductor')),
    mark.p1(('mtc-agent')),
    mark.p1(('hbs-agent')),
    mark.p1(('hw-mon')),
    mark.p1(('dnsmasq')),
    mark.p1(('fm-mgr')),
    mark.p1(('keystone')),
    mark.p1(('glance-registry')),
    mark.p1(('glance-api')),
    mark.p1(('neutron-server')),
    mark.p1(('nova-api')),
    mark.p1(('nova-scheduler')),
    mark.p1(('nova-conductor')),
    mark.p1(('nova-cert')),
    mark.p1(('nova-console-auth')),
    mark.p1(('nova-novnc')),

    mark.p1(('cinder-api')),
    mark.p1(('cinder-scheduler')),
    mark.p1(('cinder-volume')),
    mark.p1(('ceilometer-collector')),
    mark.p1(('ceilometer-api')),
    mark.p1(('ceilometer-agent-notification')),
    mark.p1(('heat-engine')),
    mark.p1(('heat-api')),
    mark.p1(('heat-api-cfn')),
    mark.p1(('heat-api-cloudwatch')),

    mark.p1(('open-ldap')),
    mark.p1(('snmp')),
    mark.p1(('lighttpd')),
    # mark.p1(('gunicorn')),
    mark.p1(('horizon')),
    mark.p1(('patch-alarm-manager')),

    mark.p1(('ceph-rest-api')),
    mark.p1(('ceph-manager')),
    mark.p1(('vim-api')),
    mark.p1(('vim-webserver')),
    mark.p1(('guest-agent')),
    mark.p1(('nova-api-proxy')),
    mark.p1(('haproxy')),

    mark.p1(('aodh-api')),
    mark.p1(('aodh-evaluator')),
    mark.p1(('aodh-listener')),
    mark.p1(('aodh-notifier')),

    # mark.p1(('critical')),
    # mark.p2(('major')),
    # mark.p3(('minor')),
    # mark.p4(('all')),
])
def test_process_monitoring(process_name, con_ssh=None):
    """
    Test system behaviors when processes monitored by TiS are killed

    Args:
        process_name (str): Name of the process to test. The following specical names are supported:
            all        --   all processes managed including those managed by PMON/RMON
            critical   --   all processes with 'critical' severity
            major      --   all processes with 'major' severity
            minor      --   all processes with 'minor' severity

        con_ssh:

    Returns:

    """
    LOG.tc_step('Start testing SM/PM Prcocess Monitoring')

    procs = []
    for name, values in PROCESSES.items():
        try:
            proc = MonitoredProcess(name, **dict(values))
            procs.append(proc)

        except KeyError as e:
            LOG.error('unknown process, error={}'.format(e))
            LOG.error('name={}, values={}'.format(name, values))
            raise

        except Exception as e:
            LOG.error('unknown error, error={}'.format(e))
            LOG.error('name={}, values={}'.format(name, values))
            raise

    if process_name is None or process_name == 'all':
        procs_to_test = procs

    elif process_name in ['critical', 'major', 'minor']:
        procs_to_test = [p for p in procs if p.severity == process_name]

    elif process_name in [p.name for p in procs]:
        procs_to_test = [p for p in procs if p.name == process_name]

    else:
        LOG.error('unknown process name:{}'.format(process_name))
        procs_to_test = []

    LOG.tc_step('Kill the proc and monitoring the TIS responds as expected')
    LOG.info('TOTAL {:02d} processes to test for:{}'.format(len(procs_to_test), process_name))

    prev_impact = ''
    tested, passed, failed, skipped = 0, 0, 0, 0

    skipped_procs = []
    for proc in procs_to_test:
        tested += 1
        LOG.tc_step('kill process:{}'.format(proc.name))

        if proc.name in SKIP_PROCESS_LIST:
            LOG.info('{} in skip-list, skip testing'.format(proc.name))
            skipped_procs.append(proc.name)
            result = 'SKIP'
            skipped += 1

        else:
            if prev_impact == 'stact' and proc.impact == 'swact':
                LOG.info('sleep {} seconds because both previous and current IMPACT are swact')
                time.sleep(INTERVAL_BETWEEN_SWACT)

            if 0 == proc.kill_process_and_verify_impact(con_ssh=con_ssh):
                result = 'PASS'
                passed += 1

            else:
                result = 'FAIL'
                failed += 1

        LOG.info('{}\t{:02d}\tprocess:{} done'.format(result, tested, proc.name))

    LOG.info('\nPASS\t{:03d}\nFAIL\t{:03d}\nSKIP\t{:03d}\nTOTAL\t{:03d}'.format(
        passed, failed, skipped, tested))

    time.sleep(INTERVAL_BETWEEN_SWACT)