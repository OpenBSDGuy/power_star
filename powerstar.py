import wx
import wx.adv
import datetime
import subprocess
from wx.lib.embeddedimage import PyEmbeddedImage
from utils import Battery

class TaskBarIcon(wx.adv.TaskBarIcon):
    battery = None
    def __init__(self, frame):
        self.battery = Battery()
        self.frame = frame
        self.toggle = 0
        wx.adv.TaskBarIcon.__init__(self)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.OnToggle)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(2000)
        self.OnTimer(None)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        togglem = wx.MenuItem(menu, wx.NewId(), 'Toggle Icon')
        menu.Bind(wx.EVT_MENU, self.OnToggle, id=togglem.GetId())
        menu.Append(togglem)
        menu.AppendSeparator()
        flashm = wx.MenuItem(menu, wx.NewId(), 'Flashing Icon')
        menu.Bind(wx.EVT_MENU, self.OnTimer, id=flashm.GetId())
        menu.Append(flashm)
        menu.AppendSeparator()
        quitm = wx.MenuItem(menu, wx.NewId(), 'Quit')
        menu.Bind(wx.EVT_MENU, self.OnQuit, id=quitm.GetId())
        menu.Append(quitm)
        return menu

    def OnToggle(self, event):
        percentage = self.get_battery_percentage()
        is_charging = self.is_charging()
        print(is_charging)

    def OnSetIcon(self, path, message):
        icon = wx.Icon(path)
        self.SetIcon(icon, message)

    def OnTimer(self,event):
        percentage = self.battery.get_battery_percentage() 
        is_charging = self.battery.is_charging()
        remaining = self.battery.get_battery_remaining()
        tooltip_text = f"{percentage}% ({remaining})"
        if is_charging and percentage == 100:
            self.OnSetIcon("icons_png/charged.png", f"Charged {tooltip_text}")
            return
        if is_charging:
            self.OnSetIcon("icons_png/charging.png", f"Charging {tooltip_text}")
            return
        if percentage >= 90:
            self.OnSetIcon("icons_png/full.png", tooltip_text)
        elif percentage >= 60:
            self.OnSetIcon("icons_png/almost_full.png", tooltip_text)
        elif percentage >= 40:
            self.OnSetIcon("icons_png/half_full.png", tooltip_text)
        elif percentage >= 15:
            self.OnSetIcon("icons_png/almost_empty.png", tooltip_text)
        elif percentage >= 5:
            self.OnSetIcon("icons_png/critical.png", tooltip_text)
        else:
            self.OnSetIcon(self, "icon_png/empty.png", tooltip_text)

    def OnQuit(self, event):
        self.RemoveIcon()
        wx.CallAfter(self.Destroy)
        self.frame.Close()

    def get_battery_percentage(self):
        result = subprocess.run(["apm", "-l"], capture_output=True, text=True).stdout.strip()
        return int(result)

    def is_charging(self):
        result = subprocess.run(["apm", "-a"], capture_output=True, text=True).stdout.strip()
        if int(result) == 0:
            return False
        return True

    def get_battery_remaining(self):
        try:
            minutes = subprocess.run(["apm", "-m"], capture_output=True, text=True).stdout.strip()
            hours, remainder = divmod(int(minutes), 60)
            hours_str = str(hours).zfill(2)
            minutes_str = str(remainder).zfill(2)
            return f"{hours_str}:{minutes_str}"
        except ValueError:
            return "unknown"

if __name__ == '__main__':
    app = wx.App()
    frame=wx.Frame(None)
    TaskBarIcon(frame)
    app.MainLoop()
