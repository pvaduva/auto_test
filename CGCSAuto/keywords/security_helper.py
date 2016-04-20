from utils.ssh import ControllerClient


class LinuxUser:
    users = {'wrsroot': 'li69nux'}
    con_ssh = None

    def __init__(self, user, password, con_ssh=None):
        self.user = user
        self.password = password
        self.added = False
        self.con_ssh = con_ssh if con_ssh is not None else ControllerClient.get_active_controller()

    def add_user(self):
        self.added = True
        LinuxUser.users[self.user] = self.password
        raise NotImplementedError

    def modify_password(self):
        raise NotImplementedError

    def delete_user(self):
        raise NotImplementedError

    def login(self):
        raise NotImplementedError

    @classmethod
    def get_user_password(cls):
        raise NotImplementedError

    @classmethod
    def get_current_user_password(cls):
        if not cls.con_ssh:
            cls.con_ssh = ControllerClient.get_active_controller()
        user = cls.con_ssh.get_current_user()
        return user, cls.users[user]
