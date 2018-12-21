import time

from utils.clients.telnet import TelnetClient
from keywords import system_helper


def check_alarms():
    pass


def test_telnet():
    # t_net = Telnet(host='128.224.148.230', port=2039, timeout=20)
    # t_net.write(b'\r\n\r\n')
    # output = t_net.read_until(b'ogin')
    # print(output.decode())
    # t_net.write('\r\n\r\n'.encode())
    # output = t_net.expect(['(controller|compute|storage)-\d+ login:'.encode()])[2]
    # output = t_net.read_until(b'ogin')
    # print(output.decode())

    # telnet = TelnetClient(host='128.224.148.230', port=2039, hostname='compute-1', timeout=10)
    telnet = TelnetClient(host='128.224.148.230', port=2039, hostname=None, timeout=10)
    try:
        print("hostname: {}; prompt: {}".format(telnet.hostname, telnet.prompt))
        telnet.connect()
        output = telnet.exec_cmd('pwd')[1]
        print("Output: {}".format(output))

        telnet.send('pwd')
        time.sleep(3)
        output = telnet.flush()
        # output = telnet.read_very_eager()
        print('flushed: ' + str(output))

    finally:
        telnet.close()


def test_get_build_info():
    telnet = TelnetClient(host='128.224.148.169', port=2015, hostname='controller-0', timeout=10)
    telnet.connect(login=False)
    telnet.login()
    telnet.logger.debug('Sending')
    telnet.send('\n\n')
    telnet.logger.debug('Sent,flusing')
    telnet.flush()
    telnet.logger.debug('flushed')
    telnet.exec_cmd('cat /etc/build.info', fail_ok=False)
    telnet.exec_cmd('pwd')