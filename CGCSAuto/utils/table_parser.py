import re, copy

from utils import exceptions
from utils.tis_log import LOG
"""Collection of utilities for parsing CLI clients output."""


delimiter_line = re.compile('^\+\-[\+\-]+\-\+$')


def __details_multiple(output_lines, with_label=False):
    """Return list of dicts with item details from cli output tables.
    If with_label is True, key '__label' is added to each items dict.
    For more about 'label' see OutputParser.tables().
    """
    items = []
    tables_ = tables(output_lines)
    for table_ in tables_:
        if 'Property' not in table_['headers'] or 'Value' not in table_['headers']:
            raise exceptions.InvalidStructure()
        item = {}
        for value in table_['values']:
            item[value[0]] = value[1]
        if with_label:
            item['__label'] = table_['label']
        items.append(item)
    return items


def __details(output_lines, with_label=False):
    """Return dict with details of first item (table_) found in output."""
    items = __details_multiple(output_lines, with_label)
    return items[0]


def listing(output_lines):
    """Return list of dicts with basic item info parsed from cli output."""

    items = []
    table_ = table(output_lines)
    for row in table_['values']:
        item = {}
        for col_idx, col_key in enumerate(table_['headers']):
            item[col_key] = row[col_idx]
        items.append(item)
    return items


def tables(output_lines, combine_multiline_entry=False):
    """Find all ascii-tables in output and parse them.
    Return list of tables parsed from cli output as dicts.
    (see OutputParser.table())
    And, if found, label key (separated line preceding the table_)
    is added to each tables dict.
    Returns (list):
    """
    tables_ = []

    table_ = []
    label = None

    start = False
    header = False

    if not isinstance(output_lines, list):
        output_lines = output_lines.split('\n')

    for line in output_lines:
        if delimiter_line.match(line):
            if not start:
                start = True
            elif not header:
                # we are after head area
                header = True
            else:
                # table ends here
                start = header = None
                table_.append(line)

                parsed = table(table_, combine_multiline_entry=combine_multiline_entry)
                parsed['label'] = label
                tables_.append(parsed)

                table_ = []
                label = None
                continue
        if start:
            table_.append(line)
        else:
            if label is None:
                label = line
            else:
                LOG.warning('Invalid line between tables: %s' % line)
    if len(table_) > 0:
        LOG.warning('Missing end of table')

    return tables_


def __table(output_lines):
    """Parse single table from cli output.
    Return dict with list of column names in 'headers' key and
    rows in 'values' key.
    """
    table_ = {'headers': [], 'values': []}
    columns = []

    if not isinstance(output_lines, list):
        output_lines = output_lines.split('\n')

    if not output_lines[-1]:
        # skip last line if empty (just newline at the end)
        output_lines = output_lines[:-1]

    delimiter_line_num = 0
    header_rows = []
    for line in output_lines:
        if delimiter_line.match(line):
            columns = __table_columns(line)
            delimiter_line_num += 1
            continue
        if '|' not in line:
            LOG.debug('skipping invalid table line: %s' % line)
            continue
        row = []
        for col in columns:
            row.append(line[col[0]:col[1]].strip())
        if table_['values']:
            table_['values'].append(row)
        else:
            if not header_rows:
                header_rows.append(row)
                continue
            if row[0] == '':
                header_rows.append(row)
            else:
                table_['values'].append(row)

    headers_ = [list(filter(None, list(t))) for t in zip(*header_rows)]
    table_['headers'] = [''.join(item) for item in headers_]

    return table_


def __table_columns(first_table_row):
    """Find column ranges in output line.
    Return list of tuples (start,end) for each column
    detected by plus (+) characters in delimiter line.
    """
    positions = []
    start = 1  # there is '+' at 0
    while start < len(first_table_row):
        end = first_table_row.find('+', start)
        if end == -1:
            break
        positions.append((start, end))
        start = end + 1
    return positions

###################################################################
#  Above are contents from tempest_lib. Below are extended by us. #
###################################################################

TWO_COLUMN_TABLE_HEADERS = [['Field', 'Value'], ['Property', 'Value']]


