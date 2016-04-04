class TiSError(Exception):
    """
    Base class for TiS test automation exceptions.

    Notes:
        Each module (or package depends on which makes more sense) should have its own sub-base-class that
    inherits this class.Then the specific exception for that module/package should inherit the sub-base-class.

    Examples:
        sub-base-class for ssh.py: SSHException(TiSError); ssh retry timeout exception: SSHRetryTimeout(SSHException)
    """
    message = "An unknown exception occurred"

    def __init__(self, detailed_message="No details provided"):
        super(TiSError, self).__init__()
        self._error_string = self.message + "\nDetails: " + detailed_message

    def __str__(self):
        return self._error_string


class NoMatchFoundError(TiSError):
    message = "No match found."


class InvalidStructure(TiSError):
    message = "Invalid cli output table structure."


class SSHException(TiSError):
    """
    Base class for SSH Exceptions. All SSH exceptions thrown from utils > ssh.py module should inherit this class.
    Examples: SSHRetryTimeout(SSHException)
    """
    pass


class SSHRetryTimeout(SSHException):
    message = "Timed out to connect to host."


class IncorrectCredential(SSHException):
    message = "Login credential rejected by host."


class SSHExecCommandFailed(SSHException):
    """Raised when remotely executed command returns nonzero status."""
    message = "Failed to execute command via SSH."


class TimeoutException(SSHException):
    message = "Request(s) timed out"


class ImproperUsage(SSHException):
    message = "Improper use of test framework"


class ActiveControllerUnsetException(SSHException):
    message = ("Active controller ssh client is not set! "
               "Please use ControllerClient.set_active_controller(ssh_client) to set an active controller client.")


class NatBoxClientUnsetException(SSHException):
    message = "NatBox ssh client it not set! Please use NATBoxClient.set_natbox_client(ip) to set an natbox client"


class CLIRejected(TiSError):
    """Throw when cli command is rejected due to unexpected reasons, such as missing arguments"""
    message = "CLI command is rejected."


class HostError(TiSError):
    """Used if post action check inside a keyword fails"""
    pass


class HostPostCheckFailed(HostError):
    """Throws when expected host status is not reached after running certain host action cli command."""
    message = "Check failed post host operation."


class HostPreCheckFailed(HostError):
    message = "Check failed pre host operation."


class HostTimeout(HostError):
    message = "Host operation timed out."


class VMError(TiSError):
    pass


class VMPostCheckFailed(VMError):
    message = "Check failed post VM operation."


class VMNetworkError(VMError):
    message = "VM network connection error."


class VMTimeout(VMError):
    message = "VM operation timed out."


class VMOperationFailed(VMError):
    """Failure indicated by CLI output"""
    message = "VM operation failed."


class VolumeError(TiSError):
    message = "Volume error."


class ImageError(TiSError):
    message = "Image error."


class FlavorError(TiSError):
    message = "Flavor error."


class CommonError(TiSError):
    message = "Setup/Teardown error."
