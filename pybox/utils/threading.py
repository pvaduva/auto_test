from utils.install_log import LOG
import threading
from helper import host_helper

class InstallThread(threading.Thread):
    def __init__(self, stream, thread_name, hostname,  host_type, id):
        threading.Thread.__init__(self)
        self.id = id
        self.thread_name = thread_name
        self.host_type = host_type
        self.hostname = hostname
        self.stream = stream
        self.id = id
    
    def run(self):
        LOG.info("Starting {} thread".format(self.hostname))
        host_helper.install_host(self.stream, self.hostname, self.host_type, self.id)
        LOG.info("Exiting {} thread".format(self.hostname))
