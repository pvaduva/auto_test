import re

from utils.tis_log import LOG

NEW_FILE_NAME = '/home/yliu12/new_session.LOG'


def format_session_log():
    # TODO: .replace(r'\r\n', '\n'), then remove duplicated sent msg and prompt to show output only.
    with open('/home/yliu12/session.LOG') as input_file:
        content = input_file.read()
        content = content.replace(r'\r', '\r').replace(r'\n', '\n').replace(r'\\"', r'\"')
        content = re.sub(r"['\"]b['\"]", "", content)
        with open(NEW_FILE_NAME, 'w+') as output_file:
            output_file.writelines(content)
            LOG.info("Formatted ssh session LOG is saved to {}".format(NEW_FILE_NAME))

if __name__ == '__main__':
    format_session_log()