from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class DefaultQuotasTable(tables.TableRegion):
    name = "quotas"

    UPDATE_DEFAULTS_FORM_FIELDS = (
        "injected_file_content_bytes",
        "metadata_items",
        "server_group_members",
        "server_groups",
        "ram",
        "key_pairs",
        "injected_file_path_bytes",
        "instances",
        "injected_files",
        "cores",
        "gigabytes",
        "snapshots",
        "volumes"
    )

    @tables.bind_table_action('update_defaults')
    def update(self, update_button):
        update_button.click()
        self.wait_till_spinner_disappears()
        return forms.FormRegion(
            self.driver,
            None,
            field_mappings=self.UPDATE_DEFAULTS_FORM_FIELDS
        )


class DefaultsPage(basepage.BasePage):
    PARTIAL_URL = 'admin/defaults'
    QUOTAS_TABLE_NAME_COLUMN = 'Quota Name'
    QUOTAS_TABLE_LIMIT_COLUMN = 'Limit'
    DEFAULT_QUOTA_NAMES = [
        'Injected File Content Bytes',
        'Metadata Items',
        'Server Group Members',
        'Server Groups',
        'RAM (MB)',
        'Key Pairs',
        'Instances',
        'Injected Files',
        'VCPUs',
        'Length of Injected File Path',
        'Total Size of Volumes and Snapshots (GiB)',
        'Volume Snapshots',
        'Volumes'
    ]

    def __init__(self, driver):
        super(DefaultsPage, self).__init__(driver)
        self._page_title = "Defaults"

    def _get_quota_row(self, name):
        return self.default_quotas_table.get_row(
            self.QUOTAS_TABLE_NAME_COLUMN, name)

    @property
    def default_quotas_table(self):
        return DefaultQuotasTable(self.driver)

    @property
    def quota_values(self):
        quota_dict = {}
        for row in self.default_quotas_table.rows:
            if row.cells[self.QUOTAS_TABLE_NAME_COLUMN].text in \
                    self.DEFAULT_QUOTA_NAMES:
                quota_dict[row.cells[self.QUOTAS_TABLE_NAME_COLUMN].text] =\
                    int(row.cells[self.QUOTAS_TABLE_LIMIT_COLUMN].text)
        return quota_dict

    def update_defaults(self, add_up):
        update_form = self.default_quotas_table.update()
        update_form.injected_file_content_bytes.value = \
            int(update_form.injected_file_content_bytes.value) + add_up

        update_form.metadata_items.value = \
            int(update_form.metadata_items.value) + add_up
        update_form.server_group_members.value = int(update_form.server_group_members.value) + add_up
        update_form.server_groups.value = int(update_form.server_groups.value) + add_up
        update_form.ram.value = int(update_form.ram.value) + add_up
        update_form.key_pairs.value = int(update_form.key_pairs.value) + add_up
        update_form.injected_file_path_bytes.value = \
            int(update_form.injected_file_path_bytes.value) + add_up
        update_form.instances.value = int(update_form.instances.value) + add_up
        update_form.injected_files.value = int(
            update_form.injected_files.value) + add_up
        update_form.cores.value = int(update_form.cores.value) + add_up
        update_form.gigabytes.value = int(update_form.gigabytes.value) + add_up
        update_form.snapshots.value = int(update_form.snapshots.value) + add_up
        update_form.volumes.value = int(update_form.volumes.value) + add_up

        update_form.submit()

    def is_quota_a_match(self, quota_name, limit):
        row = self._get_quota_row(quota_name)
        return row.cells[self.QUOTAS_TABLE_LIMIT_COLUMN].text == str(limit)