def table(output_lines, combine_multiline_entry=False):
    """
    Tempest table does not take into account when multiple lines are used for one entry. Such as neutron net-list -- if
    a net has multiple subnets, then tempest table will create multiple entries in table_['values']
    param output_lines: output from cli command
    return: Dictionary of a table with.multi-line entry taken into account.table_['values'] is list of entries. If
    multi-line entry, then this entry itself is a list.
    """
    table_ = __table(output_lines)
    rows = get_all_rows(table_)
    if not rows:
        LOG.debug("Empty table supplied! table_: {}".format(table_))
        return table_

    line_count = len(rows)
    # no need to check for multiple line entry if it's a one line table.
    if line_count == 1:
        return table_

    entries = []
    start_index = 0  # start_index for first entry
    for i in range(line_count):      # line_count > 1 if code can get here.
        # if first value for the NEXT row is not empty string, then next row is the start of a new entry,
        # and the current row is the last row of current entry
        if i == line_count-1 or rows[i+1][0]:
            end_index = i
            if start_index == end_index:   # single-line entry
                entry = rows[start_index]
            else:       # multi-line entry
                entry_lines = [rows[index] for index in range(start_index, end_index+1)]
                # each column value is a list
                entry_combined = [list(filter(None, list(t))) for t in zip(*entry_lines)]
                if combine_multiline_entry:
                    entry = [' '.join(item) for item in entry_combined]
                else:
                    # convert column value to string if list len is 1
                    entry = [item if len(item) > 1 else ' '.join(item) for item in entry_combined]
                LOG.debug("Multi-row entry found: {}".format(entry))

            entries.append(entry)
            start_index = i + 1  # start_index for next entry

    table_['values'] = entries
    return table_


def get_all_rows(table_):
    """
    Args:
        table_ (dict): Dictionary of a table parsed by tempest.
            Example: table =
            {
                'headers': ["Field", "Value"];
                'values': [['name', 'internal-subnet0'], ['id', '36864844783']]}
    Return:
        Return rows as a list. Each row itself is an sub-list.
        e.g.,[['name', 'internal-subnet0'], ['id', '36864844783']]
    """
    if table_ and not isinstance(table_, dict):
        raise ValueError("Input has to be a dictionary. Input: {}".format(table_))

    return table_['values'] if table_ else None


def get_column_index(table_, header):
    """
    Get the index of a column that has the given header. E.g., return 0 if 'id' column is the first column in a table
    This is normally used for a multi-columns table. i.e., not the two-column(Field/Value) table.
    :param table_: table as a dictionary
    :param header: header of the column in interest
    :return: Return the index value of a given header
    """
    headers = table_['headers']
    headers = [str(item).lower().strip() for item in headers]
    header = header.strip().lower()
    try:
        return headers.index(header)
    except ValueError:
        return headers.index(header.replace('_', ' '))

    # return headers.index(header.lower())  # ValueError if not found


def __get_id(table_, row_index=None):
    """
    Get id. If it's a two-column table_, find the id row, and return the value. Else if it's a multi-column table_, the
    row_index needs to be supplied, then for a specific row, return the value under the id column.
    :param table_: output table as dictionary parsed by tempest
    :param row_index: row_index for a multi-column table. row_index should exclude the header row.
    :return: return the id value
    """
    return __get_value(table_, 'id', row_index)


def __get_value(table_, field, row_index=None):
    """

    Args:
        table_:  output table as dictionary parsed by tempest
        field: field of the item. such as id, name, gateway_ip, etc
        row_index: row_index for a multi-column table. This is not required for a two-column table. Following table
            is considered to have only one row, and the row_index for that row is 0.
            +--------------------------------------+------------+--------+--------------------------------------------------------------+
            | ID                                   | Name       | Status | Networks                                                     |
            +--------------------------------------+------------+--------+--------------------------------------------------------------+
            | 1ab2c401-7863-42ab-8d2b-c2b7e8fa3adb | wrl5-avp-0 | ACTIVE | internal-net0=10.10.1.2, 10.10.0.2;public-net0=192.168.101.3 |
            +--------------------------------------+------------+--------+--------------------------------------------------------------+

    Returns:
        return the value for a specific field (on a specific row if it's a multi-column table_)

    """

    if __is_table_two_column(table_):
        if row_index is not None:
            LOG.warn("Two-column table found, row_index {} will not be used to locate {} field".
                     format(row_index, field))
        for row in table_['values']:
            if row[0] == field:
                return row[1]
        raise ValueError("Value for {} not found in table_".format(field))

    else:  # table is a multi-column table
        if row_index is None:
            raise ValueError("row_index needs to be supplied!")
        col_index = get_column_index(table_, field)
        return_value = table_['values'][row_index][col_index]
        LOG.debug("return value for {} field is: {}".format(field, return_value))
        return return_value


