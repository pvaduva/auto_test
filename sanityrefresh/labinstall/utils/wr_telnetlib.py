r"""TELNET client class.

Based on RFC 854: TELNET Protocol Specification, by J. Postel and
J. Reynolds

Example:

>>> from telnetlib import Telnet
>>> tn = Telnet('www.python.org', 79)   # connect to finger port
>>> tn.write(b'guido\r\n')
>>> print(tn.read_all())
Login       Name               TTY         Idle    When    Where
guido    Guido van Rossum      pts/2        <Dec  2 11:10> snag.cnri.reston..

>>>

Note that read_all() won't read until eof -- it just reads some data
-- but it guarantees to read at least one byte unless EOF is hit.

It is possible to pass a Telnet object to a selector in order to wait until
more data is available.  Note that in this case, read_eager() may return b''
even if there was data on the socket, because the protocol negotiation may have
eaten the data.  This is why EOFError is needed in some cases to distinguish
between "no data" and "connection closed" (since the socket also appears ready
for reading when it is closed).

To do:
- option negotiation
- timeout should be intrinsic to the connection object instead of an
  option on one of the read calls only

"""

'''
modification history:
---------------------
08nov15,kav  Merged in modifications from WASSP version:
             wassp-repos/wassp/host/htee/targetControl/Utils/wr_telnetlib.py
             into /usr/lib/python3.4/telnetlib.py
             Key mods contain support for:
             (a) echoing text or writing text to a log file
             (b) Telnet negotiation and VT100 Device Query required to view
                 and interact with HP380 when it boots up
             See comments entitled "mod begins" and "mod ends" below.
             Additional functions have also been added. See comments entitled
             "new functions begin" and "new functions end" below.
             Diff with python3.4 version to see changes.
'''

# Imported modules
import os
import pdb
import sys
import re
import time
import socket
import selectors
try:
    from time import monotonic as _time
except ImportError:
    from time import time as _time

from constants import *
from .common import remove_markers
from .log import getLogger
from utils.common import wr_exit

log = getLogger(__name__)

__all__ = ["Telnet"]

# Tunable parameters
DEBUGLEVEL = 0

# Telnet protocol defaults
TELNET_PORT = 23

# Telnet protocol characters (don't change)
IAC  = bytes([255]) # "Interpret As Command"
DONT = bytes([254])
DO   = bytes([253])
WONT = bytes([252])
WILL = bytes([251])
theNULL = bytes([0])

SE  = bytes([240])  # Subnegotiation End
NOP = bytes([241])  # No Operation
DM  = bytes([242])  # Data Mark
BRK = bytes([243])  # Break
IP  = bytes([244])  # Interrupt process
AO  = bytes([245])  # Abort output
AYT = bytes([246])  # Are You There
EC  = bytes([247])  # Erase Character
EL  = bytes([248])  # Erase Line
GA  = bytes([249])  # Go Ahead
SB =  bytes([250])  # Subnegotiation Begin


# VT100 values
ESC = bytes([27]) # Escape character
VT100_DEVICE_STATUS = bytes([27,91,53,110]) # Device Status Query
VT100_DEVICE_OK = bytes([27,91,48,110]) # Device OK

# Telnet protocol options code (don't change)
# These ones all come from arpa/telnet.h
BINARY = bytes([0]) # 8-bit data path
ECHO = bytes([1]) # echo
RCP = bytes([2]) # prepare to reconnect
SGA = bytes([3]) # suppress go ahead
NAMS = bytes([4]) # approximate message size
STATUS = bytes([5]) # give status
TM = bytes([6]) # timing mark
RCTE = bytes([7]) # remote controlled transmission and echo
NAOL = bytes([8]) # negotiate about output line width
NAOP = bytes([9]) # negotiate about output page size
NAOCRD = bytes([10]) # negotiate about CR disposition
NAOHTS = bytes([11]) # negotiate about horizontal tabstops
NAOHTD = bytes([12]) # negotiate about horizontal tab disposition
NAOFFD = bytes([13]) # negotiate about formfeed disposition
NAOVTS = bytes([14]) # negotiate about vertical tab stops
NAOVTD = bytes([15]) # negotiate about vertical tab disposition
NAOLFD = bytes([16]) # negotiate about output LF disposition
XASCII = bytes([17]) # extended ascii character set
LOGOUT = bytes([18]) # force logout
BM = bytes([19]) # byte macro
DET = bytes([20]) # data entry terminal
SUPDUP = bytes([21]) # supdup protocol
SUPDUPOUTPUT = bytes([22]) # supdup output
SNDLOC = bytes([23]) # send location
TTYPE = bytes([24]) # terminal type
EOR = bytes([25]) # end or record
TUID = bytes([26]) # TACACS user identification
OUTMRK = bytes([27]) # output marking
TTYLOC = bytes([28]) # terminal location number
VT3270REGIME = bytes([29]) # 3270 regime
X3PAD = bytes([30]) # X.3 PAD
NAWS = bytes([31]) # window size
TSPEED = bytes([32]) # terminal speed
LFLOW = bytes([33]) # remote flow control
LINEMODE = bytes([34]) # Linemode option
XDISPLOC = bytes([35]) # X Display Location
OLD_ENVIRON = bytes([36]) # Old - Environment variables
AUTHENTICATION = bytes([37]) # Authenticate
ENCRYPT = bytes([38]) # Encryption option
NEW_ENVIRON = bytes([39]) # New - Environment variables
# the following ones come from
# http://www.iana.org/assignments/telnet-options
# Unfortunately, that document does not assign identifiers
# to all of them, so we are making them up
TN3270E = bytes([40]) # TN3270E
XAUTH = bytes([41]) # XAUTH
CHARSET = bytes([42]) # CHARSET
RSP = bytes([43]) # Telnet Remote Serial Port
COM_PORT_OPTION = bytes([44]) # Com Port Control Option
SUPPRESS_LOCAL_ECHO = bytes([45]) # Telnet Suppress Local Echo
TLS = bytes([46]) # Telnet Start TLS
KERMIT = bytes([47]) # KERMIT
SEND_URL = bytes([48]) # SEND-URL
FORWARD_X = bytes([49]) # FORWARD_X
PRAGMA_LOGON = bytes([138]) # TELOPT PRAGMA LOGON
SSPI_LOGON = bytes([139]) # TELOPT SSPI LOGON
PRAGMA_HEARTBEAT = bytes([140]) # TELOPT PRAGMA HEARTBEAT
EXOPL = bytes([255]) # Extended-Options-List
NOOPT = bytes([0])


