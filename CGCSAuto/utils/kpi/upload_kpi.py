from argparse import ArgumentParser
from configparser import ConfigParser
from influxdb import InfluxDBClient
from math import ceil


KPI_DB = 'tis-lab-auto-test-kpis.cumulus.wrs.com'
KPI_USER = 'cumulus'
KPI_PASSWD = 'kumuluz'
DB_NAME = 'kpihistory'
# DB_NAME = 'testdb'    # test database


def upload_kpi(kpi_file, host=KPI_DB, port=8086, user=KPI_USER,
               password=KPI_PASSWD):
    try:
        kpi_config = ConfigParser()
        kpi_config.read(kpi_file)
        kpi_list = []
        sections = kpi_config.sections()
        if not sections:
            print("No kpi recorded in {}".format(kpi_file))
            return
    except Exception as e:
        print(e.__str__())
        return

    for section in sections:
        section_dict = {'name': section}
        options = kpi_config.options(section)
        for option in options:
            try:
                section_dict[option] = kpi_config.get(section, option)
            except:
                print("exception on %s!" % option)
                section_dict[option] = None
        kpi_list.append(section_dict)

    # print(str(kpi_list))

    upload_list = []
    for kpi_dict in kpi_list:
        kpi_name = kpi_dict.get('name')
        kpi_val = kpi_dict.get('value')
        vals = [float(val_) for val_ in kpi_val.split(',')]
        upload_dict = {
            'measurement': kpi_name,
            'time': '{}Z'.format(kpi_dict.get('timestamp').strip().replace(' ', 'T')),
            'tags': {
                'lab': kpi_dict.get('lab'),
                'build_id': kpi_dict.get('build_id', ''),
                'sw_version':  kpi_dict.get('sw_version', ''),
                'baseline': 'false'
            },
            'fields': {
                'value': vals[0],
                'unit': kpi_dict.get('unit', '')
            },
        }

        # Add patch tag when avail
        patch = kpi_dict.get('patch', None)
        if patch:
            upload_dict['tags'].update({'patch': patch})

        # Add extra fields when avail
        extra_fields = {}

        if kpi_dict.get('lab_config', None):
            extra_fields.update({'lab_config': kpi_dict.get('lab_config')})

        if 'drbd_sync' in kpi_name.lower():
            extra_fields.update({'value_min': vals[1], 'value_max': vals[2]})

        load_avg = kpi_dict.get('load_average', None)
        if load_avg is not None:
            extra_fields['load_avg'] = float(load_avg)

        disk_io = kpi_dict.get('disk_io', None)
        if disk_io is not None:
            extra_fields['disk_io'] = float(disk_io)

        if extra_fields:
            upload_dict['fields'].update(extra_fields)

        upload_list.append(upload_dict)

    print("\nConnect to KPI DB and upload KPI(s): \n{}".format(upload_list))
    client = InfluxDBClient(host, port, user, password, DB_NAME)
    client.write_points(upload_list)

    # print("\nQuery uploaded results")
    # for kpi_dict in kpi_list:
    #     # client.delete_series(measurement=kpi_dict.get('name'))
    #     query = 'SELECT * FROM "{}"'.format(kpi_dict.get('name'))
    #     print("{}".format(query))
    #     result = client.query(query)
    #     print("{}\n".format(result))

    return

if __name__ == '__main__':
    parser = ArgumentParser("KPI uploader")
    parser.add_argument('file_path', type=str, help='Full path for recorded KPIs. e.g., '
                                                    '/sandbox/AUTOMATION_LOGS/wcp_7_12/201711151119/kpi.ini')

    args = parser.parse_args()
    upload_kpi(kpi_file=args.file_path)