def __is_table_two_column(table_):
    return True if table_['headers'] in TWO_COLUMN_TABLE_HEADERS else False


def get_column(table_, header):
    """
    Get a whole column with customized header as a list. The header itself is excluded.

    Args:
        table_ (dict): Dictionary of a table parsed by tempest.
            Example: table =
            {
                'headers': ["Field", "Value"];
                'values': [['name', 'internal-subnet0'], ['id', '36864844783']]}
        header (str): header of a column

    Returns (list): target column. Each item is a string.

    """
    if not table_['headers']:
        LOG.warning("Empty table supplied")
        return []
    rows = get_all_rows(table_)
    index = get_column_index(table_, header)
    column = []
    for row in rows:
        column.append(row[index])

    return column


def __get_row_indexes_string(table_, header, value, strict=False, exclude=False):
    if isinstance(value, list):
        value = ''.join(value)

    if not isinstance(value, str):
        value = str(value)

    value = value.strip().lower()

    header = header.strip().lower()
    column = get_column(table_, header)

    row_index = []
    for i in range(len(column)):
        item = column[i]
        if isinstance(item, list):
            item = ''.join(item)
        item = item.strip().lower()
        if strict:
            is_valid = item == value
        elif isinstance(value, list):
            is_valid = True
            for v in value:
                if v not in item:
                    is_valid = False
                    break
        else:
            is_valid = value in item

        if is_valid is not exclude:
            row_index.append(i)

    LOG.debug("row index list for {}: {}: {}".format(header, value, row_index))
    return row_index


def _get_values(table_, header1, value1, header2, strict=False, regex=False):
    """
    Args:
        table_:
        header1:
        value1:
        header2:

    Returns (list):

    """

    # get a list of rows where header1 contains value1
    column1 = get_column(table_, header1)
    row_indexes = []
    if regex:
        for i in range(len(column1)):
            if strict:
                res_ = re.match(value1, column1[i])
            else:
                res_ = re.search(value1, column1[i])
            if res_:
                row_indexes.append(i)
    else:
        row_indexes = __get_row_indexes_string(table_, header1, value1, strict)

    column2 = get_column(table_, header2)
    value2 = [column2[i] for i in row_indexes]
    LOG.debug("Returning matching {} value(s): {}".format(header2, value2))
    return value2


