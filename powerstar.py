import wx
import wx.adv
from utils import Battery
from utils import PowerManagement

class TabPanel(wx.Panel):
    def __init__(self, parent, content):
        wx.Panel.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, label=content)
        sizer.Add(label, 0, wx.ALL | wx.CENTER, 5)
        self.SetSizer(sizer)

class TabPanelWithDropdown(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(self, label="Settings")
        title_font = title.GetFont()
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.LEFT | wx.TOP | wx.RIGHT, 10)
        
        # Horizontal sizer for label and dropdown
        label_dropdown_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        label = wx.StaticText(self, label="Select an option:")
        label_dropdown_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 20)
        
        dropdown = wx.ComboBox(self, choices=["Option 1", "Option 2", "Option 3"], style=wx.CB_READONLY)
        label_dropdown_sizer.Add(dropdown, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        label_dropdown_sizer.Add((10, 0))
        
        sizer.Add(label_dropdown_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(sizer)


class SettingsFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title="Settings")
        self.SetIcon(wx.Icon("icons/charged.png", wx.BITMAP_TYPE_ICO))
        notebook = wx.Notebook(self)
        tab1 = TabPanel(notebook, "Content of Tab 1")
        tab2 = TabPanel(notebook, "Content of Tab 2")
        tab3 = TabPanel(notebook, "Content of Tab 3")
        tab4 = TabPanelWithDropdown(notebook)

        notebook.AddPage(tab1, "Tab 1")
        notebook.AddPage(tab2, "Tab 2")
        notebook.AddPage(tab3, "Tab 3")
        notebook.AddPage(tab4, "Tab 4")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, 1, wx.EXPAND)
        self.SetSizerAndFit(sizer)
        self.SetSize(520,510)

def create_menu_item(menu, label, callback_function):
        item = wx.MenuItem(menu, -1, label)
        menu.Bind(wx.EVT_MENU, callback_function, id=item.GetId())
        menu.Append(item)
        return item

class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        self.frame = frame
        super(TaskBarIcon, self).__init__()
        self.frame = frame
        self.battery = Battery()
        self.power_management = PowerManagement()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.OnLeftDown) 
        self.timer.Start(2000)
        self.OnTimer(None)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        create_menu_item(menu, f"Mode: {self.power_management.get_performance_adjustment_mode()}", self.OnToggle)
        menu.AppendSeparator()
        create_menu_item(menu, "Settings...", self.OnSettings)
        create_menu_item(menu, "Quit", self.OnQuit)
        return menu

    def OnToggle(self, event):
        percentage = self.battery.get_battery_percentage()
        is_charging = self.battery.is_charging()
        print(is_charging)

    def OnSetIcon(self, icon_file_name, message):
        icon = wx.Icon(f"icons/{icon_file_name}")
        self.SetIcon(icon, message)

    def OnTimer(self,event):
        percentage = self.battery.get_battery_percentage() 
        is_charging = self.battery.is_charging()
        remaining = self.battery.get_battery_remaining()
        tooltip_text = f"{percentage}% ({remaining})"
        if is_charging and percentage == 100:
            self.OnSetIcon("charged.png", f"Charged {tooltip_text}")
            return
        if is_charging:
            self.OnSetIcon("charging.png", f"Charging {tooltip_text}")
            return
        if percentage >= 90:
            self.OnSetIcon("full.png", tooltip_text)
        elif percentage >= 60:
            self.OnSetIcon("almost_full.png", tooltip_text)
        elif percentage >= 40:
            self.OnSetIcon("half_full.png", tooltip_text)
        elif percentage >= 15:
            self.OnSetIcon("almost_empty.png", tooltip_text)
        elif percentage >= 5:
            self.OnSetIcon("critical.png", tooltip_text)
        else:
            self.OnSetIcon(self, "empty.png", tooltip_text)

    def OnSettings(self, event):
        if not hasattr(self.frame, 'settings_frame') or not self.frame.settings_frame:
            self.frame.settings_frame = SettingsFrame()
        self.frame.settings_frame.Show()
        self.frame.settings_frame.Raise()

    def OnQuit(self, event):
        wx.CallAfter(self.frame.Close)

    def OnLeftDown(self, event):
        print ("Left click is clicked!")

class PowerStar(wx.App):
    def OnInit(self):
        self.frame = wx.Frame(None, -1, "Hidden Frame")
        self.frame.settings_frame = None
        self.taskbar_icon = TaskBarIcon(self.frame)
        self.frame.Bind(wx.EVT_CLOSE, self.OnClose)
        return True

    def OnClose(self, event):
        if self.frame.settings_frame:
            self.frame.settings_frame.Destroy()
        self.taskbar_icon.Destroy()
        self.frame.Destroy()

if __name__ == '__main__':
    app = PowerStar(False)
    app.MainLoop()
