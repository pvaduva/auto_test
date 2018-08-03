import time

# from testfixtures.fixture_resources import ResourceCleanup

from keywords import common, host_helper

from utils.tis_log import LOG
from consts.cgcs import IxiaServerIP
from utils.exceptions import IxiaError

try:
    import IxNetwork
except ImportError as err:
    LOG.warn(str(err))
    LOG.warn("keywords/ixia_helper is not available")

    class ImportFailedModule(object):
        def __init__(self, imp_err):
            self._exception = imp_err

        def __getattr__(self, name):
            raise self._exception

    IxNetwork = ImportFailedModule(err)


class IxiaResource(object):
    """
    Resource allocation abstraction for IxNetwork Tcl service ports

    Locks are stored in cls.nat_dest_path (/sandbox/ixia) on the test server
    in the format of {resourceName}.lock
    """

    nat_dest_path = '/sandbox/ixia'
    resources = [8010, 8011, 8012, 8013, 8014]

    @staticmethod
    def _lock_name(res):
        return "{}.lock".format(str(res))

    @classmethod
    def _acquire_imm(cls, ssh_client):
        for res in cls.resources:
            r, msg = ssh_client.exec_cmd("test -f {}/{}".format(cls.nat_dest_path, cls._lock_name(res)), fail_ok=True)
            if r:   # file does not exist
                r, msg = ssh_client.exec_cmd(
                    "mkdir -p {}".format(cls.nat_dest_path), fail_ok=False)
                r, msg = ssh_client.exec_cmd(
                    "touch {}/{}".format(cls.nat_dest_path, cls._lock_name(res)), fail_ok=False)
                return res

    @classmethod
    def acquire(cls, timeout=60):
        """
        Acquire a service port, calls common.wait_for_val_from_func

        Args:
            timeout (int):
                stops waiting after timeout

        Returns (tuple):
            (bSucceeded, port_acquired)
        """
        with host_helper.ssh_to_test_server() as ssh_client:
            LOG.info("Acquiring a service port")
            return common.wait_for_val_from_func(cls.resources, timeout, 5, cls._acquire_imm, ssh_client)

    @classmethod
    def release(cls, res):
        """
        Release a service port
        """
        with host_helper.ssh_to_test_server() as ssh_client:
            LOG.info("Releasing service port {}".format(res))
            return ssh_client.exec_cmd("rm -f {}/{}".format(cls.nat_dest_path, cls._lock_name(res)))