def get_values(table_, target_header, strict=True, regex=False, merge_lines=False, exclude=False, **kwargs):
    """
    Return a list of cell(s) that matches the given criteria. Criteria were given via kwargs.
    Args:
        table_ (dict): cli output table in dict format
        target_header: target header to return value(s) for. Used to filter out the target column.
        regex (bool): whether value(s) in kwargs are regular string or regex pattern

        strict (bool): this param applies to value(s) in kwargs. (i.e., does not apply to the header(s))
            For string operation:
                strict True will attempt to match the whole string of the given value to actual value,
                strict False will attempt to match the given value to any substring of the actual value
            For regex operation:
                strict True will attempt to match from the start of the value
                strict False will attempt to search for a match from anywhere of the actual value

        merge_lines:
            when True: if a value spread into multiple lines, merge them into one line string
                Examples: 'capabilities' field in system host-show
            when False, if a value spread into multiple lines, this value will be presented as a list with
                each line being a string item in this list
                Examples: 'subnets' in neutron net-list
        exclude (bool): whether to exclude the values filtered out

        **kwargs: header/value pair(s) as search criteria. Used to filter out the target row(s).
            When multiple header/value pairs are given, they will be in 'AND' relation.
            i.e., only table cell(s) that matches all the criteria will be returned.

            Examples of criteria:
            personality='controller', networks=r'192.168.\d{1-3}.\d{1-3}'

            if field has space in it, such as 'Tenant ID', replace space with underscore, such as Tenant_ID=id;
            or compose the complete **kwargs like this: **{'Tenant ID': 123, 'Name': 'my name'}

            Examples:
                get_values(table_, 'ID', Tenant_ID=123, Name='my name')
                get_values(table_, 'ID', **{'Tenant ID': 123, 'Name': 'my name'})

    Returns (list): a list of matching values for target header

    """
    if not table_['headers']:
        LOG.warning('Empty table supplied')
        return []

    new_kwargs = {}
    for k, v in kwargs.items():
        if v is not None:
            new_kwargs[k] = v

    if not new_kwargs:
        LOG.debug("kwargs unspecified, returning the whole target column as list.")
        return get_column(table_, target_header)

    row_indexes = []
    for header, values in new_kwargs.items():
        if isinstance(values, tuple):
            values = list(values)
        elif not isinstance(values, list):
            values = [values]

        kwarg_row_indexes = []
        for value in values:
            kwarg_row_indexes += _get_row_indexes(table_, header, value, strict=strict, regex=regex)

        row_indexes.append(list(set(kwarg_row_indexes)))

    len_ = len(row_indexes)
    target_row_indexes = []

    if len_ == 1:
        target_row_indexes = row_indexes[0]
    elif len_ > 1:
        # Check every item in the first row_index list and see if it's also in the rest of the row_index lists
        for item in row_indexes[0]:
            for i in range(1, len_):
                if item not in row_indexes[i]:
                    break
            else:
                target_row_indexes.append(item)

    target_column = get_column(table_, target_header)
    target_values = []
    if exclude:
        total_row_indexes = list(range(len(target_column)))
        target_row_indexes = list((set(total_row_indexes) - set(target_row_indexes)))

    for i in target_row_indexes:
        target_value = target_column[i]

        # handle multi-line value
        if merge_lines and isinstance(target_value, list):
            target_value = ' '.join(target_value)

        target_values.append(target_value)

    LOG.debug("Returning matching {} value(s): {}".format(target_header, target_values))
    return target_values


def get_value_two_col_table(table_, field, strict=True, regex=False, merge_lines=False):
    """
    Get value of specified field from a two column table.

    Args:
        table_ (dict): two column table in dictionary format. Such as 'nova show' table.
        field (str): target field to return value for
        regex (bool): When True, regex will be used for field name matching, else string operation will be performed

        strict (bool): If string operation, strict match will attempt to match the whole string, while non-strict match
            will attempt match substring. If regex, strict match will attempt to find match from the beginning of the
            field name, while non-strict match will attempt to search a match anywhere in the field name.

        merge_lines:
            when True: if the value spread into multiple lines, merge them into one line string
                Examples: 'capabilities' field in system host-show
            when False, if the value spread into multiple lines, this value will be presented as a list with
                        each line being a string item in this list
                Examples: 'subnets' field in neutron net-show

    Returns (str): Value of specified filed. Return '' if field not found in table.

    """
    rows = get_all_rows(table_)
    for row in rows:
        target_field = field.strip().lower()
        actual_field = row[0].strip().lower()
        if regex:
            if strict:
                res_ = re.match(target_field, actual_field)
            else:
                res_ = re.search(target_field, actual_field)
            if res_:
                val = row[1]
                break
        # if string
        elif strict:
            if target_field == actual_field:
                val = row[1]
                break
        else:
            if target_field in actual_field:
                val = row[1]
                break
    else:
        LOG.warning("Field {} is not found in table.".format(field))
        LOG.debug("Field {} is not found in table: {}.".format(field, table_))
        val = ''

    # handle multi-line value
    if merge_lines and isinstance(val, list):
        val = ''.join(val)

    return val


def __get_values(table_, header1, value1, header2):
    row_indexes = __get_row_indexes_string(table_, header1, value1)
    column = get_column(table_, header2)
    value2 = [column[i] for i in row_indexes]
    LOG.debug("Returning matching {} value(s): {}".format(header2, value2))
    return value2


