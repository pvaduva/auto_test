import datetime
import logging

current_time = datetime.datetime.now()

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s: %(message)s")
handler = logging.FileHandler("logs/{}_{}_{}_{}:{}.log".format(current_time.year, current_time.month, current_time.day, current_time.hour, current_time.minute))
handler.setFormatter(formatter)
handler.setLevel(logging.INFO)
LOG.addHandler(handler)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
LOG.addHandler(handler)