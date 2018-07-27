from utils.horizon.pages import basepage
from utils.horizon.regions import tables
from utils.horizon.regions import forms


class AlarmsTable(tables.TableRegion):
    name = "alarms"
    pass


class EventLogsTable(tables.TableRegion):
    name = "eventlogs"
    pass


class EventsSuppressionTable(tables.TableRegion):
    name = "eventssuppression"

    @tables.bind_row_action('suppress')
    def suppress_event(self, suppress_button, row):
        suppress_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver)

    @tables.bind_row_action('unsuppress')
    def unsuppress_event(self, unsuppress_button, row):
        unsuppress_button.click()
        self.wait_till_spinner_disappears()
        return forms.BaseFormRegion(self.driver)


class FaultManagementPage(basepage.BasePage):

    PARTIAL_URL = 'admin/fault_management'
    ACTIVE_ALARMS_TAB = 0
    EVENT_LOGS_TAB = 1
    EVENTS_SUPPRESSION_TAB = 2
    ACTIVE_ALARMS_TABLE_NAME_COLUMN = 'Timestamp'
    EVENT_LOGS_TABLE_NAME_COLUMN = 'Timestamp'
    EVENTS_SUPPRESSION_TABLE_NAME_COLUMN = 'Event ID'

    @property
    def alarms_table(self):
        return AlarmsTable(self.driver)

    @property
    def event_logs_table(self):
        return EventLogsTable(self.driver)

    @property
    def events_suppression_table(self):
        return EventsSuppressionTable(self.driver)

    def _get_row_with_alarm_timestamp(self, timestamp):
        return self.alarms_table.get_row(self.ACTIVE_ALARMS_TAB, timestamp)

    def _get_row_with_event_log_timestamp(self, timestamp):
        return self.event_logs_table.get_row(self.EVENT_LOGS_TABLE_NAME_COLUMN, timestamp)

    def _get_row_with_event_id(self, event_id):
        return self.events_suppression_table.get_row(self.EVENTS_SUPPRESSION_TABLE_NAME_COLUMN, event_id)

    def is_active_alarm_present(self, timestamp):
        return bool(self._get_row_with_alarm_timestamp(timestamp))

    def is_event_log_present(self, timestamp):
        return bool(self._get_row_with_event_log_timestamp(timestamp))

    def is_suppression_present(self, event_id):
        return bool(self._get_row_with_event_id(event_id))

    def suppress_event(self, event_id):
        row = self._get_row_with_event_id(event_id)
        confirm_form = self.events_suppression_table.suppress_event(row)
        confirm_form.submit()

    def unsuppress_event(self, event_id):
        row = self._get_row_with_event_id(event_id)
        confirm_form = self.events_suppression_table.unsuppress_event(row)
        confirm_form.submit()

    def go_to_active_alarm_tab(self):
        self.wait_till_spinner_disappears()
        self.go_to_tab(self.ACTIVE_ALARMS_TAB)

    def go_to_event_logs_tab(self):
        self.wait_till_spinner_disappears()
        self.go_to_tab(self.EVENT_LOGS_TAB)

    def go_to_events_suppression_tab(self):
        self.wait_till_spinner_disappears()
        self.go_to_tab(self.EVENTS_SUPPRESSION_TAB)