class IxiaSession(object):
    """
    Ixia Session to communicate with IxNetwork through Tcl API

    Synchronous Calls (BLOCKING)

    if IxNetwork raises an IxNetwork.IxNetError,
    then the method immediately fails, session state is undefined

    """

    def __init__(self):
        self._ixnet = IxNetwork.IxNet()
        self._connected = False
        self._connected_remote = None
        self._chassis = None
        self._port_map = dict()  # maps portID to binded vport
        self._ixia_resources = list()

    def __del__(self):
        self.disconnect()

    @staticmethod
    def __craft_port_id(card, port, chassis):
        return "{}/card:{}/port:{}".format(chassis, card, port)
        # return f"{chassis}/card:{card}/port:{port}"

    @staticmethod
    def __merge_dict(default, to_merge):
        # in python3.6+, equivalent to, (lambda default, to_merge: {**default, **to_merge})
        d = default.copy()
        d.update(to_merge)
        return d

    @classmethod
    def __compound_ixargs(cls, default, to_merge,
                          k_modif=(lambda k: '-' + str(k) if str(k)[0] != '-' else str(k)),
                          v_modif=(lambda v: v)):
        args = list()
        d = cls.__merge_dict(default, to_merge)

        for k, v in d.items():
            args.append(k_modif(k))
            args.append(v_modif(v))

        return args

    def __remapIds(self, ixnet_obj):
        return self._ixnet.remapIds(ixnet_obj)[0]

    def __ensure_exist(self, obj_ref, child, *add_args):
        # create child if does not exist, returns list
        children = self.getList(obj_ref, child)
        if children:
            return children
        else:
            return [self._ixnet.add(obj_ref, child, *add_args)]

    def connect(self, tcl_server_port=None, tcl_server_ip=None, tcl_server_ver='8.10', port_timeout=60):
        """
        Connect to the IxNetwork Tcl Service Port.
        If tcl_server_port is None, guarantees exclusive access from other automation tests.

        Args:
            tcl_server_port (int|None):
                the IxNetwork Tcl service port
                or None to acquire from IxiaResource (managed)
            tcl_server_ip (str|None):
                the IxNetwork service provider host
                or None to use the default server
            tcl_server_ver (str):
                the IxNetwork Tcl server version expected
            port_timeout (int):
                used only when tcl_server_port is None
                timeout to wait for IxiaResource.acquire

        """
        if tcl_server_ip is None:
            tcl_server_ip = IxiaServerIP.tcl_server_ip

        if tcl_server_port is None:
            LOG.info("tcl_server_port unspecified")
            r, tcl_server_port = IxiaResource.acquire(port_timeout)
            if not r:
                raise IxiaError("connect failed, cannot acquire an available tcl_server_port")
            self._ixia_resources.append(tcl_server_port)

        LOG.info("Connecting to Ixia API Server at {}:{}, version {}".format(
                tcl_server_ip, tcl_server_port, tcl_server_ver))

        try:
            self._connected = True
            self._connected_remote = (tcl_server_ip, tcl_server_port, tcl_server_ver)
            self._ixnet.connect(tcl_server_ip, '-port', tcl_server_port, '-version', tcl_server_ver)
        except Exception as err:
            # if connect failed, do not expect the user to call disconnect
            # all resources allocated by connect shall be released
            self.disconnect()
            raise err

    def disconnect(self, traffic_stop=False):
        """
        Disconnect the underlying socket.
        Allowed to be called multiple times.

        Args:
            traffic_stop (bool):
                calls .traffic_stop() if the traffic is running,
                even when then traffic is not started by this session
                defaults to False, as .disconnect may be called multiple times
        """
        if self._connected:
            if traffic_stop and self.testAttributes(self.getRoot()+'/traffic', state="started"):
                try:
                    self.traffic_stop()
                except:
                    pass
            try:
                self._ixnet.disconnect()
            except:
                pass
            self._connected = False
            self._connected_remote = None

        for res in self._ixia_resources:
            try:
                IxiaResource.release(res)
            except:
                # this would usually require manual cleanup
                LOG.warn("(IxiaResource) {} release failed".format(res))
        self._ixia_resources.clear()

    def add_chassis(self, chassis_ip=None, timeout=60, default=True, clear=False):
        """
        Add a chassis to the current configuration.
        Wait 'timeout' amount of seconds for the chassis to become 'ready'.

        Args:
            chassis_ip (str|None):
                the IxNetwork chassis IP,
                or None to use the default chassis
            timeout (int):
                amount of seconds to wait until the chassis becomes 'ready'
            default (bool):
                use as the default chassis for interface-related operations
                when specifying card/port
            clear (bool):
                clear existing chassis
                if this session uses load_config,
                then required by the API docs., this flag must be set

        Returns (str):
            the chassis identifier for furthur operations
        """

        if chassis_ip is None:
            chassis_ip = IxiaServerIP.chassis_ip

        LOG.info("Adding Chassis at {}".format(chassis_ip))

        if clear:
            LOG.info("Clearing old chassis (if exist)")
            # required by API docs.: must remove all old chassis from ixncfg if exists
            for chassis in self.getList(self.getRoot()+'/availableHardware', 'chassis'):
                self._ixnet.remove(chassis)

        chassis = self._ixnet.add(self.getRoot()+'availableHardware', 'chassis', '-hostname', chassis_ip)

        self._ixnet.commit()
        chassis = self._ixnet.remapIds(chassis)[0]

        if (default):
            self._chassis = chassis

        # verify the chassis is ready
        succ, val = common.wait_for_val_from_func('ready', timeout, 1,
                                                  self.getAttribute,
                                                  chassis, 'state')
        if not succ:
            raise IxiaError("Chassis is not 'ready' after {} seconds.".format(timeout))

        return chassis

    def clear_port_ownership(self, port, chassis=None):
        """
        Clear a port's ownership.

        Args:
            port (tuple):
                [0] card # on the chassis
                [1] port # on the card
            chassis (str):
                the chassis identifier, or None to use the default

        """
        if chassis is None:
            chassis = self._chassis
        assert chassis is not None, "no default chassis connected"

        card, port = port

        # LOG.info(f"Clearing port: {chassis}/card:{card}/port:{port}")
        LOG.info("Clearing port: " + self.__craft_port_id(card, port, chassis))
        try:
            # self._ixnet.execute('clearOwnership', f"{chassis}/card:{card}/port:{port}")
            self._ixnet.execute('clearOwnership', self.__craft_port_id(card, port, chassis))
        except Exception as err:
            # Unable to release ownership is ok when the configuration is blanked already
            pass

    def connect_ports(self, ports, chassis=None, clear_ownership=True, existing=False, rtn_dict=False):
        """
        Connect physical ports on the chassis to virtual ports.
        In order to use the existing setups from ixncfgs, mark existing=True.

        Args:
            ports (list):
                list of 'port'
                port (tuple):
                    [0] card # on the chassis
                    [1] port # on the card
            chassis (str):
                the chassis identifier, or None to use the default
            clear_ownership (bool):
                clear ports' ownership prior to this operation
            existing (bool):
                whether or not to use existing vports in the configuration
                (instead of creating new vports)
            rtn_dict (bool):
                returns a dictionary mapping, from (card, port) to vport associated

        Returns (list|dict):
            vports created/existed in the configuration now
            the order of vports is the same as specified in 'ports' (ports[i] is assigned to vports[i])
            if rtn_dict is True, return a dictionary from port to vport associated
        """
        if chassis is None:
            chassis = self._chassis
        assert chassis is not None, "no default chassis connected"

        if clear_ownership:
            for port in ports:
                self.clear_port_ownership(port, chassis)

        vports = list()
        if not existing:
            for i in range(len(ports)):
                vport = self._ixnet.add(self.getRoot(), 'vport')
                self._ixnet.commit()
                vport = self._ixnet.remapIds(vport)[0]
                vports.append(vport)
        else:
            vports = self.getList(self.getRoot(), 'vport')

        vport_map = dict()
        for vport, (card, port) in zip(vports, ports):
            vport_map[(card, port)] = vport
            port_id = self.__craft_port_id(card, port, chassis)
            self._port_map[port_id] = vport
            LOG.info("Connecting port: {}, vport = {}".format(port_id, vport))
            self._ixnet.setAttribute(vport, '-connectedTo', port_id)

        LOG.info("Rebooting port(s) (~40s)")
        self._ixnet.commit()

        if rtn_dict:
            return vport_map
        else:
            return vports

    def configure_protocol_interface(self, port, ipv4=None, ipv6=None,
                                     vlan_id=None, mac_address=None,
                                     description=None, chassis=None,
                                     interface=None, create_if_nonexistent=False,
                                     validate=True, validate_timeout=60):
        """
        Configure a Protocol Interface.
        In order to re-configure for an existing interface, specify 'interface='.

        Args:
            port (tuple):
                [0] card # on the chassis
                [1] port # on the card
            ipv4 (tuple|None):
                [0] interface address
                [1] interface gateway
            ipv6 (tuple|None):
                [0] interface address
                [1] interface gateway
            vlan_id (int|None):
                interface VLAN ID, or None to skip vlan configurations
            mac_address (str|None):
                interface mac address, or None to use default
            description (str|None):
                interface description in the configuration, or None to use default
            chassis (str|None):
                the chassis identifier, or None to use the default
            interface (str|None):
                existing interface identifier, or None to create a new one
            create_if_nonexistent (bool):
                default to False, raise IxiaError if the specified interface does not exist
                otherwise, create a new interface instead
            validate (bool):
                validate if the protocol interface is configured correctly
                through ARP/NS
            validate_timeout (int):
                ARP/NS request timeout
                note: arp/ns takes several fetches to refresh the result even when succeeded

        Returns (str):
            the interface identifier
        """
        if interface is None:
            LOG.info("Configuring Protocol Interface: Creating")
        else:
            LOG.info("Configuring Protocol Interface: {}".format(interface))

        if chassis is None:
            chassis = self._chassis
        assert chassis is not None, "no default chassis connected"

        card, port = port
        port_id = self.__craft_port_id(card, port, chassis)

        if description is None:
            description = "{}/{}".format(card, port)

        if interface is None:
            interface = self._ixnet.add(self._port_map[port_id], "interface")
            self._ixnet.commit()
        interface = self.__remapIds(interface)

        # verify if the interface exists
        try:
            self._ixnet.execute('sendArpAndNS', interface)
        except IxNetwork.IxNetError as err:
            if create_if_nonexistent:
                LOG.warn("the specified interface does not exist, creating instead")
                interface = self._ixnet.add(self._port_map[port_id], "interface")
                self._ixnet.commit()
                interface = self.__remapIds(interface)
                LOG.warn("interface created: {}".format(interface))
            else:
                raise IxiaError("specified interface does not exist")
        self.configure(interface, enabled='true', description=description)

        if ipv4 is not None:
            addr, gateway = ipv4
            ipv4_interface = self.__ensure_exist(interface, 'ipv4')[0]
            self.configure(ipv4_interface, gateway=gateway, ip=addr, maskWidth=24)
            ipv4_interface = self.__remapIds(ipv4_interface)

        if ipv6 is not None:
            addr, gateway = ipv6
            ipv6_interface = self.__ensure_exist(interface, 'ipv6')[0]
            self.configure(ipv6_interface, gateway=gateway, ip=addr, maskWidth=64)
            ipv6_interface = self.__remapIds(ipv6_interface)

        if vlan_id is not None:
            vlan_interface = self.__ensure_exist(interface, 'vlan')[0]
            self.configure(vlan_interface, vlanEnable='true', vlanId=str(vlan_id))

        if mac_address is not None:
            self.configure(interface + '/ethernet', macAddress=mac_address)

        LOG.info("Protocol Interface Configuration Complete: {}".format(interface))

        if validate:
            vport = '/'.join(interface.split('/')[:-1])

            def _validate(vport, interface):
                self._ixnet.execute("clearNeighborTable", vport)
                self._ixnet.execute('sendArpAndNS', interface)
                time.sleep(5)
                for neighbor in self.getList(vport, 'discoveredNeighbor'):
                    r, val = common.wait_for_val_from_func(
                        False, 5, 1, self.testAttributes, neighbor, neighborMac="00:00:00:00:00:00")
                    if not r:
                        return False
                    else:
                        LOG.info("{} resolved. MAC: {}".format(vport, self.getAttribute(neighbor, 'neighborMac')))
                return True

            r, val = common.wait_for_val_from_func(True, validate_timeout, 10, _validate, vport, interface)
            if not r:
                raise IxiaError("Protocol Interface Validation Failed, ARP not resolved")
            LOG.info("Protocol Interface Validation Complete: {}".format(interface))
        return interface    # used for configuring traffic item

    def configure(self, obj_ref, commit=True, **kwargs):
        """
        Set an Attribute's value of the obj_ref.

        Args:
            obj_ref (str):
                the identifier for the object
            commit (bool):
                whether or not this change is commited immediately
                (also implicitly commits all previously uncommited configs)
            **kwargs:
                Attribute values to set.
                i.e., attributeName='true'

        """
        LOG.info("configure: {} {}".format(obj_ref, self.__compound_ixargs({}, kwargs)))
        self._ixnet.setMultiAttribute(obj_ref, *self.__compound_ixargs({}, kwargs))
        if commit:
            self._ixnet.commit()

    def duplicate_traffic_item(self, trafficItem, times=1):
        """
        Duplicate a traffic item.

        Args:
            trafficItem (str):
                the identifier of the trafficItem to be duplicated
            times (int):
                number of times to duplicate

        Returns (list):
            newly created trafficItems from duplication

        """
        old_items = self.getList(self.getRoot()+'/traffic', 'trafficItem')
        self._ixnet.execute("duplicate", trafficItem, times)
        new_items = self.getList(self.getRoot()+'/traffic', 'trafficItem')
        for item in old_items:
            new_items.remove(item)
        return new_items

    def create_traffic_item(self, trafficItem, trackBy, endpointSets, configElements):
        """
        Create a traffic item.

        Args:
            trafficItem (dict):
                attributes to configure in the newly created traffic item,
                merging default options with override.
                see ._show(traffic_obj) for available attributes
            trackBy (list):
                tracking options list,
                see ._show(traffic_obj + '/tracking') for available options
            endpointSets (list):
                list of dict
                    attributes to configure in the newly created endpoint set,
                    see ._show(endp_obj) for available attributes
            configElements (list):
                list of
                    {child: {attribute: value}}
                specified in the same order as endpointSets
                see ._show(ce_obj) for available children
                see ._show(ce_obj+'/'+child) for available attributes
                see ._help(ce_obj+'/'+child, '-'+attribute) for available options

        Returns (tuple):
            tuple(traffic_obj, [tuple(endp_obj, ce_obj), ..])
            traffic_obj (str):
                the traffic item identifier
            endp_obj (str):
                the endpointSet identifier
            ce_obj (str):
                the associate configElement identifier for the endpointSet
        """
        LOG.info("Creating Traffic Item")
        traffic_obj = self._ixnet.add(self.getRoot() + '/traffic', 'trafficItem')

        default_args = {
            'enabled': 'True',
            'trafficItemType': 'l2L3',
            'routeMesh': 'oneToOne',
            'srcDestMesh': 'oneToOne',
            'transmitMode': 'interleaved',
            'trafficType': 'ipv4',
            'biDirectional': '1'
        }

        self.configure(traffic_obj, **self.__merge_dict(default_args, trafficItem))
        traffic_obj = self.__remapIds(traffic_obj)

        endp_pairs = list()
        for endp, ce in zip(endpointSets, configElements):
            endp_obj, ce_obj = self.create_endpoint_set(traffic_obj, endp)
            endp_pairs.append((endp_obj, ce_obj))

            for k, v in ce.items():
                # commit together
                self.configure(ce_obj + '/' + k, commit=False, **self.__merge_dict({}, v))

            self._ixnet.commit()

        self._ixnet.setAttribute(traffic_obj + '/tracking', '-trackBy', trackBy)
        self._ixnet.commit()

        self.traffic_regenerate(traffic_obj)

        LOG.info("Traffic Item Creation Complete: {}".format(traffic_obj))
        return traffic_obj, endp_pairs

    def create_endpoint_set(self, trafficItem, endp={}):
        """
        Create an endpointSet according to 'endp' under a trafficItem

        Args:
            trafficItem (str):
                the traffic item to attach to
            endp (dict):
                attributes to configure in the newly created endpoint set,
                see ._show(endp_obj) for available attributes

        Returns (tuple):
            endpointSet, configElement

        """
        endp_obj = self._ixnet.add(trafficItem, 'endpointSet', *self.__compound_ixargs({}, endp))
        self._ixnet.commit()
        endp_obj = self.__remapIds(endp_obj)
        ce_obj = trafficItem + '/configElement:' + endp_obj[endp_obj.rindex(':')+1:]
        return endp_obj, ce_obj

    def configure_endpoint_set(self, endpointSet, sources=[], destinations=[], append=True):
        """
        Configure an existing endpointSet in a trafficItem

        Args:
            endpointSet (str):
                the endpoint set to be modified
                get a list of available endpointSets through .getList(trafficItem, 'endpointSet')
            sources (list):
                source endpoints (interface)
            destinations (list):
                destination endpoints (interface)
            append (bool):
                if appending to existing endpoints in the endpoint set

        Returns (None)

        Note:
            the traffic item shall be regenerated
            assuming only using -sources and -destinations
            (multicast and scalable are not supported here, use .configure instead)
            if append=False, this is equivalent to session.configure
        """
        if append:
            current = set(self.getAttribute(endpointSet, 'sources'))
            current.update(sources)
        else:
            current = sources
        self.configure(endpointSet, sources=list(current))

        if append:
            current = set(self.getAttribute(endpointSet, 'destinations'))
            current.update(destinations)
        else:
            current = destinations
        self.configure(endpointSet, destinations=list(current))

    def traffic_regenerate(self, trafficItem=None):
        """
        Regenerate (a) traffic item(s).

        Args:
            trafficItem (str|None):
                the traffic item to regenerate
                use None to regenerate all traffic items
        """
        if trafficItem is None:
            LOG.info("Regenerating all trafficItems")
            for trafficItem in self._ixnet.getList(self.getRoot()+'/traffic', 'trafficItem'):
                self._ixnet.execute('generate', trafficItem)
        else:
            LOG.info("Regenerating trafficItem: {}".format(trafficItem))
            self._ixnet.execute('generate', trafficItem)

    def traffic_apply(self):
        """
        Apply all traffic items to hardware.
        """
        LOG.info("Applying all traffic to hardware")
        self._ixnet.execute('apply', self.getRoot() + 'traffic')

    def traffic_apply_live(self):
        """
        Apply all traffic items to hardware while the traffic is running.
        Only highLevelStream configurations are applied. (not from configElement)
        """
        LOG.info("Applying changes to live traffic")
        traffic = self.getRoot()+'/traffic'
        self._ixnet.execute('applyOnTheFlyTrafficChanges', traffic)

    def traffic_start(self, regenerate=True, apply=True, timeout=60):
        """
        Start all traffic items.
        Wait 'timeout' amount of seconds for the traffic to become 'started'.

        Args:
            regenerate (bool):
                regenerate all traffic items prior to starting
            apply (bool):
                apply all traffic items prior to starting
            timeout (int):
                amount of seconds to wait for the traffic to become 'started'
        """
        if regenerate:
            self.traffic_regenerate()
        if apply:
            self.traffic_apply()
        traffic = self.getRoot()+'/traffic'
        LOG.info("Starting all traffic")
        self._ixnet.execute('start', traffic)

        succ, val = common.wait_for_val_from_func("started", timeout, 1, self.getAttribute, traffic, 'state')
        if not succ:
            raise IxiaError("Traffic cannot become 'started' after {} seconds. state={}".format(timeout, val))

    def traffic_stop(self, timeout=60):
        """
        Stop all traffic items.
        Wait 'timeout' amount of seconds for the traffic to become 'stopped'.

        Args:
            timeout (int):
                amount of seconds to wait for the traffic to become 'stopped'
        """
        traffic = self.getRoot()+'/traffic'
        LOG.info("Stopping all traffic")
        self._ixnet.execute('stop', traffic)

        succ, val = common.wait_for_val_from_func("stopped", timeout, 1, self.getAttribute, traffic, 'state')
        if not succ:
            raise IxiaError("Traffic cannot become 'stopped' after {} seconds. state={}".format(timeout, val))

    def clear(self):
        """
        Clear the current configuration.
        i.e. replace with a empty new one
        """
        LOG.info("Clearing current configuration")
        self._ixnet.execute('newConfig')

    def _show(self, obj_ref):
        """
        Show the configurations for obj_ref, including children and attributes.

        Returns (str):
            the configurations for obj_ref

        Warning:
            this is not exposed in the IxNetwork package, but available in Tcl API set.
            might be removed in the future
        """
        return self._ixnet._IxNet__SendRecv("ixNet", "show", obj_ref)

    def load_config(self, filename, from_server=True):
        """
        Load an ixncfg for this session.
        Must re-add chassis with clear=True required by the API.

        Args:
            filename (str):
                the filename to be loaded as an ixncfg
            from_server (bool):
                whether or not the file is located on the server
                (currently loading from the client is not supported)
        """
        LOG.info("configuration={}".format(filename))
        if from_server:
            self._ixnet.execute("loadConfig", self._ixnet.readFrom(filename, "-ixNetRelative"))
        else:
            # fails on server side, possibly due to API not supported in 8.10 EA
            self._ixnet.execute("loadConfig", self._ixnet.readFrom(filename))

    def getAttribute(self, obj_ref, name):
        """
        Get an attribute's value from obj_ref.
        under certain scenarios, this operation block forever due to recv.

        Args:
            obj_ref (str):
                the identifier for the object
            name (str):
                the name of the attribute

        Returns (str|list):
            the value stored in the attribute
            bool attributes are repr. in "true" or "false"
        """
        if name and name[0] != '-':
            name = '-' + name
        return self._ixnet.getAttribute(obj_ref, name)

    def testAttributes(self, obj_ref, **kwargs):
        """
        Test whether or not all the attributes are matching.
        under certain scenarios, this operation block forever due to recv.

        Args:
            obj_ref (str):
                the identifier for the object
            **kwargs (dict):
                attributeName==attributeValue
                to be tested

        Returns (bool):
            whether or not all the attributes are matching the desired values
        """
        return all([self.getAttribute(obj_ref, k) == v for k, v in kwargs.items()])

    def getList(self, *args, **kwargs):
        """
        Forwarding the Tcl API for getList.
        see Tcl API Guide for more details.
        """
        return self._ixnet.getList(*args, **kwargs)

    def getRoot(self):
        """
        Forwarding the Tcl API for help.
        see Tcl API Guide for more details.
        """
        return self._ixnet.getRoot()

    def _help(self, *args, **kwargs):
        """
        Forwarding the Tcl API for help.
        see Tcl API Guide for more details.
        """
        return self._ixnet.help(*args, **kwargs)

    def get_hls(self, trafficItem, **kwargs):
        """
        Get highLevelStreams, filtered by **kwargs.

        Args:
            trafficItem (str):
                the traffic item identifer
            **kwargs (dict):
                key:
                    the hls' attributeName
                value:
                    the desired hls' attributeValue

        Returns (generator):
            generator of str
            filtered highLevelStream identifiers

        Note:
            runtime adjustments could only be made through hls
        """

        # return filter(
        #               (lambda hls: all(map((lambda kv: self.getAttribute(hls, kv[0]) == kv[1]), kwargs.items()))),
        #               self.getList(trafficItem, "highLevelStream"))

        for hls in self.getList(trafficItem, "highLevelStream"):
            desired = True
            for k, v in kwargs.items():
                if self.getAttribute(hls, k) != v:
                    desired = False
                    break
            if desired:
                yield hls

    def _statistics_views(self):
        """
        Get all statistics views' identifiers.

        Returns (list):
            list of all statistics views' identifiers, in str
        """
        return self.getList(self.getRoot()+'/statistics', 'view')

    def get_statistics(self, view, timeout=10, fail_ok=True):
        """
        Get the data in the statistics view.
        certain views causes getAttribute to block forever due to recv.

        Args:
            view (str):
                the view to look at, or the view identifier
                this could just be the view name as in the GUI,
                implicitly matched with list of identifiers
                (not case sensitive)
            timeout (int):
                amount of time to wait until the view become ready
            fail_ok (bool):
                does not raise an IxiaError after timeout if set

        Returns (list|None):
            list of 'row's (dict) in the view
                row:
                    key: column name
                    value: value
            or None if 'view' cannot be matched with a view identifier
            or None if fail_ok=True and timeout occurred and no other match possible
        """
        for view_obj in self._statistics_views():
            if view.lower() not in view_obj.lower():
                continue

            view = view_obj

            LOG.info("matched with view {}".format(view))

            self._ixnet.execute("refresh", view)
            time.sleep(1)
            succ, val = common.wait_for_val_from_func('true', timeout, 1, self.getAttribute, view+"/page", 'isReady')
            if not succ:
                msg = "timeout occurred when waiting for view {} to become ready. isReady={}".format(view, val)
                if fail_ok:
                    LOG.warn(msg)
                    continue
                raise IxiaError(msg)

            # return [dict(zip(self.getAttribute(view+'/page', 'columnCaptions'), row))
            #         for row in self.getAttribute(view+'/page', 'rowValues')[0]]

            result = list()
            for row in self.getAttribute(view+'/page', 'rowValues'):
                result.append(dict(zip(self.getAttribute(view+'/page', 'columnCaptions'), row[0])))
            return result

        return None

    @staticmethod
    def wait_for_stable_value_from_func(func, *args, timeout=300, interval=10, **kwargs):
        val = func(*args, **kwargs)

        prev_val = val
        end_time = time.time() + timeout
        while time.time() < end_time:
            time.sleep(interval)
            val = func(*args, **kwargs)
            if val == prev_val:
                return True, val
            prev_val = val

        return False, val

    def get_frames_delta(self, name=None, stable=False, timeout=300, interval=10):
        """
        Equiv. to int(.get_statistics('traffic item statistics', fail_ok=False)[0]["Frames Delta"]) if stable=False
        otherwise, this functions ensures the delta value is not changed before and after the interval
        For tests with multiple traffic items, use wait_for_stable_value_from_func for stable=True

        Args:
            name (str|None):
                traffic item name
                if None, returns the 0th entry
            stable (bool):
                if True, ensures the delta values is not changed in between two fetches
            timeout (int):
                max. time to wait for the delta to become stable
                used only if stable=True

        Returns (int):
            int(.get_statistics('traffic item statistics', fail_ok=False)[0]['Frames Delta'])
        """
        def _get_delta():
            if name is None:
                delta = int(self.get_statistics('traffic item statistics', fail_ok=False)[0]['Frames Delta'])
            else:
                items = self.get_statistics('traffic item statistics', fail_ok=False)
                for item in items:
                    item_name = item['Traffic Item']
                    if name == item_name:
                        delta = int(item['Frames Delta'])
                        break
                else:
                    raise ValueError("{} is not found in traffic item statistics".format(name))
            LOG.info("Frames Delta={}".format(delta))
            return delta
        if not stable:
            return _get_delta()
        succ, val = self.wait_for_stable_value_from_func(_get_delta, timeout=timeout, interval=interval)
        if not succ:
            raise IxiaError("frames delta did not become stable after timeout")
        return val