# def filter_table_single_field(table_, field, value, strict=True, regex=False, match=False):
#     row_indexes = _get_row_indexes(table_, field=field, value=value, strict=strict, regex=regex)
#     return __filter_table(table_, row_indexes)


def __filter_table(table_, row_indexes):
    """

    Args:
        table_ (dict):
        row_indexes:

    Returns (dict):

    """
    all_rows = get_all_rows(table_)
    target_rows = [all_rows[i] for i in row_indexes]
    table_['values'] = target_rows

    return table_


def _get_row_indexes(table_, field, value, strict=True, regex=False, exclude=False):
    row_indexes = []
    column = get_column(table_, field)
    if regex:
        for j in range(len(column)):
            search_val = column[j]
            if isinstance(search_val, list):
                search_val = ''.join(search_val)
            if isinstance(value, list):
                value = ''.join(value)
            if strict:
                res_ = re.match(value, search_val)
            else:
                res_ = re.search(value, search_val)
            if bool(res_) != exclude:
                row_indexes.append(j)
    else:
        row_indexes = __get_row_indexes_string(table_, field, value, strict=strict, exclude=exclude)

    return row_indexes


def filter_table(table_, strict=True, regex=False, exclude=False, **kwargs):
    """
    Filter out rows of a table with given criteria (via kwargs)
    Args:
        table_ (dict): Dictionary of a table parsed by tempest.
            Example: table {
                'headers': ["Field", "Value"];
                'values': [['name', 'internal-subnet0'], ['id', '36864844783']]}
        strict (bool):
        regex (bool): Whether to use regex to find matching value(s)
        exclude (bool): whether to exclude the rows filtered out

        **kwargs: header/value pair(s) as search criteria. Used to filter out the target row(s).
            Examples: header_1 = [value1, value2, value3], header_2 = value_2
            - kwargs are 'and' relation
            - values for the same key are 'or' relation
            e.g., if kwargs = {'id':[id_1, id_2], 'name': [name_1, name_3]}, a table with only item_2 will be returned
            - See more details from **kwargs in get_values()

    Returns (dict):
        A table dictionary with original headers and filtered values(rows)

    """
    table_ = table_.copy()
    if not kwargs:
        LOG.debug("No kwargs specified. Skip filtering")
        return table_

    if not table_['headers']:
        LOG.warning("Empty table supplied")
        return table_

    row_indexes = []
    first_iteration = True
    for header, values in kwargs.items():
        if isinstance(values, str):
            values = [values]
        row_indexes_for_field = []
        for value in values:
            row_indexes_for_value = _get_row_indexes(table_, field=header, value=value, strict=strict, regex=regex,
                                                     exclude=exclude)
            row_indexes_for_field = set(row_indexes_for_field) | set(row_indexes_for_value)

        if row_indexes_for_field is []:
            row_indexes = []
            break

        if first_iteration:
            row_indexes = row_indexes_for_field
        else:
            row_indexes = set(row_indexes) & set(row_indexes_for_field)

        first_iteration = False

    return __filter_table(table_, row_indexes)


def compare_tables(table_one, table_two):
    """
    table_one and table_two are two nested dict where header is a list and values are nested list
    table_one and table two are form of {'headers':['id','name',...], 'values':[[1,'name1',..],[2,'name2',..]]}

    This function compare the number of elements under 'headers' and 'values' and see if they are same between two table
    Check if the nested list are same length and contain same elements between two table.
    This function does not check any ordering
    """

    table1_keys = set(table_one.keys())
    table2_keys = set(table_two.keys())
    # compare number of keys in each set. They should be only 'headers' and 'values'
    if len(table1_keys) == len(table2_keys) == 2:
        if table1_keys - {'headers', 'values'} or table2_keys - {'headers', 'values'}:
            return 1, "The keys of the two tables is different than expected {{'headers','values'}}, " \
                      "Table one contain {}. Table two contain {}".format(table1_keys, table2_keys)
    else:
        return 2, "The number of keys is different between Table One and Table Two"

    # compare values within the header and values
    for key in table_one:

        if key == 'headers':
            table1_list = set(table_one[key])
            table2_list = set(table_two[key])

        # map nested list into tuples for easy comparison with other table
        if key == 'values':
            table1_list = set(map(tuple, table_one[key]))
            table2_list = set(map(tuple, table_two[key]))

        # values (in list form) under the dict of one table should have same length as the other table
        if len(table1_list) == len(table2_list):

            # they should also have no difference between each other as well
            in1_not2 = table1_list - table2_list
            in2_not1 = table2_list - table1_list

            if len(in1_not2) > 0 or len(in2_not1) > 0:
                msg = "The Value {} was found in table one under header '{}' but not in table two. " \
                      "The Value {} was found in table two under header '{}' but not in table one. "\
                    .format(in1_not2, key, in2_not1, key)
                return 3, msg
        else:
            return 4, "The number of elements under header '{}' different in Table one and Table two".format(key)

    return 0, "Both Table contain same headers and values"


