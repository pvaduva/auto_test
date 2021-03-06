import os

from keywords import common
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def test_scp_from_local():
    srcfile = os.path.join(os.path.expanduser('~'),
                                'TiS_config.ini')

    destfile = os.path.join('/home/sysadmin',
                                 'TiS_config.ini')

    destip = ControllerClient.get_active_controller().host

    LOG.info('scp: srcfile={}, dest={}, destip={}'.format(srcfile, destfile, destip))
    common.scp_from_local(source_path=srcfile, dest_ip=destip, dest_path=destfile)


def test_scp_to_local():
    srcdir = '/home/sysadmin/instances'

    destdir = os.path.join(os.path.expanduser('~'))

    destip = ControllerClient.get_active_controller().host

    common.scp_to_local(source_path=srcdir, source_server=destip,
                        dest_path=destdir, is_dir=True)
