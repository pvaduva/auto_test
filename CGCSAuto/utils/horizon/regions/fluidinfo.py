from selenium.webdriver.common import by
from utils.horizon.regions import baseregion
from utils import exceptions


class FluidInfo(baseregion.BaseRegion):
    name = None
    _info_headers_locator = (by.By.CSS_SELECTOR, 'dl > dt')
    _info_details_locator = (by.By.CSS_SELECTOR, 'dl > dd')

    def _info_locator(self, info_title):
        return by.By.CSS_SELECTOR, 'div#%s' % info_title

    def __init__(self, driver, src_element=None):
        if not src_element:
            self._default_src_locator = self._info_locator(self.__class__.name)
            super(FluidInfo, self).__init__(driver)
        else:
            super(FluidInfo, self).__init__(driver, src_elem=src_element)

    @property
    def header_list(self):
        headers = []
        for element in self._get_elements(*self._info_headers_locator):
            headers.append(element.text)
        if headers is None:
            raise exceptions.HorizonError('Headers not found.')
        return headers

    @property
    def value_list(self):
        details = []
        for elem in self._get_elements(*self._info_details_locator):
            details.append(elem.text)
        if details is None:
            raise exceptions.HorizonError('Info details not found.')
        return details

    @property
    def fluid_info_dict(self):
        return dict(zip(self.header_list, self.value_list))