__sm_delimeter_line = re.compile('^-.*[\-]{3,}$')
__sm_category_line = re.compile('^-([A-Z].*[a-z])[\-]{3,}$')
__sm_item_line = re.compile('([a-z-]+)[\t\s$]')


def sm_dump_table(output_lines):
    """
    get sm dump table as dictionary
    Args:
        output_lines (output): output of sudo sm-dump command from a controller

    Returns (dict): table with following headers.
            {'headers': ["category", "name", "desired-state", "actual-state"];
             'values': [
                ['Service_Groups', 'oam-services', 'active', 'active'],
                ['Service_Groups', 'controller-services', 'active', 'active']
                ...
                ['Services', 'oam-ip', 'enabled-active', 'enabled-active']
                ...
                ['Services', 'drbd-cinder, 'enabled-active', 'enabled-active']
                ...
            ]}
    """
    headers = ['category', 'name', 'desired-state', 'actual-state']
    table_ = {'headers': headers, 'values': []}

    if not isinstance(output_lines, list):
        output_lines = output_lines.split('\n')

    if not output_lines[-1]:
        # skip last line if empty (just newline at the end)
        output_lines = output_lines[:-1]

    category = ''
    for line in output_lines:
        if __sm_delimeter_line.match(line):
            potential_category = __sm_category_line.findall(line)
            if potential_category:
                category = potential_category[0]
            LOG.debug("skipping delimiter line: {}".format(line))
            continue
        elif not line.strip():
            LOG.debug('skipping empty table line')
            continue

        row = [category]
        row_contents = list(__sm_item_line.findall(line))
        if not 3 == len(row_contents):
            raise ValueError("Expecting 3 columns per item line. Actual line: {}".format(line))

        row += row_contents
        table_['values'].append(row)

    return table_


def row_dict_table(table_, key_header, unique_key=True, eliminate_keys=None, lower_case=True):
    """
    convert original table to a dictionary with a given column to be the keys.

    Args:
        table_ (dict): original table which in the format of {'headers': [<headers>], 'values': [<rows>]}
        key_header (str): chosen keys for the table
        unique_key (bool): if key_header is unique for each row, such as UUID, then value for each key will be dict
            instead of list of dict
        eliminate_keys (None|str|list): columns to eliminate

    Returns (dict): dictionary with value of the key_header as key, and the complete row as the value.
        The value itself is a list, number of items in the list depends on how many rows has the same value for
        given key_header.

    Examples: system host-list on 2+2 system
        row_dict_table(table_, 'hostname') will return following table:
            {
            'controller-0': {'id': 1, 'hostname': 'controller-0', 'personality': 'controller', ...}
            'controller-1': {'id': 2, 'hostname': 'controller-1', 'personality': 'controller', ...}
            'compute-0': ...
            'compute-1': ...
            }

        row_dict_table(table_, 'personality') will return following table:
            {
            'controller': [{'id': 1, 'hostname': 'controller-0', 'personality': 'controller', ...},
                           {'id': 2, 'hostname': 'controller-1', 'personality': 'controller', ...}]
            'compute': [{'id': 3, 'hostname': 'compute-0', 'personality': 'compute', ...},
                        {'id': 4, 'hostname': 'compute-1', 'personality': 'compute', ...}]
            }
    """
    keys = get_column(table_, key_header)
    all_headers = table_['headers']
    if lower_case:
        all_headers = [header.lower() for header in all_headers]
        keys = [key.lower() for key in keys]
    if eliminate_keys is None:
        eliminate_keys = []
    elif isinstance(eliminate_keys, str):
        eliminate_keys = [eliminate_keys]

    rtn_dict = {}
    for header_val in keys:
        tmp_table = filter_table(table_, **{key_header: header_val})
        applicable_rows = get_all_rows(tmp_table)
        values = []
        for row_ in applicable_rows:
            row_dict = dict(zip(all_headers, row_))
            for key_to_rm in list(eliminate_keys):
                row_dict.pop(key_to_rm, None)

            values.append(row_dict)

        if unique_key:
            values = values[0]

        rtn_dict[header_val] = values

    LOG.debug("Converted table: {}".format(rtn_dict))
    return rtn_dict


