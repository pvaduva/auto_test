
import yaml
from utils.tis_log import LOG


def parse_yaml(yaml_files, yaml_output):

    yaml_out = {}
    for yaml_file in yaml_files:
        print(yaml_file)
        y = open(yaml_file, "r")
        docs = yaml.load_all(y)
        for document in docs:
            if document:
                LOG.info(document['kind'])
                document_name = (document['kind'], document['metadata']['name'])
                yaml_out[document_name] = merge_yaml(yaml_out.get(document_name, {}), document)

    yaml.dump_all(yaml_out.values(), open(yaml_output, 'w'), default_flow_style=False)


def merge_yaml(yaml_old, yaml_new):
    merged_dict = yaml_old.copy()
    for k in yaml_new.keys():
        if not isinstance(yaml_new[k], dict):
            merged_dict[k] = yaml_new[k]
        elif k not in yaml_old:
            merged_dict[k] = merge_yaml({}, yaml_new[k])
        else:
            merged_dict[k] = merge_yaml(yaml_old[k], yaml_new[k])
    return merged_dict
