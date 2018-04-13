from utils.horizon.pages import basepage
from utils.horizon.regions import tables


class UsageTable(tables.TableRegion):
    name = "usage"
    pass


class StorageOverviewPage(basepage.BasePage):

    PARTIAL_URL = 'admin/storage_overview'
    SERVICES_TAB_INDEX = 0
    USAGE_TAB_INDEX = 1

    def go_to_services_tab(self):
        self.go_to_tab(self.SERVICES_TAB_INDEX)

    def go_to_usage_tab(self):
        self.go_to_tab(self.USAGE_TAB_INDEX)
