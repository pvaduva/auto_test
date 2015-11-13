from common_utils import DriverUtils
import settings

__author__ = 'jbarber'


class Logout():

    @classmethod
    def logout(cls):
        # Get driver
        logout_link = ""
        driver = DriverUtils.get_driver()
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Get link from partial text in table (Host Name column)
        links = driver.find_elements_by_partial_link_text('')
        for link in links:
            host_local = link.get_attribute("text")
            #print host_local
            # Match host_to_lock with link
            if("Sign Out" in host_local):
                logout_link = link.get_attribute("href")
        driver.get(DriverUtils.set_url(logout_link))
        # Navigate to newly appended URL
        driver.get(DriverUtils.get_url())
        # Reset URL to home page in Horizon
        DriverUtils.set_url(settings.DEFAULT_URL)