# poll/select have the advantage of not requiring any extra file descriptor,
# contrarily to epoll/kqueue (also, they require a single syscall).
if hasattr(selectors, 'PollSelector'):
    _TelnetSelector = selectors.PollSelector
else:
    _TelnetSelector = selectors.SelectSelector


class Telnet:

    """Telnet interface class.

    An instance of this class represents a connection to a telnet
    server.  The instance is initially not connected; the open()
    method must be used to establish a connection.  Alternatively, the
    host name and optional port number can be passed to the
    constructor, too.

    Don't try to reopen an already connected instance.

    This class has many read_*() methods.  Note that some of them
    raise EOFError when the end of the connection is read, because
    they can return an empty string for other reasons.  See the
    individual doc strings.

    read_until(expected, [timeout])
        Read until the expected string has been seen, or a timeout is
        hit (default is no timeout); may block.

    read_all()
        Read all data until EOF; may block.

    read_some()
        Read at least one byte or EOF; may block.

    read_very_eager()
        Read all data available already queued or on the socket,
        without blocking.

    read_eager()
        Read either data already queued or some data available on the
        socket, without blocking.

    read_lazy()
        Read all data in the raw queue (processing it first), without
        doing any socket I/O.

    read_very_lazy()
        Reads all data in the cooked queue, without doing any socket
        I/O.

    read_sb_data()
        Reads available data between SB ... SE sequence. Don't block.

    set_option_negotiation_callback(callback)
        Each time a telnet option is read on the input flow, this callback
        (if set) is called with the following parameters :
        callback(telnet socket, command, option)
            option will be chr(0) when there is no option.
        No other action is done afterwards by telnetlib.

    """

    def __init__(self, host=None, port=0,
                 timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
                 negotiate=False, vt100query=False, logfile=None):
        """Constructor.

        When called without arguments, create an unconnected instance.
        With a hostname argument, it connects the instance; port number
        and timeout are optional.
        """
        self.debuglevel = DEBUGLEVEL
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.rawq = b''
        self.irawq = 0
        self.cookedq = b''
        self.eof = 0
        self.iacseq = b'' # Buffer for IAC sequence.
        #-- mod begins
        self.negotiate = negotiate
        self.vt100query = vt100query
        if self.vt100query:
            self.vt100querybuffer = b'' # Buffer for VT100 queries
            #-- mod ends
        self.sb = 0 # flag for SB and SE sequence.
        self.sbdataq = b''
        self.option_callback = None
        #-- mod begins
        self.logfile = logfile
        self.echo = None
        #-- mod ends
        if host is not None:
            self.open(host, port, timeout)

    def open(self, host, port=0, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        """Connect to a host.

        The optional second argument is the port number, which
        defaults to the standard telnet port (23).

        Don't try to reopen an already connected instance.
        """
        self.eof = 0
        if not port:
            port = TELNET_PORT
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = socket.create_connection((host, port), timeout)

    def __del__(self):
        """Destructor -- close the connection."""
        self.close()

    def msg(self, msg, *args):
        """Print a debug message, when the debug level is > 0.

        If extra arguments are present, they are substituted in the
        message using the standard string formatting operator.

        """
        if self.debuglevel > 0:
            print('Telnet(%s,%s):' % (self.host, self.port), end=' ')
            if args:
                print(msg % args)
            else:
                print(msg)

    def set_debuglevel(self, debuglevel):
        """Set the debug level.

        The higher it is, the more debug output you get (on sys.stdout).

        """
        self.debuglevel = debuglevel

    def close(self):
        """Close the connection."""
        if self.sock:
            #self.sock.shutdown()
            self.sock.close()
        self.sock = 0
        self.eof = 1
        self.iacseq = b''
        self.sb = 0

    def get_socket(self):
        """Return the socket object used internally."""
        return self.sock

    def fileno(self):
        """Return the fileno() of the socket object used internally."""
        return self.sock.fileno()

    def write(self, buffer):
        """Write a string to the socket, doubling any IAC characters.

        Can block if the connection is blocked.  May raise
        OSError if the connection is closed.

        """
        if IAC in buffer:
            buffer = buffer.replace(IAC, IAC+IAC)
        self.msg("send %r", buffer)
        self.sock.sendall(buffer)
        return buffer

    def read_until(self, match, timeout=None):
        """Read until a given string is encountered or until timeout.

        When no match is found, return whatever is available instead,
        possibly the empty string.  Raise EOFError if the connection
        is closed and no cooked data is available.

        """
        n = len(match)
        self.process_rawq()
        i = self.cookedq.find(match)
        if i >= 0:
            i = i+n
            buf = self.cookedq[:i]
            self.cookedq = self.cookedq[i:]
            return buf
        if timeout is not None:
            deadline = _time() + timeout
        with _TelnetSelector() as selector:
            selector.register(self, selectors.EVENT_READ)
            while not self.eof:
                if selector.select(timeout):
                    i = max(0, len(self.cookedq)-n)
                    self.fill_rawq()
                    self.process_rawq()
                    i = self.cookedq.find(match, i)
                    if i >= 0:
                        i = i+n
                        buf = self.cookedq[:i]
                        self.cookedq = self.cookedq[i:]
                        return buf
                if timeout is not None:
                    timeout = deadline - _time()
                    if timeout < 0:
                        break
        return self.read_very_lazy()

    def read_all(self):
        """Read all data until EOF; block until connection closed."""
        self.process_rawq()
        while not self.eof:
            self.fill_rawq()
            self.process_rawq()
        buf = self.cookedq
        self.cookedq = b''
        return buf

    def read_some(self):
        """Read at least one byte of cooked data unless EOF is hit.

        Return b'' if EOF is hit.  Block if no data is immediately
        available.

        """
        self.process_rawq()
        while not self.cookedq and not self.eof:
            self.fill_rawq()
            self.process_rawq()
        buf = self.cookedq
        self.cookedq = b''
        return buf

    def read_very_eager(self):
        """Read everything that's possible without blocking in I/O (eager).

        Raise EOFError if connection closed and no cooked data
        available.  Return b'' if no cooked data available otherwise.
        Don't block unless in the midst of an IAC sequence.

        """
        self.process_rawq()
        while not self.eof and self.sock_avail():
            self.fill_rawq()
            self.process_rawq()
        return self.read_very_lazy()

    def read_eager(self):
        """Read readily available data.

        Raise EOFError if connection closed and no cooked data
        available.  Return b'' if no cooked data available otherwise.
        Don't block unless in the midst of an IAC sequence.

        """
        self.process_rawq()
        while not self.cookedq and not self.eof and self.sock_avail():
            self.fill_rawq()
            self.process_rawq()
        return self.read_very_lazy()

    def read_lazy(self):
        """Process and return data that's already in the queues (lazy).

        Raise EOFError if connection closed and no data available.
        Return b'' if no cooked data available otherwise.  Don't block
        unless in the midst of an IAC sequence.

        """
        self.process_rawq()
        return self.read_very_lazy()

    def read_very_lazy(self):
        """Return any data available in the cooked queue (very lazy).

        Raise EOFError if connection closed and no data available.
        Return b'' if no cooked data available otherwise.  Don't block.

        """
        buf = self.cookedq
        self.cookedq = b''
        if not buf and self.eof and not self.rawq:
            raise EOFError('telnet connection closed')
        return buf

    def read_sb_data(self):
        """Return any data available in the SB ... SE queue.

        Return b'' if no SB ... SE available. Should only be called
        after seeing a SB or SE command. When a new SB command is
        found, old unread SB data will be discarded. Don't block.

        """
        buf = self.sbdataq
        self.sbdataq = b''
        return buf

    def set_option_negotiation_callback(self, callback):
        """Provide a callback function called after each receipt of a telnet option."""
        self.option_callback = callback

    def process_rawq(self):
        """Transfer from raw queue to cooked queue.

        Set self.eof when connection is closed.  Don't block unless in
        the midst of an IAC sequence.

        """
        buf = [b'', b'']
        try:
            while self.rawq:
                c = self.rawq_getchar()
                if not self.iacseq:
                    if c == theNULL:
                        continue
                    if c == b"\021":
                        continue
                        #-- mod begins
                    # deal with vt100 escape sequences
                    if self.vt100query:
                        if self.vt100querybuffer:
                           self.vt100querybuffer += c
                           if len(self.vt100querybuffer) > 10:
                               self.vt100querybuffer = b'' # too long, ignore
                           elif self.vt100querybuffer == VT100_DEVICE_STATUS:
                               self.sock.sendall(VT100_DEVICE_OK)
                               self.vt100querybuffer = b''
                        if not self.vt100querybuffer and c == ESC:
                           self.vt100querybuffer += c
                    # deal with IAC sequences
                    #-- mod ends
                    if c != IAC:
                        buf[self.sb] = buf[self.sb] + c
                        continue
                    else:
                        self.iacseq += c
                elif len(self.iacseq) == 1:
                    # 'IAC: IAC CMD [OPTION only for WILL/WONT/DO/DONT]'
                    if c in (DO, DONT, WILL, WONT):
                        self.iacseq += c
                        continue

                    self.iacseq = b''
                    if c == IAC:
                        buf[self.sb] = buf[self.sb] + c
                    else:
                        if c == SB: # SB ... SE start.
                            self.sb = 1
                            self.sbdataq = b''
                        elif c == SE:
                            self.sb = 0
                            self.sbdataq = self.sbdataq + buf[1]
                            buf[1] = b''
                        if self.option_callback:
                            # Callback is supposed to look into
                            # the sbdataq
                            self.option_callback(self.sock, c, NOOPT)
                        else:
                            # We can't offer automatic processing of
                            # suboptions. Alas, we should not get any
                            # unless we did a WILL/DO before.
                            self.msg('IAC %d not recognized' % ord(c))
                elif len(self.iacseq) == 2:
                    cmd = self.iacseq[1:2]
                    self.iacseq = b''
                    opt = c
                    if cmd in (DO, DONT):
                        self.msg('IAC %s %d',
                            cmd == DO and 'DO' or 'DONT', ord(opt))
                        if self.option_callback:
                            self.option_callback(self.sock, cmd, opt)
                        else:
                            #-- mod begins
                            if self.negotiate:
                                # do some limited logic to use SGA if asked
                                if cmd == DONT and opt == SGA:
                                   self.sock.sendall(IAC + WILL + opt)
                                elif cmd == DO and opt == SGA:
                                   self.sock.sendall(IAC + WILL + opt)
                                else:
                                   self.sock.sendall(IAC + WONT + opt)
                            else:
                                #-- mod ends
                                self.sock.sendall(IAC + WONT + opt)
                    elif cmd in (WILL, WONT):
                        self.msg('IAC %s %d',
                            cmd == WILL and 'WILL' or 'WONT', ord(opt))
                        if self.option_callback:
                            self.option_callback(self.sock, cmd, opt)
                        else:
                            #-- mod begins
                            if self.negotiate:
                                # do some limited logic to use SGA if asked
                                if cmd == WONT and opt == SGA:
                                   self.sock.sendall(IAC + DO + opt)
                                elif cmd == WILL and opt == SGA:
                                   self.sock.sendall(IAC + DO + opt)
                                elif cmd == WILL and opt == ECHO:
                                   self.sock.sendall(IAC + DO + opt)
                                else:
                                   self.sock.sendall(IAC + DONT + opt)
                            else:
                                #-- mod ends
                                self.sock.sendall(IAC + DONT + opt)
        except EOFError: # raised by self.rawq_getchar()
            self.iacseq = b'' # Reset on EOF
            self.sb = 0
            pass
        self.cookedq = self.cookedq + buf[0]
        #-- mod begins
        self.log_write(buf[0])
        if self.echo:
            self.echo.write(buf[0].decode('utf-8', 'ignore'))
            #-- mod ends
        self.sbdataq = self.sbdataq + buf[1]

    def rawq_getchar(self):
        """Get next char from raw queue.

        Block if no data is immediately available.  Raise EOFError
        when connection is closed.

        """
        if not self.rawq:
            self.fill_rawq()
            if self.eof:
                raise EOFError
        c = self.rawq[self.irawq:self.irawq+1]
        self.irawq = self.irawq + 1
        if self.irawq >= len(self.rawq):
            self.rawq = b''
            self.irawq = 0
        return c

    def fill_rawq(self):
        """Fill raw queue from exactly one recv() system call.

        Block if no data is immediately available.  Set self.eof when
        connection is closed.

        """
        if self.irawq >= len(self.rawq):
            self.rawq = b''
            self.irawq = 0
        # The buffer size should be fairly small so as to avoid quadratic
        # behavior in process_rawq() above
        buf = self.sock.recv(50)
        self.msg("recv %r", buf)
        self.eof = (not buf)
        self.rawq = self.rawq + buf

    def sock_avail(self):
        """Test whether data is available on the socket."""
        with _TelnetSelector() as selector:
            selector.register(self, selectors.EVENT_READ)
            return bool(selector.select(0))

    def interact(self):
        """Interaction function, emulates a very dumb telnet client."""
        if sys.platform == "win32":
            self.mt_interact()
            return
        with _TelnetSelector() as selector:
            selector.register(self, selectors.EVENT_READ)
            selector.register(sys.stdin, selectors.EVENT_READ)

            while True:
                for key, events in selector.select():
                    if key.fileobj is self:
                        try:
                            text = self.read_eager()
                        except EOFError:
                            print('*** Connection closed by remote host ***')
                            return
                        if text:
                            sys.stdout.write(text.decode('ascii'))
                            sys.stdout.flush()
                    elif key.fileobj is sys.stdin:
                        line = sys.stdin.readline().encode('ascii')
                        if not line:
                            return
                        self.write(line)

    def mt_interact(self):
        """Multithreaded version of interact()."""
        import _thread
        _thread.start_new_thread(self.listener, ())
        while 1:
            line = sys.stdin.readline()
            if not line:
                break
                #-- mod begins
            self.write(line)
            #-- mod ends

    def listener(self):
        """Helper for mt_interact() -- this executes in the other thread."""
        while 1:
            try:
                data = self.read_eager()
            except EOFError:
                print('*** Connection closed by remote host ***')
                return
            if data:
                #-- mod begins
                sys.stdout.write(data)
                #-- mod ends
            else:
                sys.stdout.flush()

    def expect(self, list, timeout=None):
        """Read until one from a list of a regular expressions matches.

        The first argument is a list of regular expressions, either
        compiled (re.RegexObject instances) or uncompiled (strings).
        The optional second argument is a timeout, in seconds; default
        is no timeout.

        Return a tuple of three items: the index in the list of the
        first regular expression that matches; the match object
        returned; and the text read up till and including the match.

        If EOF is read and no text was read, raise EOFError.
        Otherwise, when nothing matches, return (-1, None, text) where
        text is the text received so far (may be the empty string if a
        timeout happened).

        If a regular expression ends with a greedy match (e.g. '.*')
        or if more than one expression can match the same input, the
        results are undeterministic, and may depend on the I/O timing.

        """
        re = None
        list = list[:]
        indices = range(len(list))
        for i in indices:
            if not hasattr(list[i], "search"):
                if not re: import re
                list[i] = re.compile(list[i])
        if timeout is not None:
            deadline = _time() + timeout
        with _TelnetSelector() as selector:
            selector.register(self, selectors.EVENT_READ)
            while not self.eof:
                self.process_rawq()
                for i in indices:
                    m = list[i].search(self.cookedq)
                    if m:
                        e = m.end()
                        text = self.cookedq[:e]
                        self.cookedq = self.cookedq[e:]
                        return (i, m, text)
                if timeout is not None:
                    ready = selector.select(timeout)
                    timeout = deadline - _time()
                    if not ready:
                        if timeout < 0:
                            break
                        else:
                            continue
                self.fill_rawq()
        text = self.read_very_lazy()
        if not text and self.eof:
            raise EOFError
        return (-1, None, text)

        #-- mod begins

    def log_write(self, text):
        if not text:
            return

        try:
            if not isinstance(text,str):
                text = text.decode('utf-8','ignore')
        except AttributeError as e:
            print ('log_write exception: ', e)
            pass

        if self.logfile:
            try:
                self.logfile.write(text)
                self.logfile.flush()
            except UnicodeEncodeError:
                # Commented out to prevent the log from filling up with
                # these messages when a node is being installed
                #print(' following text caused a UNICODE ENCODE ERROR ')
                pass
                #-- mod ends

                #-- new functions begin

    def write_line(self, text):
        """Wrapper for write().
           Writes text followed by line separator in utf-8 encoding.
           Fails if error occurred during write.
        """

        try:
            self.write(str.encode(text + "\n"))
        except OSError:
            msg = "Failed to write to Telnet socket (connection could be closed): {}:{}".format(self.host, self.port)
            log.exception(msg)
            wr_exit()._exit(1, msg)

    def get_read_until(self, expected, timeout=TELNET_EXPECT_TIMEOUT):
        """Wrapper for read_until().
           Returns text in utf-8 encoding.
           Fails if given string is not found or if EOF is encountered.
        """
        log.info("Looking for: {}".format(expected))
        try:
            output = self.read_until(str.encode(expected), timeout)
        except EOFError:
            msg = "Connection closed: Reached EOF and no data was read in Telnet session: {}:{}.".format(self.host, self.port)
            log.info(msg)
            wr_exit()._exit(1, msg)

        output = output.decode('utf-8', 'ignore')
        if expected not in output:
            msg = 'Timeout occurred: Failed to find \"{}\" in output. Output:\n{}'.format(expected, output)
            log.info(msg)
            wr_exit()._exit(1, msg)
        else:
            log.info("Found expected text")

        lines = output.splitlines()
        # Remove command
        start = 1
        if len(lines) > 2:
            # Remove prompt
            end = -1
        else:
            end = None
        output = "\n".join(output.splitlines()[start:end])

        return output

    def find_prompt(self, timeout=TELNET_EXPECT_TIMEOUT):
        """Matches against prompt regex.

           Returns output matched up to prompt.
        """
        try:
            result = self.expect([str.encode(PROMPT)], timeout)
            index = result[0]
            output = result[2]
        except EOFError:
            msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
            log.exception(msg)
            wr_exit()._exit(1, msg)
        if index != 0:
            msg = "Timeout occurred: Failed to find prompt"
            log.error(msg)

        # Remove command and prompt
        output = "\n".join(output.decode('utf-8', 'ignore').splitlines()[1:-1])

        return output

    def exec_cmd(self, cmd, timeout=TELNET_EXPECT_TIMEOUT, show_output=True):
        log.info(cmd)
        self.write_line(cmd)
        output = self.find_prompt(timeout)
        if show_output:
            log.info("Output:\n" + output)
        self.write_line(RETURN_CODE_CMD)
        try:
            index, match = self.expect([str.encode(RETURN_CODE_REGEX)], TELNET_EXPECT_TIMEOUT)[:2]
        except EOFError:
            msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
            log.exception(msg)
            wr_exit()._exit(1, msg)
        if index == 0:
            rc = remove_markers(match.group(0).decode('utf-8','ignore'))
            log.info("Return code: " + rc)
        else:
            msg = "Timeout occurred: Failed to find return code"
            log.error(msg)
            wr_exit()._exit(1, msg)
        self.find_prompt(TELNET_EXPECT_TIMEOUT)
        return (int(rc), output)

    def login(self, username=WRSROOT_USERNAME, password=WRSROOT_PASSWORD, reset=False):
        """Waits for login prompt to authenticate user.

           Does nothing if user is already logged in.
        """
        if reset:
            self.write_line(WRSROOT_USERNAME)
            self.get_read_until(PASSWORD_PROMPT)
            self.write_line(WRSROOT_DEFAULT_PASSWORD)
            self.get_read_until(PASSWORD_PROMPT)
            self.write_line(WRSROOT_DEFAULT_PASSWORD)
            self.get_read_until(PASSWORD_PROMPT)
            self.write_line(WRSROOT_PASSWORD)
            self.get_read_until(PASSWORD_PROMPT)
            self.write_line(WRSROOT_PASSWORD)
            self.find_prompt()
        else:
            count = 0
            while count < MAX_SEARCH_ATTEMPTS:
                log.info("Searching for login prompt...")
                self.write_line("")
                try:
                    index  = (self.expect([b"ogin:", str.encode(PROMPT)], TELNET_EXPECT_TIMEOUT))[0]
                except EOFError:
                    msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
                    log.exception(msg)
                    wr_exit()._exit(1, msg)
                if index == 0:
                    log.info("Found login prompt. Login as {}".format(username))
                    self.write(str.encode(username + '\r\n'))
                    if password:
                        self.get_read_until(PASSWORD_PROMPT, TELNET_EXPECT_TIMEOUT)
                    self.write(str.encode(password + '\r\n'))
                    self.find_prompt()
                    break
                elif index == 1:
                    log.info('User "{}" is already logged in.'.format(username))
                    break
                count += 1
            if count == MAX_SEARCH_ATTEMPTS:
                msg = "Timeout occurred: Failed to find login or prompt"
                log.error(msg)
                wr_exit()._exit(1, msg)


    def menu_selection(self, host_os, small_footprint, lowlat, usb, security, iso_install):
        """
        Menu selection logic
        """

        # Install from pxeboot script behaves exactly like USB installs
        if iso_install:
            usb = True

        # Options align with pxeboot.cfg on tuxlab
        if host_os == 'wrlinux':
            if usb:
                if small_footprint:
                    log.info("Selecting WRL CPE Install")
                    selection_menu_option = '3'
                else:
                    log.info("Selecting WRL Controller Install")
                    selection_menu_option = '0'
                for x in range(0, int(selection_menu_option)):
                    log.info("Pressing down key")
                    self.write(str.encode(DOWN))
                    time.sleep(1)
                log.info("Pressing ENTER key")
                self.write(str.encode("\n"))
                return
            else:
                if small_footprint:
                    log.info("Selecting WRL CPE Install")
                    selection_menu_option = '3'  # WRL CPE Install
                else:
                    log.info("Selecting WRL Controller Install")
                    selection_menu_option = '1'  # WRL Controller Install
                self.write(str.encode(selection_menu_option))
                self.write(str.encode("\n"))
                return
        else:
            # Centos
            if (small_footprint and lowlat) and not security:
                log.info("Selecting Centos AIO Low Lat Install")
                selection_menu_option = '6'  # Centos CPE Low Latency Install
            elif small_footprint and not security:
                log.info("Selecting Centos AIO Install")
                selection_menu_option = '4'  # Centos CPE Install
            elif small_footprint and lowlat and security:
                log.info("Selecting Centos AIO Low Lat Install")
                selection_menu_option = '2'  # Centos CPE Low Latency Install - Security
            elif small_footprint and security:
                log.info("Selecting Centos AIO Install")
                selection_menu_option = '1'  # Centos CPE Install - Security
            elif security:
                log.info("Selecting Centos Controller Install")
                selection_menu_option = '0'  # Centos Controller Install - Security
            else:
                log.info("Selecting Centos Controller Install")
                selection_menu_option = '2'  # Centos Controller Install - Security

            time.sleep(2)

            # Hierarchical menu
            if security and not usb:
                log.info("Pressing SPACE bar")
                self.write_line(" ")
                time.sleep(2)
                log.info("Pressing menu label")
                self.write(str.encode(selection_menu_option))
                log.info("Pressing ENTER key")
                self.write(str.encode("\n"))
                return

            # This is the standard pxeboot menu selection
            if not usb:
                log.info("Pressing menu label")
                self.write(str.encode(selection_menu_option))
                log.info("Pressing ENTER key")
                self.write(str.encode("\n"))
                return

            # This is the USB menu for installs that don't have a hierarchical
            # menu
            if usb and not security:
                if small_footprint and lowlat:
                    selection_menu_option = '4'
                elif small_footprint:
                    selection_menu_option = '2'
                else:
                    selection_menu_option = '0'

                for x in range(0, int(selection_menu_option)):
                    log.info("Pressing down key")
                    self.write(str.encode(DOWN))
                    time.sleep(1)
                log.info("Pressing ENTER key")
                self.write(str.encode("\n"))
                return

            # This is the USB hierarchical menu
            if security and usb:
                for x in range(0, int(selection_menu_option)):
                    log.info("Pressing down key")
                    self.write(str.encode(DOWN))
                    time.sleep(1)
                log.info("Pressing ENTER key")
                self.write(str.encode("\n"))

                # Press enter for Serial Console
                log.info("Selecting serial console")
                log.info("Pressing ENTER key")
                self.write(str.encode("\n"))
                time.sleep(2)

                # Pick extended or standard profile
                if security.lower() == 'extended':
                    log.info("Selecting extended profile")
                    log.info("Pressing down key")
                    self.write(str.encode(DOWN))
                    time.sleep(2)
                    log.info("Pressing ENTER key")
                    self.write(str.encode("\n"))
                else:
                    log.info("Selecting standard profile")
                    log.info("Pressing ENTER key")
                    self.write(str.encode("\n"))



    #TODO: The regular expression passed into re.compile(...) to search through
    #      the boot menu for each BIOS type should perhaps be set as constants
    #      or even specified in the barcode .ini for each node. Some nodes
    #      e.g. wildcat13-14 do not print their BIOS type (wildcat) when they
    #      boot so the logic below to expect the BIOS type to be printed
    #      does not work. This is why for wildcat the host_name is searched
    #      for reference to "wildcat". But it is messy to search the boot
    #      console for the BIOS type for some nodes and not for others.
    #      So this function needs more consistency in terms of how it
    #      figures out what the BIOS type is and subsequently, how it determines
    #      which regex to pass into re.compile(...).

    #TODO: The timeouts in this function need to be tested to see if they
    #      should be increased/decreased
    #TODO: If script returns zero, should check return code, otherwise remove it
    def install(self, node, boot_device_dict, small_footprint=False, host_os='centos', usb=False, lowlat=False, security=False, iso_install=False):
        if "wildcat" in node.host_name or "supermicro" in node.host_name or "wolfpass" in node.host_name:
            if "wildcat" in node.host_name or "wolfpass" in node.host_name:
                index = 0
                boot_menu_name = "boot menu"
            else:
                index = 4
                boot_menu_name = "Boot Menu"
            bios_key = BIOS_TYPE_FN_KEY_ESC_CODES[index]
            bios_key_hr = BIOS_TYPE_FN_HUMAN_READ[index]
            install_timeout = INSTALL_TIMEOUTS[index]
            bios_type = BIOS_TYPES[index]
            log.info("BIOS type: " + bios_type.decode('utf-8', 'ignore'))
            log.info("Use BIOS key: " + bios_key_hr)

            self.get_read_until(boot_menu_name, 360)
            log.info("Pressing BIOS key")
            self.write(str.encode(bios_key))

            boot_device_regex = next(
                (value for key, value in boot_device_dict.items() if key == node.name or key == node.personality), None)
            if boot_device_regex is None:
                msg = "Failed to determine boot device for: " + node.name
                log.error(msg)
            if usb:
                log.info("Boot device is: USB")
            else:
                log.info("Boot device is: " + str(boot_device_regex))

            self.get_read_until("Please select boot device", 60)

            count = 0
            down_press_count = 0
            while count < MAX_SEARCH_ATTEMPTS:

                # GENERIC USB
                if usb and node.name == CONTROLLER0:
                    log.info("Looking for USB device")
                    boot_device_regex = "USB|Kingston|JetFlash"

                log.info("Searching boot device menu for {}...".format(boot_device_regex))
                # \x1b[13;22HIBA XE Slot 8300 v2140\x1b[14;22HIBA XE Slot
                # Construct regex to work with wildcatpass machines
                # in legacy and uefi mode
                if "wildcat" in node.host_name or "wolfpass" in node.host_name:
                    regex = re.compile(b"\[\d+(;22H|;15H|;14H|;11H|;13H)(.*?)\x1b")
                else:
                    regex = re.compile(b"\[\d+(;22H|;15H|;14H|;11H|;13H)(.*?)\x1b|Slot \d{4} v\d+")
                    #regex = re.compile(b"Slot \d{4} v\d+")

                try:
                    index, match = self.expect([regex], BOOT_MENU_TIMEOUT)[:2]
                except EOFError:
                    msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
                    log.exception(msg)
                    wr_exit()._exit(1, msg)
                if index == 0:
                    match = match.group(0).decode('utf-8', 'ignore')
                    log.info("Matched: " + match)
                    if re.search(boot_device_regex, match, re.IGNORECASE):
                        log.info("Found boot device {}".format(boot_device_regex))
                        time.sleep(1)
                        log.info("Pressing ENTER key")
                        self.write(str.encode("\r\r"))
                        break
                    else:
                        time.sleep(1)
                        self.write(str.encode(DOWN))
                        down_press_count += 1
                        log.info("DOWN key count: " + str(down_press_count))
                count += 1

            if count == MAX_SEARCH_ATTEMPTS:
                msg = "Timeout occurred: Failed to find boot device {} in menu".format(boot_device_regex)
                log.error(msg)
                return 1

            # log.info("Waiting for ESC to exit")
            if node.name == CONTROLLER0:
                if usb:
                    self.get_read_until("Select kernel options and boot kernel", 120)
                    self.menu_selection(host_os, small_footprint, lowlat, usb, security, iso_install)
                elif "UEFI" in boot_device_regex:
                    # Special case for wcp92-98 (NVME default)
                    log.info("boot_device_regex, selecting UEFI boot option 2: {}".format(boot_device_regex))
                    #self.get_read_until("UEFI CentOS Serial Controller Install", BOOT_MENU_TIMEOUT)
                    self.get_read_until("Automatic Anaconda", BOOT_MENU_TIMEOUT)
                    time.sleep(3)
                    log.info("Pressing DOWN key")
                    self.write(str.encode(DOWN))
                    if small_footprint:
                        time.sleep(1)
                        log.info("Pressing DOWN key")
                        self.write(str.encode(DOWN))
                    if lowlat:
                        time.sleep(1)
                        log.info("Pressing DOWN key")
                        self.write(str.encode(DOWN))
                    if security:
                        time.sleep(1)
                        log.info("Pressing DOWN key")
                        self.write(str.encode(DOWN))
                        time.sleep(1)
                        log.info("Pressing DOWN key")
                        self.write(str.encode(DOWN))
                    log.info("Pressing ENTER key")
                    self.write(str.encode("\r\r"))
                else:
                    self.get_read_until("Boot from hard drive", 240)
                    self.menu_selection(host_os, small_footprint, lowlat, usb, security, iso_install)

            self.get_read_until(LOGIN_PROMPT, install_timeout)
            log.info("Found login prompt. {} installation has completed".format(node.name))
            return 0

        try:
            log.info("Find BIOS type")
            index, match = self.expect(BIOS_TYPES, BIOS_TYPE_TIMEOUT)[:2]
        except EOFError:
            msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
            log.exception(msg)
            wr_exit()._exit(1, msg)
        if 0 <= index <= len(BIOS_TYPES)-1:
            bios_key = BIOS_TYPE_FN_KEY_ESC_CODES[index]
            bios_key_hr = BIOS_TYPE_FN_HUMAN_READ[index]
            install_timeout = INSTALL_TIMEOUTS[index]
            bios_type = match.group(0)
            log.info("BIOS type: " + bios_type.decode('utf-8','ignore'))
            log.info("Use BIOS key: " + bios_key_hr)
            log.info("Installation timeout: " + str(install_timeout))
        else:
            msg = "Timeout occurred: Failed to find BIOS type {} while booting {}".format(str(BIOS_TYPES), node.name)
            log.error(msg)
            wr_exit()._exit(1, msg)

        # American Megatrends BIOS, e.g. IronPass
        if bios_type == BIOS_TYPES[0]:
            boot_device_regex = next((value for key, value in boot_device_dict.items() if key == node.name or key == node.personality), None)
            if boot_device_regex is None:
                msg = "Failed to determine boot device for: " + node.name
                log.error(msg)
                wr_exit()._exit(1, msg)
            if usb:
                log.info("Boot device is: USB")
            else:
                log.info("Boot device is: " + str(boot_device_regex))

            self.get_read_until("Boot Menu", 200)
            log.info("Pressing BIOS key " + bios_key_hr)

            # Ugly hack for machines that don't cooperate
            for i in range(0, 5):
                self.write(str.encode(bios_key))
                time.sleep(1)

            self.get_read_until("Please select boot device", 200)

            count = 0
            down_press_count = 0
            while count < MAX_SEARCH_ATTEMPTS:

                # GENERIC USB
                if usb and node.name == CONTROLLER0:
                    log.info("Looking for USB device")
                    boot_device_regex = "USB|Kingston|JetFlash"

                log.info("Searching boot device menu for {}...".format(boot_device_regex))
                #regex = re.compile(b"\\x1b\[\d;\d\d;\d\dm.*\|\s(.*)\s+(.*?)\|")
                regex = re.compile(b"\\x1b\[\d;\d\d;\d\dm.*\|\s(.*?)\|")
                #\x1b[13;22HIBA XE Slot 8300 v2140\x1b[14;22HIBA XE Slot
                try:
                    index, match = self.expect([regex], BOOT_MENU_TIMEOUT)[:2]
                except EOFError:
                    msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
                    log.exception(msg)
                    wr_exit()._exit(1, msg)
                if index == 0:
                    match = match.group(1).decode('utf-8','ignore')
                    log.info("Matched: " + match)
                    if re.search(boot_device_regex, match, re.IGNORECASE):
                        log.info("Found boot device {}".format(boot_device_regex))
                        time.sleep(1)
                        log.info("Pressing ENTER key")
                        self.write(str.encode("\r\r"))
                        break
                    else:
                        time.sleep(1)
                        self.write(str.encode(DOWN))
                        down_press_count += 1
                        log.info("DOWN key count: " + str(down_press_count))
                count += 1
            if count == MAX_SEARCH_ATTEMPTS:
                msg = "Timeout occurred: Failed to find boot device {} in menu".format(boot_device_regex)
                log.error(msg)
                return 1
                #wr_exit()._exit(1, msg)

            if node.name == CONTROLLER0:
                # booting device = USB tested only for Ironpass-31_32
                if usb:
                    self.get_read_until("Select kernel options and boot kernel", 120)
                    self.menu_selection(host_os, small_footprint, lowlat, usb, security, iso_install)
                else:
                    self.get_read_until("Boot from hard drive", 60)
                    self.menu_selection(host_os, small_footprint, lowlat, usb, security, iso_install)

        elif bios_type == BIOS_TYPES[1] or "r430" in node.host_name or "r730" in node.host_name:
            print("Hewlett-Packard BIOS")
            if "r430" in node.host_name or "r730" in node.host_name:
                bios_key = '\x1b@'
                self.get_read_until("PXE Boot", 120)
            else:
                self.get_read_until("Network Boot", 120)
                self.get_read_until("Network Boot", 10)
            log.info("Enter BIOS key")
            self.write(str.encode(bios_key))

            if node.name == CONTROLLER0:
                #self.get_read_until("Kickstart Boot Menu", 120)
                self.get_read_until("Boot Menu", 360)
                self.menu_selection(host_os, small_footprint, lowlat, usb, security, iso_install)
        elif bios_type == BIOS_TYPES[2]:
            boot_device_regex = next((value for key, value in boot_device_dict.items() if key == node.name or key == node.personality), None)
            if boot_device_regex is None:
                msg = "Failed to determine boot device for: " + node.name
                log.error(msg)
                wr_exit()._exit(1, msg)
            if usb:
                log.info("Boot device is: USB")
            else:
                log.info("Boot device is: " + str(boot_device_regex))

            # GENERIC USB
            if usb and node.name == CONTROLLER0:
                log.info("Looking for USB device")
                boot_device_regex = "USB|Kingston|JetFlash"

            # Read until we are prompted for the boot type
            self.get_read_until("PXE")
            log.info("Pressing BIOS key " + bios_key_hr)
            self.write(str.encode(bios_key))
            # Wait until we see the boot device menu
            self.get_read_until("From")
            count = 0
            down_press_count = 0
            while count < MAX_SEARCH_ATTEMPTS:
                log.info("Searching boot device menu for {}...".format(boot_device_regex))
                # e.g. Integrated NIC 2 BRCM MBA Slot 0101 v16.2.1
                regex = re.compile(b"\x1B\(B(.*)\x1B\(0x")
                try:
                    index, match = self.expect([regex], BOOT_MENU_TIMEOUT)[:2]
                except EOFError:
                    msg = "Connection closed: Reached EOF in Telnet session: {}:{}.".format(self.host, self.port)
                    log.exception(msg)
                    wr_exit()._exit(1, msg)

                if index == 0:
                    match = match.group(1).decode('utf-8','ignore')
                    log.info("Matched: " + match)
                    if re.search(boot_device_regex, match, re.IGNORECASE):
                        log.info("Found boot device {}".format(boot_device_regex))
                        time.sleep(1)
                        log.info("Pressing ENTER key")
                        self.write(str.encode("\r\r"))
                        break
                    else:
                        time.sleep(1)
                        self.write(str.encode(DOWN))
                        down_press_count += 1
                        log.info("DOWN key count: " + str(down_press_count))
                count += 1
            if count == MAX_SEARCH_ATTEMPTS:
                msg = "Timeout occurred: Failed to find boot device {} in menu".format(boot_device_regex)
                log.error(msg)
                return 1

            if node.name == CONTROLLER0:
                self.get_read_until("Boot from hard drive", 300)
                self.menu_selection(host_os, small_footprint, lowlat, usb, security, iso_install)

        # Not fool-proof.  FIX
        self.get_read_until(LOGIN_PROMPT, install_timeout)
        log.info("Found login prompt. {} installation has completed".format(node.name))


        return 0

def deploy_ssh_key(self):
    self.write_line("mkdir -p ~/.ssh/")
    cmd = 'grep -q "{}" {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH)
    if self.exec_cmd(cmd)[0] != 0:
        log.info("Adding public key to {}".format(AUTHORIZED_KEYS_FPATH))
        self.write_line('echo -e "{}\n" >> {}'.format(ssh_key, AUTHORIZED_KEYS_FPATH))
        self.write_line("chmod 700 ~/.ssh/ && chmod 644 {}".format(AUTHORIZED_KEYS_FPATH))

def connect(ip_addr, port=23, timeout=TELNET_EXPECT_TIMEOUT, port_login=False, negotiate=False, vt100query=False, log_path=None, debug=False):
    """Establishes telnet connection to host."""

    if log_path:
        logfile = open(log_path, 'a')
    else:
        logfile = None
    try:
        log.info("Open Telnet connection to: {} {}".format(ip_addr, port))
        conn = Telnet(ip_addr, port, timeout, negotiate, vt100query, logfile)
        if port_login:
            conn.login(TELNET_CONSOLE_USERNAME, TELNET_CONSOLE_PASSWORD)

        if debug:
            conn.set_debuglevel(1)
    except ConnectionRefusedError:
        msg = "Connection refused: Telnet session already open: {} {}".format(ip_addr, port)
        log.exception(msg)
        wr_exit()._exit(1, msg)
    except TimeoutError:
        msg = "Timeout occurred: Failed to create Telnet session: {} {}".format(ip_addr, port)
        log.exception(msg)
        wr_exit()._exit(1, msg)

    return conn

#-- new functions end

def test():
    """Test program for telnetlib.

    Usage: python telnetlib.py [-d] ... [host [port]]

    Default host is localhost; default port is 23.

    """
    debuglevel = 0
    while sys.argv[1:] and sys.argv[1] == '-d':
        debuglevel = debuglevel+1
        del sys.argv[1]
    host = 'localhost'
    if sys.argv[1:]:
        host = sys.argv[1]
    port = 0
    if sys.argv[2:]:
        portstr = sys.argv[2]
        try:
            port = int(portstr)
        except ValueError:
            port = socket.getservbyname(portstr, 'tcp')
    tn = Telnet()
    tn.set_debuglevel(debuglevel)
    tn.open(host, port, timeout=0.5)
    tn.interact()
    tn.close()

if __name__ == '__main__':
    test()