def remove_columns(table_, headers):
    """
    Remove header(s) and corresponding values from the table. If the supplied header is not found, skips that header.

    Args:
        table_ (dict): original table which in the format of {'headers': [<headers>], 'values': [<rows>]}
        headers (str/list/tuple): chosen key(s) to remove

    Returns (dict): A table dictionary without key_headers and corresponding values

    Examples: system host-list on 2+2 system
        remove_columns(table_, 'hostname') will return following table:
            {
            'controller-0': [{'id': 1, 'personality': 'controller', ...}]
            'controller-1': [{'id': 2, 'personality': 'controller', ...}]
            'compute-0': ...
            'compute-1': ...
            }

        remove_columns(table_, ['personality', 'hostname']) will return following table:
            {
            'controller': [{'id': 1, ...},
                           {'id': 2, ...}]
            'compute': [{'id': 3, ...},
                        {'id': 4, ...}]
            }
    """
    if isinstance(headers, str):
        headers = [headers]

    if not isinstance(headers, (list, tuple)):
        raise ValueError("key_headers is not a list/string/tuple: {}".format(headers))

    new_table_ = copy.deepcopy(table_)

    for key in headers:
        try:
            column_id = get_column_index(new_table_, key)
            new_table_['headers'].pop(column_id)
            for row in new_table_['values']:
                row.pop(column_id)
        except ValueError:
            continue

    return new_table_


def convert_value_to_dict_cinder(value):
    """
    In a client (e.g. cinderclient) CLI output, a dict type value can be either
    a plain raw string (e.g. cinderclient Newton) or a "pretty formatted"
    multiline dict (e.g. cinderclient Pike).

    Respectively, value parsed from get_value_two_col_table() for these values
    are either a plain raw string in dict format, or a list of key:value pairs.

    This function convert either types to a dict. For latter type leading and
    ending spaces removed for each key/value are removed in the process.

    Example:
        input:
        ['checksum : c1b6664df43550fd5684fe85cdd3ddc3',
        'container_format : bare',
        'disk_format : qcow2',
        'image_id : 8d8ea28f-e633-4e29-8f28-9d8171dbf5b6',
        'image_name : ubuntu_14',
        'min_disk : 0', 'min_ram : 0',
        'size : 260440576', 'store : file']
        output:
        {'checksum': 'c1b6664df43550fd5684fe85cdd3ddc3',
        'min_ram': '0', 'disk_format': 'qcow2',
        'image_name': 'ubuntu_14', 'image_id': '8d8ea28f-e633-4e29-8f28-9d8171dbf5b6',
        'container_format': 'bare', 'min_disk': '0', 'store': 'file', 'size': '260440576'}

    """
    if not isinstance(value, list):
        if '{' in value:
            # newton
            return eval(value)
        value = [value]
    d = {k.strip(): v.strip() for k, v in (x.split(':') for x in value)}
    return d


def get_columns(table_, headers):
    if not isinstance(headers, list) and not isinstance(headers, set):
        headers = [headers]

    all_headers = table_['headers']
    if not set(headers).issubset(all_headers):
        LOG.error('Unknown column:{}'.format(
                list(set(all_headers) - set(headers)) + list(set(headers) - set(all_headers)))
        )
        return []

    selected_column_positions = [i for i, header in enumerate(all_headers) if header in headers]
    results = []
    for row in table_['values']:
        results.append([row[i] for i in selected_column_positions])

    return results
