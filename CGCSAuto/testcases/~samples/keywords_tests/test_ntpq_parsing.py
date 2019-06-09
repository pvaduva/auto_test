import re

from keywords import system_helper


def test_ntpq_parser():
    system_helper.get_ntpq_status(host='controller-0')

    healthy = """
     remote           refid      st t when poll reach   delay   offset  jitter
==============================================================================
-192.168.204.3   67.215.197.149   3 u   67 1024  377    1.071   -5.596   4.244
*64.56.154.211   128.233.150.93   2 u  740 1024  377   38.330  -16.841   2.965
+159.203.8.72    192.5.41.209     2 u  682 1024  377   11.388  114.288 107.485
+217.26.163.51   128.138.141.172  2 u  342 1024  377  146.054    4.067  18.170

"""
    code, msg = _ntp_test(output=healthy, host='controller-0')
    assert 0 == code

    no_remote = """
     remote           refid      st t when poll reach   delay   offset  jitter
==============================================================================
*192.168.204.3   67.215.197.149   3 u   67 1024  377    1.071   -5.596   4.244
+64.56.154.211   128.233.150.93   2 u  740 1024  377   38.330  -16.841   2.965
+159.203.8.72    192.5.41.209     2 u  682 1024  377   11.388  114.288 107.485
+217.26.163.51   128.138.141.172  2 u  342 1024  377  146.054    4.067  18.170
"""
    code, msg = _ntp_test(output=no_remote, host='controller-0')
    assert 1 == code

    unreachable = """
     remote           refid      st t when poll reach   delay   offset  jitter
==============================================================================
+192.168.204.3   67.215.197.149   3 u   67 1024  377    1.071   -5.596   4.244
*64.56.154.211   128.233.150.93   2 u  740 1024  377   38.330  -16.841   2.965
-159.203.8.72    192.5.41.209     2 u  682 1024  377   11.388  114.288 107.485
+217.26.163.51   128.138.141.172  2 u  342 1024  377  146.054    4.067  18.170

"""
    code, msg = _ntp_test(output=unreachable, host='controller-0')
    assert 2 == code

    unreachable_ = """
         remote           refid      st t when poll reach   delay   offset  jitter
==============================================================================
+192.168.204.4   167.114.204.238  3 u   19   64  376    0.041   10.021   5.967
 192.95.25.79    83.157.230.212   3 u  915   64    0   18.556    9.543   0.000
*131.188.3.221   .DCFp.           1 u    5   64  377  125.342    1.460   6.247
+208.81.1.244    200.98.196.212   2 u   62   64  377   32.534    4.918   4.020
"""

    code, msg = _ntp_test(output=unreachable_, host='controller-0')
    assert 2 == code


def _ntp_test(output, host):
    output_lines = output.splitlines()

    server_lines = list(output_lines)
    for line in output_lines:
        server_lines.remove(line)
        if '======' in line:
            break

    selected = None
    invalid = []
    unreachable = []
    for server_line in server_lines:
        if re.match("192.168..*", server_line[1:]):
            continue

        if server_line.startswith('*'):
            selected = server_line
        elif server_line.startswith(' '):
            invalid.append(server_line)
        elif server_line.startswith('-'):
            unreachable.append(server_line)

    if not selected:
        return 1, "No NTP server selected"

    if invalid or unreachable:
        return 2, "Some NTP servers are not reachable"

    return 0, "{} NTPQ is in healthy state".format(host)
