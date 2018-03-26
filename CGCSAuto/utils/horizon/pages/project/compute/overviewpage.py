#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from selenium.webdriver.common import by

from utils.horizon.pages import basepage
from utils.horizon.regions import forms
from utils.horizon.regions import tables


class UsageTable(tables.TableRegion):
    name = 'project_usage'


class OverviewPage(basepage.BasePage):
    _date_form_locator = (by.By.ID, 'date_form')

    def __init__(self, driver):
        super(OverviewPage, self).__init__(driver)
        self._page_title = 'Instance Overview'

    @property
    def usage_table(self):
        return UsageTable(self.driver, self)

    @property
    def date_form(self):
        src_elem = self._get_element(*self._date_form_locator)
        return forms.DateFormRegion(self.driver, src_elem)
