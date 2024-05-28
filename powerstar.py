import wx
import wx.adv
import datetime
import subprocess
from wx.lib.embeddedimage import PyEmbeddedImage
from utils import Battery

def create_menu_item(menu, label, callback_function):
        item = wx.MenuItem(menu, -1, label)
        menu.Bind(wx.EVT_MENU, callback_function, id=item.GetId())
        menu.Append(item)
        return item

class TaskBarIcon(wx.adv.TaskBarIcon):
    battery = None
    def __init__(self, frame):
        self.frame = frame
        super(TaskBarIcon, self).__init__()
        self.battery = Battery()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(2000)
        self.OnTimer(None)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        create_menu_item(menu, "Hello", self.OnToggle)
        menu.AppendSeparator()
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

    def OnQuit(self, event):
        self.RemoveIcon()
        wx.CallAfter(self.Destroy)
        self.frame.Close()

if __name__ == '__main__':
    app = wx.App()
    frame=wx.Frame(None)
    TaskBarIcon(frame)
    app.MainLoop()
