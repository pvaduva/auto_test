import os
from consts.cgcs import LocalStorage
from keywords import common
from utils.ssh import ControllerClient
from utils.tis_log import LOG

def test_scp_from_local():
    srcfile = os.path.sep.join([os.path.expanduser('~'),
                                LocalStorage.DIR_PROFILE,
                                'image_storage_profile_to_import.xml'])

    destfile = os.path.sep.join(['/home/wrsroot',
                                 LocalStorage.DIR_PROFILE,
                                 'new_image_storage_profile_to_import.xml'])

    destip = ControllerClient.get_active_controller().host

    LOG.info('scp: srcfile={}, dest={}, destip={}'.format(srcfile, destfile, destip))
    common.scp_from_local(srcfile, destip, destfile)


def test_scp_to_local():
    srcdir = '/home/wrsroot/instances'

    destdir = os.path.sep.join([os.path.expanduser('~'),
                                LocalStorage.DIR_PROFILE])

    destip = ControllerClient.get_active_controller().host

    common.scp_to_local(srcdir, destip, destdir, is_dir=True)
