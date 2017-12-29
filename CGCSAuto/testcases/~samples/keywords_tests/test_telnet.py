import time
from utils.ssh import TelnetClient


def test_telnet():
    telnet = TelnetClient(host='128.224.148.176', port=2001, hostname='controller-0', timeout=10)
    try:
        telnet.connect()
        telnet.send('ls')
        time.sleep(5)
        output = telnet.flush()
        # output = telnet.read_very_eager()
        print('read very eager: ' + str(output))

        # telnet.flush()
        # telnet.send()
        # index = telnet.expect([telnet.prompt, 'controller-0 login'], fail_ok=False)
        # assert 0 == index
        #
        # code, output = telnet.exec_cmd('pwd')
        # print("Here's output for pwd: {}".format(output))
        # # telnet.send('ls')
        # # telnet.expect('hahaha')
    finally:
        telnet.close()
    # print(content)
