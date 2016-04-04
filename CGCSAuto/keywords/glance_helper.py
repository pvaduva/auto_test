import random

from utils import table_parser, cli


def get_image_id_from_name(name=None, strict=False, con_ssh=None, auth_info=None):
    table_ = table_parser.table(cli.glance('image-list', ssh_client=con_ssh, auth_info=auth_info))
    if name is None:
        image_id = random.choice(table_parser.get_column(table_, 'ID'))
    else:
        image_ids = table_parser.get_values(table_, 'ID', strict=strict, Name=name)
        image_id = '' if not image_ids else random.choice(image_ids)
    return image_id