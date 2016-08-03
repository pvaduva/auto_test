import time
from datetime import datetime, date
from keywords import check_helper

print(datetime.utcnow())
print(datetime.utcnow().timestamp())

timestamp = '2016-07-18 20:01:25.176488+00:00'

time_ = datetime.utcnow()
print(check_helper.compare_times(time_, timestamp))

