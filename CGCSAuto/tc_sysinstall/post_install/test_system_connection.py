import setups
from keywords import install_helper
from consts.proj_vars import InstallVars



def test_system_fip():
    lab = InstallVars.get_install_var("LAB")
    res_dict = setups.collect_sys_net_info(lab)
    retry = False
    for res in res_dict.values():
        if not res:
            retry = True
            break
    if retry:
        res_dict = setups.collect_sys_net_info(lab)
        for key, value in res_dict.items():
            assert value, "could not {}".format(key)


def test_system_telnet():
    lab = InstallVars.get_install_var("LAB")
    node_obj = lab["controller-0"]
    install_helper.power_on_host(node_obj.name, wait_for_hosts_state_=False)
    telnet_conn = install_helper.open_telnet_session(node_obj) if node_obj.telnet_conn is None else node_obj.telnet_conn
    telnet_conn.send("\r\n")
    index = telnet_conn.expect(["ogin:", telnet_conn.prompt], fail_ok=True)
    if index < 0:
        telnet_conn.send_control("\\")
        telnet_conn.expect(["anonymous:.+:PortCommand> "])
        telnet_conn.send("resetport")
        telnet_conn.send("\r\n")
        telnet_conn.login()
