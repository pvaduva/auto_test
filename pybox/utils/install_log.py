import os
import datetime
import logging
from consts.env import LOGPATH

if not os.path.exists(LOGPATH):
    os.mkdir(LOGPATH)

current_time = datetime.datetime.now()

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s: %(message)s")
log_file = "{}/{}_{}_{}_{}_{}.log".format(LOGPATH, current_time.year, current_time.month, current_time.day, current_time.hour, current_time.minute)
handler = logging.FileHandler("{}/{}_{}_{}_{}_{}.log".format(LOGPATH, current_time.year, current_time.month, current_time.day, current_time.hour, current_time.minute))
handler.setFormatter(formatter)
handler.setLevel(logging.INFO)
LOG.addHandler(handler)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
LOG.addHandler(handler)
