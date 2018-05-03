from utils.ssh import RemoteCLIClient


def test_remote_cli():
    import sys
    print(sys.executable)
    try:
        client = RemoteCLIClient.get_remote_cli_client()
        cmd = ("nova --os-username 'admin' --os-password 'Li69nux*' --os-project-name admin --os-auth-url "
               "http://128.224.150.222:5000/v3 --os-region-name RegionOne --os-user-domain-name Default "
               "--os-project-domain-name Default list --a")
        client.exec_cmd(cmd, fail_ok=False)

        client = RemoteCLIClient.get_remote_cli_client()
        client.exec_cmd(cmd)

    finally:
        RemoteCLIClient.remove_remote_cli_clients()
